import signal
import threading
import logging

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from contexts.institutions.coursework.scheduling import run_due_applications


class Command(BaseCommand):
    help = 'Executa aplicações agendadas, inclusive sem usuários conectados.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        stopped = threading.Event()
        if not options['once']:
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *args: stopped.set())
        while not stopped.is_set():
            close_old_connections()
            try:
                total = run_due_applications()
                if total:
                    self.stdout.write(f'{total} aplicações executadas.')
            except Exception:
                logging.getLogger(__name__).exception('Application scheduler iteration failed')
                if options['once']:
                    raise
            if options['once']:
                return
            stopped.wait(15)
