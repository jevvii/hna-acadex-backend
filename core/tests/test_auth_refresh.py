from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import User


class AuthRefreshTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="refresh-user@example.com",
            password="testpass123",
            first_name="Refresh",
            last_name="User",
            role=User.Role.TEACHER,
            status=User.Status.ACTIVE,
            requires_setup=False,
        )

    def test_refresh_works_with_cookie_only(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"email": self.user.email, "password": "testpass123"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)

        refresh_response = self.client.post(reverse("token-refresh"), {}, format="json")
        self.assertEqual(refresh_response.status_code, 200)
        self.assertIn("access", refresh_response.json())
        self.assertIn("refresh", refresh_response.json())
        self.assertIn("access_token", refresh_response.cookies)
        self.assertIn("refresh_token", refresh_response.cookies)

    def test_refresh_works_with_body_token(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"email": self.user.email, "password": "testpass123"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)
        refresh_token = login_response.json()["refresh"]

        refresh_response = self.client.post(
            reverse("token-refresh"),
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refresh_response.status_code, 200)
        self.assertIn("access", refresh_response.json())
        self.assertIn("refresh", refresh_response.json())
