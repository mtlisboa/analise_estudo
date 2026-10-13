from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from features.paper_exams.models import ExamRun, AnswerSheet, ImportBatch, SheetResult
from features.users_manager.models import ClassroomMembership
from .models import Evidence, Attendance, Curriculum, Trajectory, KeyRevision, OfferContext, Audit
from .scope import Scope
from .services import build,percent

class AnalysisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from ..coursework.tests import CourseworkTests
        CourseworkTests.setUpTestData.__func__(cls)
    def setUp(self):
        self.client.force_login(self.teacher.user)
        self.url=reverse('institutions:institution-analysis:index')
    def result(self,subject='MATEMÁTICA',answers=None):
        run=ExamRun.objects.create(assessment=self.assessment,classroom=self.classroom,created_by=self.teacher.user,
            subject=subject,title='Teste',classroom_name='Teste',questions=[{'id':1,'statement':'Questão','options':['sim','não'],
                'correct':'A','points':'2','diagnostic_metadata':{'skills':['H1'],'alternatives':{'B':{'hypothesis':'Confusão conceitual','reviewed':True}}}}])
        sheet=AnswerSheet.objects.create(run=run,student=self.student.user,student_name='Aluno',student_registration='aluno')
        batch=ImportBatch.objects.create(run=run,created_by=self.teacher.user,filename='test.csv')
        return SheetResult.objects.create(sheet=sheet,batch=batch,source_name='test',answers=answers or ['B'],score=0,maximum_score=2,status='graded')
    def evidence(self,attempt=1,**kw):
        data=dict(offer=self.offer,subject='MATEMÁTICA',student=self.student,publication=self.publication,
            skill='H1',criterion='item',attempt=attempt,date=date(2026,10,1),score=1,maximum=2,created_by=self.teacher.user)
        data.update(kw);return Evidence.objects.create(**data)
    def test_scope_and_formats_reject_subject_and_ids(self):
        self.result();self.result('CIÊNCIAS')
        for fmt in ('','json','csv'):
            response=self.client.get(self.url,{'format':fmt})
            self.assertEqual(response.status_code,200)
            self.assertNotContains(response,'CIÊNCIAS')
            self.assertEqual(self.client.get(self.url,{'format':fmt,'subject':'CIÊNCIAS'}).status_code,400)
            self.assertEqual(self.client.get(self.url,{'format':fmt,'offer':99999}).status_code,400)
        ClassroomMembership.objects.filter(user=self.teacher.user).update(status='REMOVED')
        self.assertEqual(build(Scope(self.teacher.user),{})['evaluated'],0)
    def test_other_institution_manager_never_sees_local_data(self):
        self.result()
        other_user=self.other.institutional_accounts.get(role='ADMIN').user
        other_user.must_change_password=False;other_user.save()
        self.client.force_login(other_user)
        self.assertEqual(self.client.get(self.url,{'format':'json'}).json()['evaluated'],0)
        self.assertEqual(self.client.get(self.url,{'offer':self.offer.pk}).status_code,400)
    def test_student_guardian_operator_forbidden(self):
        for role in ('STUDENT','GUARDIAN','OPERATOR'):
            self.client.force_login(self.users[role]);self.assertEqual(self.client.get(self.url).status_code,403)
    def test_latest_attempt_and_qualitative_evidence(self):
        self.evidence();self.evidence(2,score=2)
        self.evidence(3,score=None,maximum=None,status='pending')
        d=build(Scope(self.teacher.user),{})
        self.assertEqual(d['rows'][0]['percentage'],100)
        self.assertEqual(d['skills'][0]['count'],1)
        self.assertEqual(d['skills'][0]['status'],'Evidência insuficiente')
        self.assertEqual(percent(0,0),None);self.assertEqual(percent(0,2),0)
    def test_distractor_blank_invalid_and_snapshot(self):
        r=self.result();d=build(Scope(self.teacher.user),{})
        self.assertEqual(d['hypotheses'][0]['count'],1)
        self.question.correct_answer='Mudança no banco';self.question.save()
        self.assertEqual(build(Scope(self.teacher.user),{})['items'][0]['percentage'],0)
        r.answers=[''];r.save();self.assertEqual(build(Scope(self.teacher.user),{})['items'][0]['blank'],1)
        r.answers=['Z'];r.save();d=build(Scope(self.teacher.user),{})
        self.assertEqual(d['items'][0]['invalid'],1);self.assertEqual(d['hypotheses'],[])
    def test_key_revision_and_annulment_audited(self):
        r=self.result();url=reverse('institutions:institution-analysis:record',args=['gabarito'])
        payload={'run':r.sheet.run_id,'question_index':1,'correct':'B','reason':'Correção validada','change_reason':'Conferência'}
        response=self.client.post(url,payload)
        self.assertEqual(response.status_code,302)
        r.refresh_from_db();self.assertEqual(r.score,2)
        self.assertEqual(build(Scope(self.teacher.user),{})['rows'][0]['percentage'],100)
        self.assertEqual(r.sheet.run.questions[0]['correct'],'A')
        payload.update(annulled='on',correct='');self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(build(Scope(self.teacher.user),{})['rows'],[])
        self.assertTrue(Audit.objects.exists())
    def test_forms_validate_cross_subject_and_collect_evidence(self):
        url=reverse('institutions:institution-analysis:record',args=['evidencia'])
        payload={'offer':self.offer.pk,'subject':'MATEMÁTICA','student':self.student.pk,'publication':self.publication.pk,
            'skill':'H1','criterion':'discursiva','attempt':1,'date':'2026-10-01','score':1,'maximum':2,
            'status':'evaluated','purpose':'regular','change_reason':'Rubrica conferida'}
        response=self.client.post(url,payload)
        self.assertEqual(response.status_code,302, getattr(response,'context',None))
        self.assertEqual(Evidence.objects.count(),1)
        payload['subject']='CIÊNCIAS';self.assertEqual(self.client.post(url,payload).status_code,200)
        self.assertEqual(Evidence.objects.count(),1)
        for kind in ('oficial','trajetoria','configuracao'):
            self.assertEqual(self.client.get(reverse('institutions:institution-analysis:record',args=[kind])).status_code,403)
    def test_attendance_and_transfer(self):
        Attendance.objects.create(offer=self.offer,subject='MATEMÁTICA',student=self.student,date=date(2026,10,1),hours=4,present=3)
        self.assertEqual(build(Scope(self.teacher.user),{})['attendance'][0]['percentage'],75)
        t=Trajectory(offer=self.offer,student=self.student,outcome='transferred',transition='dropout',next_year=2027,verification='Fonte')
        with self.assertRaises(ValidationError):t.full_clean()
        t.transition='';t.save()
        d=build(Scope(self.admin),{});self.assertEqual(d['rate_denominator'],0);self.assertEqual(d['transferred'],1)
    def test_all_sections_and_forms_render_for_manager(self):
        self.client.force_login(self.admin)
        for section in ('overview','learning','classes','students','items','attendance','interventions','trajectory','official'):
            self.assertEqual(self.client.get(self.url,{'section':section}).status_code,200)
        for kind in ('evidencia','oficial','trajetoria','configuracao','curriculo','intervencao','frequencia','gabarito'):
            self.assertEqual(self.client.get(reverse('institutions:institution-analysis:record',args=[kind])).status_code,200)
    def test_tampered_write_foreign_keys_are_form_errors(self):
        url=reverse('institutions:institution-analysis:record',args=['evidencia'])
        response=self.client.post(url,{'offer':999999,'subject':'MATEMÁTICA','student':999999,'publication':999999,
            'skill':'H','criterion':'x','attempt':1,'date':'2026-10-01','score':0,'maximum':1,
            'status':'evaluated','purpose':'regular','change_reason':'Teste'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(Evidence.objects.exists())
        self.assertEqual(self.client.get(self.url,{'classroom':'abc'}).status_code,400)
    def test_annulled_attempt_removes_prior_criterion_and_history_is_kept(self):
        self.evidence();self.evidence(2,status='annulled')
        d=build(Scope(self.teacher.user),{})
        self.assertEqual(d['rows'],[])
        self.assertEqual(len(d['evidence_history']),2)
    def test_skills_in_other_subject_do_not_cover_curriculum(self):
        self.evidence()
        self.offer.published_schedule.append({'subject':'CIÊNCIAS','teacher_id':self.teacher.pk});self.offer.save()
        Curriculum.objects.create(offer=self.offer,subject='CIÊNCIAS',skill='H1',description='Outro conceito',source='Local')
        self.assertEqual(build(Scope(self.teacher.user),{})['coverage'][0]['status'],'Não avaliada')
    def test_official_registration_requires_matching_inep_and_preserves_audit(self):
        from .models import OfficialResult
        self.client.force_login(self.admin)
        school=self.organization.school;school.inep_code='25000001';school.save()
        url=reverse('institutions:institution-analysis:record',args=['oficial'])
        payload={'indicator':'ideb','year':2025,'stage':'fundamental','area':'Anos finais','value':'5.8','unit':'índice',
            'status':'published','source':'https://www.gov.br/inep','methodology':'Referência conferida na fonte para esta escola.',
            'change_reason':'Registro da publicação'}
        response=self.client.post(url,payload)
        self.assertEqual(response.status_code,302)
        record=OfficialResult.objects.get();self.assertEqual(record.inep_code,'25000001')
        self.assertEqual(record.organization,self.organization)
        self.assertTrue(Audit.objects.filter(model='institution_analysis.OfficialResult').exists())
        self.client.force_login(self.teacher.user)
        self.assertEqual(self.client.get(reverse('institutions:institution-analysis:edit',args=['oficial',record.pk])).status_code,403)
    def test_snapshot_diagnostics_copy_without_changing_sharing(self):
        from features.assessments.forms import QuestionForm
        from features.paper_exams.services import issue_run
        self.question.delete()
        form=QuestionForm(data={'question_type':'multiple_choice','statement':'Escolha','options':'A\nB','correct_answer':'A','points':2,
            'skill_codes':'H1','diagnostic_B_hypothesis':'Confusão','diagnostic_B_reviewed':'on'})
        self.assertTrue(form.is_valid(),form.errors)
        question=form.save(self.assessment)
        self.assertEqual(question.diagnostic_metadata['skills'],['H1'])
        self.assertIsNone(question.bank_item.organization)
        run=issue_run(self.assessment,self.classroom,self.teacher.user)
        question.diagnostic_metadata={};question.save()
        self.assertEqual(run.questions[0]['diagnostic_metadata']['alternatives']['B']['hypothesis'],'Confusão')
    def test_edit_cannot_move_evidence_identity_and_break_intervention_scope(self):
        e=self.evidence()
        payload={'offer':self.offer.pk,'subject':'MATEMÁTICA','student':self.student.pk,'publication':self.publication.pk,
            'skill':'OTHER','criterion':'item','attempt':1,'date':'2026-10-01','score':2,'maximum':2,
            'status':'evaluated','purpose':'regular','change_reason':'Alteração'}
        response=self.client.post(reverse('institutions:institution-analysis:edit',args=['evidencia',e.pk]),payload)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context['form'].errors)
        e.refresh_from_db();self.assertEqual(e.skill,'H1')
