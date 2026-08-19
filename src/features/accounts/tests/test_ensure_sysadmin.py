from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from features.accounts.models import User


class EnsureSysAdminCommandTests(TestCase):
    env = {
        "DJANGO_SYSADMIN_NAME": "Matheus Lisboa",
        "DJANGO_SYSADMIN_LOGIN": "sysadmin",
        "DJANGO_SYSADMIN_EMAIL": "sysadmin@example.com",
        "DJANGO_SYSADMIN_PASSWORD": "senha-forte-123",
    }

    @patch.dict("os.environ", {}, clear=True)
    def test_skips_when_environment_is_not_configured(self) -> None:
        call_command("ensure_sysadmin")

        self.assertFalse(User.objects.exists())

    @patch.dict("os.environ", env, clear=True)
    def test_creates_sysadmin_from_environment(self) -> None:
        call_command("ensure_sysadmin")

        user = User.objects.get(username="sysadmin")
        self.assertEqual(user.get_full_name(), "Matheus Lisboa")
        self.assertEqual(user.email, "sysadmin@example.com")
        self.assertEqual(user.system_role, User.SystemRole.SYSADMIN)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("senha-forte-123"))

    @patch.dict("os.environ", env, clear=True)
    def test_updates_existing_sysadmin_and_rotates_password(self) -> None:
        user = User.objects.create_user(
            username="sysadmin",
            email="old@example.com",
            password="senha-antiga",
        )

        call_command("ensure_sysadmin")

        user.refresh_from_db()
        self.assertEqual(user.email, "sysadmin@example.com")
        self.assertEqual(user.system_role, User.SystemRole.SYSADMIN)
        self.assertTrue(user.check_password("senha-forte-123"))

    @patch.dict(
        "os.environ",
        {"DJANGO_SYSADMIN_LOGIN": "sysadmin"},
        clear=True,
    )
    def test_rejects_incomplete_environment(self) -> None:
        with self.assertRaisesMessage(CommandError, "Configuração incompleta"):
            call_command("ensure_sysadmin")

    @patch.dict("os.environ", env, clear=True)
    def test_rejects_email_owned_by_another_user(self) -> None:
        User.objects.create_user(
            username="existing",
            email="sysadmin@example.com",
            password="senha-existente",
        )

        with self.assertRaisesMessage(CommandError, "já pertence"):
            call_command("ensure_sysadmin")
