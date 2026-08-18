from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.settings.environment import csv_values, railway_origin


class EnvironmentSettingsTests(SimpleTestCase):
    def test_csv_values_removes_blanks_and_duplicates(self) -> None:
        values = csv_values(" https://one.test, ,https://two.test,https://one.test ")

        self.assertEqual(values, ["https://one.test", "https://two.test"])

    def test_railway_origin_adds_https_scheme(self) -> None:
        self.assertEqual(
            railway_origin("analiseestudo-production.up.railway.app"),
            "https://analiseestudo-production.up.railway.app",
        )

    def test_railway_origin_ignores_empty_domain(self) -> None:
        self.assertEqual(railway_origin(""), "")


class RailwayCsrfIntegrationTests(TestCase):
    domain = "analiseestudo-production.up.railway.app"
    origin = f"https://{domain}"

    @override_settings(
        ALLOWED_HOSTS=[domain],
        CSRF_TRUSTED_ORIGINS=[origin],
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
    )
    def test_accepts_login_post_from_railway_public_origin(self) -> None:
        get_user_model().objects.create_user(
            username="railway-user", password="safe-password"
        )
        client = Client(enforce_csrf_checks=True)
        request_headers = {
            "HTTP_HOST": self.domain,
            "HTTP_X_FORWARDED_PROTO": "https",
        }
        response = client.get(reverse("accounts:login"), **request_headers)
        csrf_token = response.cookies["csrftoken"].value

        response = client.post(
            reverse("accounts:login"),
            {
                "username": "railway-user",
                "password": "safe-password",
                "csrfmiddlewaretoken": csrf_token,
            },
            HTTP_ORIGIN=self.origin,
            **request_headers,
        )

        self.assertEqual(response.status_code, 302)

    @override_settings(
        ALLOWED_HOSTS=[domain],
        CSRF_TRUSTED_ORIGINS=[origin],
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
    )
    def test_accepts_sign_up_post_from_railway_public_origin(self) -> None:
        client = Client(enforce_csrf_checks=True)
        request_headers = {
            "HTTP_HOST": self.domain,
            "HTTP_X_FORWARDED_PROTO": "https",
        }
        response = client.get(reverse("accounts:sign-up"), **request_headers)
        csrf_token = response.cookies["csrftoken"].value

        response = client.post(
            reverse("accounts:sign-up"),
            {
                "username": "new-railway-user",
                "email": "new-railway-user@example.com",
                "password1": "safe-password-456",
                "password2": "safe-password-456",
                "csrfmiddlewaretoken": csrf_token,
            },
            HTTP_ORIGIN=self.origin,
            **request_headers,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            get_user_model().objects.filter(username="new-railway-user").exists()
        )
