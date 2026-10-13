from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from features.users_manager.models import Classroom
from .planning.models import Offer
from .views import institutional_identity


@login_required
@never_cache
@require_GET
def index(request):
    account = institutional_identity(request.user)
    if account.role not in ('ADMIN', 'MANAGER', 'OPERATOR', 'TEACHER', 'STUDENT'):
        raise PermissionDenied
    rows = Classroom.objects.filter(organization=account.organization, is_active=True)
    if account.role in ('TEACHER', 'STUDENT'):
        rows = rows.filter(memberships__user=request.user, memberships__role=account.role,
                           memberships__status='ACTIVE').distinct()
    query = request.GET.get('q', '').strip()[:100]
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(letter__icontains=query))
    # Existing group records are internal to planning, never used as navigation.
    offers = Offer.objects.filter(period__published_at__isnull=False,
        period__organization=account.organization).select_related('period').order_by('-period__starts_on', '-pk')
    rows = rows.prefetch_related(Prefetch('planning_offer', queryset=offers, to_attr='room_offer'))
    return render(request, 'institutions/classrooms.html', {
        'institution': account.organization.school, 'identity': account, 'query': query,
        'classroom_page': Paginator(rows.order_by('name', 'pk'), 20).get_page(request.GET.get('page')),
        'can_plan': account.role in ('ADMIN', 'OPERATOR')})


@login_required
@never_cache
@require_GET
def detail(request, pk):
    institutional_identity(request.user)
    from features.users_manager.room import detail as room_detail
    return room_detail(request, pk)
