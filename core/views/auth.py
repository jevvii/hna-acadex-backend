"""
Authentication-related views.
"""
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.utils.decorators import method_decorator
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import PasswordResetRequest, User
from core.permissions import IsAdminRole
from core.serializers import UserCreateSerializer, UserSerializer
from core.views.common import validate_file_upload, ALLOWED_IMAGE_TYPES
from core.decorators import rate_limit_login, rate_limit_password_reset, rate_limit_file_upload


def get_jwt_settings():
    """Get JWT cookie settings from Django settings."""
    return settings.SIMPLE_JWT


def set_auth_cookies(response, access_token, refresh_token=None):
    """
    Set JWT tokens as HttpOnly cookies on the response.

    HttpOnly cookies are secure against XSS attacks and are automatically
    sent with requests when credentials: 'include' is used in fetch.
    """
    jwt_settings = get_jwt_settings()
    cookie_name = jwt_settings.get('AUTH_COOKIE', 'access_token')
    refresh_cookie_name = jwt_settings.get('AUTH_COOKIE_REFRESH', 'refresh_token')
    cookie_secure = jwt_settings.get('AUTH_COOKIE_SECURE', False)
    cookie_httponly = jwt_settings.get('AUTH_COOKIE_HTTP_ONLY', True)
    cookie_samesite = jwt_settings.get('AUTH_COOKIE_SAMESITE', 'Lax')
    cookie_path = jwt_settings.get('AUTH_COOKIE_PATH', '/')
    access_max_age = jwt_settings.get('ACCESS_TOKEN_LIFETIME').total_seconds() if hasattr(jwt_settings.get('ACCESS_TOKEN_LIFETIME'), 'total_seconds') else 300
    refresh_max_age = jwt_settings.get('REFRESH_TOKEN_LIFETIME').total_seconds() if hasattr(jwt_settings.get('REFRESH_TOKEN_LIFETIME'), 'total_seconds') else 86400

    response.set_cookie(
        cookie_name,
        access_token,
        max_age=int(access_max_age),
        path=cookie_path,
        secure=cookie_secure,
        httponly=cookie_httponly,
        samesite=cookie_samesite,
    )

    if refresh_token:
        response.set_cookie(
            refresh_cookie_name,
            refresh_token,
            max_age=int(refresh_max_age),
            path=cookie_path,
            secure=cookie_secure,
            httponly=cookie_httponly,
            samesite=cookie_samesite,
        )


def clear_auth_cookies(response):
    """Clear JWT authentication cookies."""
    jwt_settings = get_jwt_settings()
    cookie_name = jwt_settings.get('AUTH_COOKIE', 'access_token')
    refresh_cookie_name = jwt_settings.get('AUTH_COOKIE_REFRESH', 'refresh_token')
    cookie_path = jwt_settings.get('AUTH_COOKIE_PATH', '/')

    response.delete_cookie(cookie_name, path=cookie_path)
    response.delete_cookie(refresh_cookie_name, path=cookie_path)


class AuthLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    @method_decorator(rate_limit_login)
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        if not email or not password:
            return Response({"detail": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=email, password=password)
        if not user:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        if user.status != User.Status.ACTIVE:
            return Response({"detail": "This account is inactive."}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = Response({
            "access": access_token,
            "refresh": refresh_token,
            "user": UserSerializer(user, context={"request": request}).data,
        })

        # Set JWT tokens as HttpOnly cookies for web clients
        set_auth_cookies(response, access_token, refresh_token)
        return response


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)


class ChangePasswordView(APIView):
    """Change password for authenticated users. Used for first-time setup."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        new_password = request.data.get("new_password")

        if not new_password:
            return Response(
                {"detail": "New password is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(new_password) < 8:
            return Response(
                {"detail": "Password must be at least 8 characters long."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Set the new password (this hashes it)
        user.set_password(new_password)
        user.requires_setup = False
        # Save all fields to ensure password is properly persisted
        user.save()

        # Generate new tokens for the user
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = Response({
            "detail": "Password changed successfully.",
            "access": access_token,
            "refresh": refresh_token,
            "user": UserSerializer(user, context={"request": request}).data,
        })

        # Set JWT tokens as HttpOnly cookies for web clients
        set_auth_cookies(response, access_token, refresh_token)
        return response


class AuthLogoutView(APIView):
    """Logout view that clears authentication cookies."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        response = Response({"detail": "Successfully logged out."})
        clear_auth_cookies(response)
        return response


class ForgotPasswordRequestView(APIView):
    """Request a password reset. Creates a pending request for admin approval."""
    permission_classes = [permissions.AllowAny]

    @method_decorator(rate_limit_password_reset)
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response(
                {"detail": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find user by school email
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal if user exists or not
            return Response({
                "detail": "If an account with that email exists, a password reset request has been submitted. Please wait for admin approval."
            })

        # Only teachers and students can request password reset
        if user.role not in [User.Role.TEACHER, User.Role.STUDENT]:
            return Response(
                {"detail": "Only teachers and students can request password reset."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if user has personal email
        if not user.personal_email:
            return Response(
                {"detail": "No personal email configured for this account. Please contact administrator."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Rate limit: 1 request per hour per email
        cache_key = f"password_reset_rate:{email}"
        if cache.get(cache_key):
            return Response(
                {"detail": "A password reset request was recently submitted. Please wait before requesting another."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Check for existing pending request
        existing_pending = PasswordResetRequest.objects.filter(
            user=user,
            status=PasswordResetRequest.Status.PENDING
        ).exists()

        if existing_pending:
            return Response({
                "detail": "A password reset request is already pending. Please wait for admin approval."
            })

        # Create the request
        PasswordResetRequest.objects.create(
            user=user,
            personal_email=user.personal_email,
        )

        # Set rate limit cache (1 hour)
        cache.set(cache_key, True, timeout=3600)

        return Response({
            "detail": "Password reset request submitted. You will receive an email once approved by administrator."
        })


class ProfileViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("last_name", "first_name")

    def get_permissions(self):
        if self.action in ["list", "create", "destroy", "toggle_status"]:
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def get_queryset(self):
        user = self.request.user
        role = self.request.query_params.get("role")

        qs = User.objects.all()
        if role:
            qs = qs.filter(role=role)

        if user.role != User.Role.ADMIN:
            return qs.filter(id=user.id)
        return qs.order_by("last_name", "first_name")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        partial = kwargs.pop("partial", False)

        if request.user.role != User.Role.ADMIN and request.user.id != instance.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        serializer = UserSerializer(instance, data=request.data, partial=partial, context={"request": request})
        serializer.is_valid(raise_exception=True)

        if request.user.role != User.Role.ADMIN:
            allowed_fields = {"first_name", "last_name", "middle_name", "avatar_url", "theme", "section", "grade_level", "strand"}
            for key in list(serializer.validated_data.keys()):
                if key not in allowed_fields:
                    serializer.validated_data.pop(key, None)

        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def toggle_status(self, request, pk=None):
        user = self.get_object()
        user.status = User.Status.INACTIVE if user.status == User.Status.ACTIVE else User.Status.ACTIVE
        user.save(update_fields=["status", "updated_at"])
        return Response(UserSerializer(user, context={"request": request}).data)


class AvatarUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(rate_limit_file_upload)
    def post(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"detail": "file is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_file_upload(file_obj, ALLOWED_IMAGE_TYPES)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        request.user.avatar = file_obj
        request.user.save()

        # Return the updated user with avatar_url
        return Response(UserSerializer(request.user, context={"request": request}).data)


__all__ = [
    'AuthLoginView',
    'AuthLogoutView',
    'MeView',
    'ChangePasswordView',
    'ForgotPasswordRequestView',
    'ProfileViewSet',
    'AvatarUploadView',
]