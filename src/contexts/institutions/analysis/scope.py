from django.core.exceptions import PermissionDenied
from django.db.models import Q
from features.users_manager.models import InstitutionalAccount
from features.paper_exams.models import ExamRun
from ..views import institutional_identity
from ..planning.models import Offer
from ..coursework.services import teacher_disciplines

class Scope:
    def __init__(self, user):
        self.account = institutional_identity(user)
        self.user = user
        self.organization = self.account.organization
        self.manager = self.account.role in ('ADMIN', 'MANAGER')
        if not self.manager and self.account.role != 'TEACHER':
            raise PermissionDenied('Análise restrita à gestão e aos professores autorizados.')
        offers = Offer.objects.filter(period__organization=self.organization,
            classroom__organization=self.organization, classroom__is_active=True,
            period__published_at__isnull=False).select_related('period','classroom','analysis_context')
        if self.manager:
            self.pairs = [(o.pk, x['subject']) for o in offers for x in o.published_schedule if x.get('subject')]
        else:
            self.pairs = [(r['offer'].pk, r['subject']) for r in teacher_disciplines(self.account)]
        self.pairs = sorted(set(self.pairs))
        self.offers = offers.filter(pk__in=[o for o,s in self.pairs])
        self.students = InstitutionalAccount.objects.filter(organization=self.organization, role='STUDENT',
            user__classroom_memberships__classroom_id__in=self.offers.values('classroom_id'),
            user__classroom_memberships__role='STUDENT', user__classroom_memberships__status='ACTIVE').distinct()

    def query(self, offer='offer_id', subject='subject'):
        query = Q(pk__in=[])
        for oid, name in self.pairs:
            query |= Q(**{offer: oid, subject: name})
        return query

    def records(self, model):
        return model.objects.filter(self.query())

    def runs(self):
        query = Q(pk__in=[])
        rooms = dict(self.offers.values_list('pk','classroom_id'))
        for oid, name in self.pairs:
            if oid in rooms:
                query |= Q(classroom_id=rooms[oid], subject=name) | Q(classroom_id=rooms[oid], subject='', assessment__subject__iexact=name)
        qs = ExamRun.objects.filter(classroom__organization=self.organization, classroom__is_active=True) if self.manager else ExamRun.objects.filter(query, classroom__organization=self.organization)
        # Existing teacher analysis exposes only their own issued assessments.
        if not self.manager:
            qs = qs.filter(created_by=self.user, assessment__owner=self.user)
        return qs
