from django.test import TestCase
from django.urls import reverse

from features.assessments.models import Assessment
from features.paper_exams.models import AnswerSheet, ExamRun, ImportBatch, SheetResult


class TeacherModulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from contexts.institutions.coursework.tests import CourseworkTests
        CourseworkTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.teacher.user)

    def result(self, owner, classroom, score=1, maximum=2, status='graded'):
        assessment = Assessment.objects.create(owner=owner, subject='MATEMÁTICA', topic='Teste', technique=self.technique)
        run = ExamRun.objects.create(assessment=assessment, classroom=classroom, created_by=owner,
            title='Prova teste', classroom_name=classroom.name, questions=[])
        sheet = AnswerSheet.objects.create(run=run, student=self.student.user, student_name='Aluno',student_registration='aluno')
        batch = ImportBatch.objects.create(run=run, created_by=owner, filename='teste.csv')
        return SheetResult.objects.create(sheet=sheet, batch=batch, source_name='teste', score=score,
            maximum_score=maximum, status=status)

    def test_modules_and_sidebar_render_without_administrative_privileges(self):
        for name in ('teacher-analysis','teacher-administration'):
            response = self.client.get(reverse('institutions:'+name))
            self.assertEqual(response.status_code,200)
            self.assertContains(response,reverse('institutions:teacher-analysis'))
            self.assertContains(response,reverse('institutions:teacher-administration'))
            self.assertTemplateUsed(response,'components/layout/teacher_navigation.html')
            self.assertNotContains(response,'Pessoa externa')
        self.assertEqual(self.client.get(reverse('users-manager:institutional-accounts',args=[self.organization.pk])).status_code,403)
        self.assertFalse(self.teacher.user.is_staff)
        self.assertEqual(self.teacher.role,'TEACHER')

    def test_analysis_normalizes_scores_and_excludes_other_teachers_and_classes(self):
        self.result(self.teacher.user,self.classroom,1,2)
        self.result(self.teacher.user,self.classroom,8,10)
        self.result(self.teacher.user,self.classroom,0,10,'review')
        self.result(self.teacher.user,self.classroom,0,0)
        self.result(self.teacher.user,self.other_classroom,10,10)
        self.result(self.admin,self.classroom,10,10)
        response = self.client.get(reverse('institutions:teacher-analysis'))
        self.assertEqual(response.context['metrics'],[('Provas corrigidas',2),('Aguardando revisão',1),
            ('Alunos avaliados',1),('Aproveitamento médio','65,0%')])
        self.assertEqual(len(response.context['classroom_summary']),1)
        self.assertEqual(response.context['student_page'].object_list[0]['average'],65)
        self.assertNotContains(response,'Turma sem vínculo')
        self.assertEqual(self.client.get(reverse('institutions:teacher-analysis'),
            {'classroom':self.other_classroom.pk}).status_code,400)

    def test_administration_only_offers_own_pending_corrections(self):
        own = self.result(self.teacher.user,self.classroom,0,10,'review')
        other = self.result(self.admin,self.classroom,0,10,'review')
        response = self.client.get(reverse('institutions:teacher-administration-section',args=['correcoes']))
        self.assertContains(response,reverse('paper-exams:review',args=[own.pk]))
        self.assertNotContains(response,reverse('paper-exams:review',args=[other.pk]))
        response = self.client.get(reverse('institutions:teacher-administration-section',args=['publicacoes']))
        self.assertContains(response,reverse('coursework:create',args=[self.offer.code,'MATEMÁTICA']))
        self.assertNotContains(response,reverse('users-manager:institutional-accounts',args=[self.organization.pk]))

    def test_role_and_membership_changes_apply_without_new_login(self):
        from features.users_manager.models import ClassroomMembership, InstitutionalAccount
        self.result(self.teacher.user,self.classroom)
        ClassroomMembership.objects.filter(classroom=self.classroom,user=self.teacher.user).update(status='REMOVED')
        response = self.client.get(reverse('institutions:teacher-analysis'))
        self.assertEqual(response.context['metrics'][0],('Provas corrigidas',0))
        InstitutionalAccount.objects.filter(pk=self.teacher.pk).update(role='STUDENT')
        self.assertEqual(self.client.get(reverse('institutions:teacher-administration')).status_code,403)

    def test_other_profiles_and_mutations_are_rejected(self):
        urls=[reverse('institutions:teacher-analysis'),reverse('institutions:teacher-administration')]
        for url in urls:
            self.assertEqual(self.client.post(url,{}).status_code,405)
        for role in ('ADMIN','MANAGER','OPERATOR','GUARDIAN','STUDENT'):
            self.client.force_login(self.users[role])
            for url in urls:
                self.assertEqual(self.client.get(url).status_code,403)
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code,302)

    def test_administration_opens_options_and_each_option_has_its_own_page(self):
        response = self.client.get(reverse('institutions:teacher-administration'))
        for section in ('acesso','turmas'):
            url = reverse('institutions:teacher-administration-section',args=[section])
            self.assertContains(response,url)
            self.assertEqual(self.client.get(url).status_code,200)
        self.assertContains(response,'teacher-admin-nav')
        self.assertNotContains(response,'<h2>Meu acesso institucional</h2>')
        self.client.force_login(self.users['STUDENT'])
        self.assertEqual(self.client.get(reverse('institutions:teacher-administration-section',args=['turmas'])).status_code,403)
