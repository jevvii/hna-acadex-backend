"""
Custom authentication backends for JWT token handling.
"""
from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class CookieJWTAuthentication(JWTAuthentication):
    """
    JWT authentication that reads tokens from HttpOnly cookies.

    This authentication class first tries to get the token from the Authorization header,
    and falls back to reading from cookies if not present.

    This supports both:
    - API clients using Authorization: Bearer <token> header
    - Web browsers using HttpOnly cookies (for CSRF protection)
    """

    def authenticate(self, request):
        # First try the standard Authorization header
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                try:
                    validated_token = self.get_validated_token(raw_token)
                    return self.get_user(validated_token), validated_token
                except (InvalidToken, TokenError):
                    pass

        # Fall back to cookie-based authentication
        raw_token = request.COOKIES.get(settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token'))
        if raw_token is not None:
            try:
                validated_token = self.get_validated_token(raw_token.encode())
                return self.get_user(validated_token), validated_token
            except (InvalidToken, TokenError):
                return None

        return None


__all__ = ['CookieJWTAuthentication']