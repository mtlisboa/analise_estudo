import os

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction


class Command(BaseCommand):
    help = "Cria ou atualiza o sysadmin definido pelas variáveis de ambiente."

    env_names = (
        "DJANGO_SYSADMIN_NAME",
        "DJANGO_SYSADMIN_LOGIN",
        "DJANGO_SYSADMIN_EMAIL",
        "DJANGO_SYSADMIN_PASSWORD",
    )

    def handle(self, *args, **options) -> None:
        values = {
            "DJANGO_SYSADMIN_NAME": os.getenv("DJANGO_SYSADMIN_NAME", "").strip(),
            "DJANGO_SYSADMIN_LOGIN": os.getenv(
                "DJANGO_SYSADMIN_LOGIN", ""
            ).strip(),
            "DJANGO_SYSADMIN_EMAIL": os.getenv(
                "DJANGO_SYSADMIN_EMAIL", ""
            ).strip(),
            "DJANGO_SYSADMIN_PASSWORD": os.getenv(
                "DJANGO_SYSADMIN_PASSWORD", ""
            ),
        }

        if not any(values.values()):
            self.stdout.write("Sysadmin por ambiente não configurado; ignorando.")
            return

        missing = [name for name in self.env_names if not values[name]]
        if missing:
            raise CommandError(
                "Configuração incompleta do sysadmin. Variáveis ausentes: "
                + ", ".join(missing)
            )

        full_name = values["DJANGO_SYSADMIN_NAME"]
        username = values["DJANGO_SYSADMIN_LOGIN"]
        email = values["DJANGO_SYSADMIN_EMAIL"]
        password = values["DJANGO_SYSADMIN_PASSWORD"]

        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("DJANGO_SYSADMIN_EMAIL não é um e-mail válido.") from exc

        name_parts = full_name.split(maxsplit=1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) == 2 else ""

        User = get_user_model()
        normalized_email = User.objects.normalize_email(email)

        with transaction.atomic():
            email_owner = (
                User.objects.filter(email__iexact=normalized_email)
                .exclude(username=username)
                .first()
            )
            if email_owner:
                raise CommandError(
                    "DJANGO_SYSADMIN_EMAIL já pertence a outro usuário."
                )

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": normalized_email,
                },
            )

            user.first_name = first_name
            user.last_name = last_name
            user.email = normalized_email
            user.system_role = User.SystemRole.SYSADMIN
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True

            password_changed = not user.check_password(password)
            if password_changed:
                user.set_password(password)

            user.save()

        action = "criado" if created else "atualizado"
        self.stdout.write(
            self.style.SUCCESS(f'Sysadmin "{username}" {action} com sucesso.')
        )
