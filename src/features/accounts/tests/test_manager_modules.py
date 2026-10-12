from django.test import TestCase
from django.urls import reverse


class ManagerModulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_institutional_contexts import InstitutionalContextTests
        InstitutionalContextTests.setUpTestData.__func__(cls)

    def urls(self):
        return [reverse('institutions:gestor'), reverse('institutions:manager-performance')] + [
            reverse('institutions:manager-module', args=[slug])
            for slug in ('academico', 'analise', 'administracao', 'institucional')]

    def test_modules_render_for_management_without_cross_tenant_content(self):
        for role in ('ADMIN', 'MANAGER'):
            self.client.force_login(self.users[role])
            for url in self.urls():
                with self.subTest(role=role, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'Escola local')
                    self.assertNotContains(response, 'Pessoa externa')
                    self.assertNotContains(response, 'Turma externa')
                    self.assertTemplateUsed(response, 'components/layout/sidebar.html')
                    self.assertTemplateUsed(response, 'notifications/bell.html')

    def test_modules_reject_other_roles_and_mutation_requests(self):
        for role in ('TEACHER', 'STUDENT', 'OPERATOR', 'GUARDIAN'):
            self.client.force_login(self.users[role])
            for url in self.urls():
                self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('institutions:manager-performance')).status_code, 405)
        self.assertEqual(self.client.get(reverse('institutions:manager-module', args=['unknown'])).status_code, 404)

    def test_performance_is_nested_and_admin_actions_keep_their_permissions(self):
        self.client.force_login(self.users['MANAGER'])
        academic = self.client.get(reverse('institutions:manager-module', args=['academico']))
        self.assertContains(academic, reverse('institutions:manager-performance'))
        self.assertNotContains(academic, reverse('planning:index'))
        admin_url = reverse('institutions:manager-module', args=['administracao'])
        action_url = reverse('users-manager:institutional-accounts', args=[self.organization.pk])
        self.assertNotContains(self.client.get(admin_url), action_url)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(admin_url), action_url)
        self.assertContains(self.client.get(reverse('institutions:manager-module', args=['academico'])),
                            reverse('planning:index'))

    def test_directory_search_stays_in_institution(self):
        self.client.force_login(self.users['MANAGER'])
        url = reverse('institutions:manager-module', args=['administracao'])
        response = self.client.get(url, {'q': 'STUDENT', 'organization': self.other.pk})
        self.assertContains(response, 'Pessoa STUDENT')
        self.assertNotContains(response, 'Pessoa TEACHER')
        self.assertNotContains(response, 'Pessoa externa')

    def test_performance_uses_percentages_and_excludes_review_and_external_results(self):
        from features.assessments.models import Assessment, AssessmentTechnique
        from features.paper_exams.models import AnswerSheet, ExamRun, ImportBatch, SheetResult
        from features.users_manager.models import Classroom
        technique = AssessmentTechnique.objects.create(code='manager-test', name='Teste')
        assessment = Assessment.objects.create(owner=self.admin, subject='Matemática', topic='Teste', technique=technique)
        cases = [(self.classroom, 1, 2, 'graded'), (self.classroom, 8, 10, 'graded'),
                 (self.classroom, 0, 10, 'review'), (self.classroom, 0, 0, 'graded'),
                 (Classroom.objects.get(organization=self.other), 10, 10, 'graded')]
        for classroom, score, maximum, status in cases:
            run = ExamRun.objects.create(assessment=assessment, classroom=classroom, created_by=self.admin,
                                        title='Prova', classroom_name=classroom.name, questions=[])
            sheet = AnswerSheet.objects.create(run=run, student=self.users['STUDENT'], student_name='Aluno', student_registration='s')
            batch = ImportBatch.objects.create(run=run, created_by=self.admin, filename='test.csv')
            SheetResult.objects.create(sheet=sheet, batch=batch, source_name='test', status=status,
                                       score=score, maximum_score=maximum)
        self.client.force_login(self.users['MANAGER'])
        response = self.client.get(reverse('institutions:manager-performance'))
        self.assertEqual(response.context['metrics'], [('Provas corrigidas', 2), ('Aguardando revisão', 1),
                                                     ('Aproveitamento médio', '65,0%')])
        self.assertEqual(len(response.context['performance_page']), 1)
        self.assertContains(response, '65,0%')
        self.assertNotContains(response, 'Turma externa')
