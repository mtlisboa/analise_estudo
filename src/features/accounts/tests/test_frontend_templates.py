from pathlib import Path

from django.conf import settings
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse


class FrontendTemplateTests(TestCase):
    def test_all_project_templates_compile(self):
        for path in Path(settings.BASE_DIR).rglob('*.html'):
            if 'templates' not in path.parts:
                continue
            name = '/'.join(path.parts[path.parts.index('templates') + 1:])
            with self.subTest(template=name):
                get_template(name)

    def test_login_uses_shared_fields_and_preserves_redirect(self):
        response = self.client.get(reverse('accounts:login'), {'next': '/instituicao/'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'components/forms/fields.html')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'value="/instituicao/"')
        self.assertContains(response, 'css/workspace.css')

    def test_public_home_explains_institutional_workflow(self):
        response = self.client.get(reverse('accounts:landing'))
        self.assertContains(response, 'Da lista de alunos à turma publicada.')
        self.assertContains(response, reverse('accounts:institutional-contact'))
        self.assertContains(response, 'Acadêmico com turmas e desempenho')
