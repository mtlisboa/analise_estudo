from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import PermissionDenied
from contexts.ia_integrations.rag.auth import issue_token


class Command(BaseCommand):
    help = 'Emitir credencial MCP somente leitura para um usuário (expira em 5 minutos).'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, required=True)

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(pk=options['user_id'])
            self.stdout.write(issue_token(user))
        except (get_user_model().DoesNotExist, PermissionDenied) as exc:
            raise CommandError('Usuário indisponível.') from exc
