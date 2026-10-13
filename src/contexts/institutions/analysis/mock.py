"""Idempotent additions to the existing, explicitly named demonstration institution."""
from datetime import timedelta
from django.utils import timezone
from .models import OfferContext, Curriculum, Evidence, Attendance, Intervention, Trajectory, OfficialResult
from ..planning.models import Offer
from ..coursework.models import Publication
from features.users_manager.models import InstitutionalAccount, Organization, School
from features.paper_exams.models import ExamRun

def populate(organization, administrator):
    if organization.name != 'Colégio Lumini Demo':
        raise ValueError('A carga de demonstração não pode usar uma instituição real.')
    now=timezone.localdate()
    for offer in Offer.objects.filter(period__organization=organization).select_related('period'):
        OfferContext.objects.get_or_create(offer=offer,defaults={'stage':'fundamental','expected_age':14,
            'census_date':now,'regulation':'[MOCK] Rubricas por pontos; acompanhamento sem decisão automática.',
            'low_score':50,'attendance_alert':80})
        accounts=InstitutionalAccount.objects.filter(organization=organization,role='STUDENT',
            user__classroom_memberships__classroom_id=offer.classroom_id,user__classroom_memberships__status='ACTIVE')
        for publication in Publication.objects.filter(offer=offer):
            skill='MOCK-MAT-01' if publication.subject=='MATEMÁTICA' else 'MOCK-CIE-01'
            Curriculum.objects.get_or_create(offer=offer,subject=publication.subject,skill=skill,
                defaults={'description':'Aplicar o conceito em situação-problema','source':'[MOCK] Objetivo curricular local','is_demo':True})
            Curriculum.objects.get_or_create(offer=offer,subject=publication.subject,skill=skill+'-NA',
                defaults={'description':'Habilidade ainda não avaliada','source':'[MOCK] Currículo local','is_demo':True})
            for j,student in enumerate(accounts):
                prior=None
                for attempt in (1,2,3):
                    e,_=Evidence.objects.get_or_create(publication=publication,student=student,criterion='rubrica-demo',attempt=attempt,
                        defaults={'offer':offer,'subject':publication.subject,'skill':skill,'date':now-timedelta(days=30-attempt*7),
                            'score':min(10,attempt*3) if j%3==0 else 2,'maximum':10,'purpose':'recovery' if attempt==3 else 'regular',
                            'observation':'[MOCK] Resolução discursiva com rubrica de dez pontos.',
                            'snapshot':{'demo':True},'created_by':publication.teacher.user,'is_demo':True})
                    if attempt==1:prior=e
                if j%3!=0:
                    Intervention.objects.get_or_create(offer=offer,subject=publication.subject,student=student,skill=skill,
                        defaults={'difficulty':'[MOCK] Dificuldade persistente em aplicar conceitos','action':'Retomar exemplos e realizar prática orientada',
                            'responsible':publication.teacher,'starts_on':now-timedelta(days=20),'ends_on':now+timedelta(days=7),
                            'before':prior,'after':e,'outcome':'[MOCK] Reavaliar a estratégia; dificuldade persistente.','is_demo':True})
                for day in range(6):
                    Attendance.objects.get_or_create(offer=offer,subject=publication.subject,student=student,date=now-timedelta(days=6-day),
                        defaults={'hours':2,'present':0 if j%3==1 and day>2 else 2,'is_demo':True})
                Trajectory.objects.get_or_create(offer=offer,student=student,defaults={'outcome':'transferred' if j%7==0 else 'ongoing','is_demo':True})
        # Demonstration snapshots may be enriched only in this explicitly fictional institution.
        for run in ExamRun.objects.filter(classroom_id=offer.classroom_id):
            changed=False
            for q in run.questions:
                if 'diagnostic_metadata' not in q:
                    q['diagnostic_metadata']={'skills':['MOCK-MAT-01' if run.assessment.subject=='MATEMÁTICA' else 'MOCK-CIE-01'],
                        'alternatives':{'B':{'hypothesis':'[MOCK] Confusão entre operação e contexto','justification':'Distrator conceitual de demonstração','reviewed':True}}};changed=True
            if changed:run.save(update_fields=['questions'])
    OfficialResult.objects.get_or_create(organization=organization,indicator='ideb',year=now.year-1,stage='fundamental',area='Anos finais',is_demo=True,
        defaults={'inep_code':organization.school.inep_code,'value':5.8,'unit':'índice','status':'published',
            'source':'https://www.gov.br/inep','methodology':'[MOCK] Valor fictício para demonstrar importação; não é resultado publicado.', 'imported_by':administrator})
