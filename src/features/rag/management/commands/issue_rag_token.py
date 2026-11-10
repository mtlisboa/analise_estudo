from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import PermissionDenied
from features.rag.bootstrap import build_repository
from features.rag.exceptions import AgentUnavailable


class Command(BaseCommand):
    help = 'Emitir credencial MCP somente leitura para um usuário (expira em 5 minutos).'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, required=True)

    def handle(self, *args, **options):
        try:
            self.stdout.write(async_to_sync(build_repository().issue_token)(options['user_id']))
        except (PermissionDenied, AgentUnavailable) as exc:
            raise CommandError('Usuário indisponível.') from exc
