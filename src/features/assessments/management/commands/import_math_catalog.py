from django.core.management.base import BaseCommand, CommandError
from features.users_manager.models import Organization
from features.assessments.catalog import import_math_catalog


class Command(BaseCommand):
    help = 'Importa MATH-PT nas instituições ativas sem duplicar ou sobrescrever questões.'

    def add_arguments(self, parser):
        parser.add_argument('--organization', type=int)

    def handle(self, *args, **options):
        organizations = Organization.objects.filter(is_active=True)
        if options['organization'] is not None:
            organizations = organizations.filter(pk=options['organization'])
            if not organizations.exists():
                raise CommandError('Instituição ativa não encontrada.')
        total = 0
        for organization in organizations.iterator():
            count = import_math_catalog(organization)
            total += count
            self.stdout.write(f'{organization.pk}: {count} questões adicionadas.')
        self.stdout.write(self.style.SUCCESS(f'Total: {total} questões adicionadas.'))
