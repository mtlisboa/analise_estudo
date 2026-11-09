"""Render the institutional menu routes with disposable data, not the saved-analysis panel."""
import json
import os
import sys
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.development'
os.environ['SQLITE_PATH'] = ':memory:'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'testserver'
import django
django.setup()
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from contexts.institutions.analysis.tests import AnalysisTests
from contexts.institutions.coursework.models import Publication
call_command('migrate', verbosity=0)
AnalysisTests.setUpTestData()
fixture = AnalysisTests()
for day, score in enumerate([4, 5.5, 5, 7, 6.5, 8], start=1):
    publication = Publication.objects.create(offer=fixture.offer, subject='MATEMÁTICA', teacher=fixture.teacher, assessment=fixture.assessment, kind='EXAM', title=f'Atividade {day}')
    fixture.evidence(publication=publication, skill=f'H{day}', criterion=f'criterion-{day}', date=date(2026,10,day), score=score, maximum=10)
client = Client()
client.force_login(fixture.users['MANAGER'])
manager_url = reverse('institutions:manager-module', args=['analise'])
pages = {}
for section in ['overview','learning','classes','students','items','attendance','interventions','trajectory','official']:
    response = client.get(manager_url, {'section': section})
    assert response.status_code == 200, (section, response.status_code)
    pages[section] = response.content.decode()
pages['empty'] = client.get(manager_url, {'start':'2027-01-01'}).content.decode()
pages['record'] = client.get(reverse('institutions:institution-analysis:record', args=['evidencia'])).content.decode()
client.force_login(fixture.teacher.user)
pages['teacher'] = client.get(reverse('institutions:teacher-analysis')).content.decode()
print(json.dumps(pages))
