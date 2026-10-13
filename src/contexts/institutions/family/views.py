from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, FloatField, Q, Value
from django.db.models.functions import Cast
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from features.notifications.models import Notification
from features.notifications.services import notify_user
from features.paper_exams.models import SheetResult
from ..roles import workspace_for
from ..student import enrolled_classrooms, enrolled_subjects
from ..views import institutional_identity
from .forms import EventForm, LinkForm, PerformanceFilterForm, ReplyForm, RequestForm
from .models import FamilyRequest, GuardianLink, RequestMessage, SchoolEvent
from .services import family_requests, linked_children, notify_event, notify_staff

MODULES = [('inicio', 'Meus filhos'), ('desempenho', 'Desempenho'), ('grade', 'Grade de aulas'),
           ('eventos', 'Eventos'), ('contato', 'Contatar instituição'), ('documentos', 'Solicitar documentos'),
           ('notificacoes', 'Notificações')]


def identity(request, staff=False):
    account = institutional_identity(request.user)
    if account.role not in (('ADMIN', 'MANAGER', 'OPERATOR') if staff else ('GUARDIAN',)):
        raise PermissionDenied('Este perfil não tem acesso a esta área.')
    return account


def base_data(account):
    return {'identity': account, 'organization': account.organization, 'institution': account.organization.school,
            'workspace': workspace_for(account), 'family_modules': MODULES}


def child_selection(request, account):
    children = linked_children(account)
    selected = None
    value = request.GET.get('child', '')
    if value:
        try:
            selected = get_object_or_404(children, pk=int(value))
        except ValueError:
            raise Http404
        children = children.filter(pk=selected.pk)
    return linked_children(account), children, selected


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def portal(request, module='inicio'):
    account = identity(request)
    if module not in dict(MODULES):
        raise Http404
    if request.method == 'POST' and module not in ('contato', 'documentos'):
        return HttpResponseNotAllowed(['GET'])
    all_children, children, selected = child_selection(request, account)
    data = {**base_data(account), 'module': module, 'children': all_children, 'selected_child': selected,
            'page_title': dict(MODULES)[module], 'metrics': [('Filhos vinculados', all_children.count())]}
    if module == 'inicio':
        data['child_rows'] = [{'child': child, 'classrooms': enrolled_classrooms(child)} for child in children]
    elif module == 'desempenho':
        results = SheetResult.objects.filter(sheet__student_id__in=children.values('user_id'),
            sheet__run__classroom__organization=account.organization,
            status=SheetResult.Status.GRADED, score__isnull=False, maximum_score__gt=0)
        filters = PerformanceFilterForm(request.GET)
        data['filters'] = filters
        if filters.is_valid():
            if filters.cleaned_data['starts_on']:
                results = results.filter(created_at__date__gte=filters.cleaned_data['starts_on'])
            if filters.cleaned_data['ends_on']:
                results = results.filter(created_at__date__lte=filters.cleaned_data['ends_on'])
            if filters.cleaned_data['subject']:
                results = results.filter(sheet__run__assessment__subject__icontains=filters.cleaned_data['subject'])
        else:
            results = results.none()
        percentage = Cast('score', FloatField()) * Value(100.0) / Cast('maximum_score', FloatField())
        average = results.aggregate(value=Avg(percentage))['value']
        data['metrics'] += [('Provas corrigidas', results.count()),
            ('Aproveitamento médio', f'{average:.1f}%' if average is not None else '—')]
        data['subject_summary'] = results.order_by().values('sheet__student__first_name',
            'sheet__student__last_name', 'sheet__student__username', 'sheet__run__assessment__subject').annotate(
                average=Avg(percentage), total=Count('pk')).order_by('sheet__student__first_name', 'sheet__run__assessment__subject')
        data['result_page'] = Paginator(results.annotate(percentage=percentage).select_related(
            'sheet__student', 'sheet__run__classroom').order_by('-created_at', '-pk'), 20).get_page(request.GET.get('page'))
    elif module == 'grade':
        data['child_grades'] = [{'child': child, 'subjects': enrolled_subjects(child)} for child in children]
    elif module == 'eventos':
        classroom_ids = set()
        for child in children:
            classroom_ids.update(enrolled_classrooms(child).values_list('pk', flat=True))
        events = SchoolEvent.objects.filter(organization=account.organization, is_published=True)
        # Without any verified children, no institutional events are exposed.
        events = events.filter(Q(classroom__isnull=True) | Q(classroom_id__in=classroom_ids)) if children.exists() else events.none()
        if request.GET.get('past') == '1':
            events = events.filter(ends_at__lt=timezone.now()).order_by('-starts_at')
            data['past'] = True
        else:
            events = events.filter(ends_at__gte=timezone.now())
        data['event_page'] = Paginator(events.select_related('classroom'), 20).get_page(request.GET.get('page'))
    elif module in ('contato', 'documentos'):
        kind = 'DOCUMENT' if module == 'documentos' else 'CONTACT'
        ticket = FamilyRequest(organization=account.organization, guardian=account, kind=kind)
        form = RequestForm(request.POST if request.method == 'POST' else None, children=all_children, instance=ticket, initial={'student': selected.pk if selected else None})
        if request.method == 'POST' and form.is_valid():
            with transaction.atomic():
                obj = form.save()
                notify_staff(account.organization, 'Nova solicitação de responsável', f'{obj.title} · Protocolo {obj.protocol}')
            messages.success(request, 'Solicitação registrada. Acompanhe o protocolo e as respostas nesta área.')
            return redirect('family:request', pk=obj.pk)
        data['form'] = form
        rows = family_requests(account).filter(kind=kind)
        if selected:
            rows = rows.filter(student=selected)
        data['request_page'] = Paginator(rows, 20).get_page(request.GET.get('page'))
    elif module == 'notificacoes':
        data['notification_page'] = Paginator(Notification.objects.filter(recipient=request.user), 20).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    data['page_query'] = query.urlencode()
    return render(request, 'family/portal.html', data)


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def request_detail(request, pk):
    account = institutional_identity(request.user)
    staff = account.role in ('ADMIN', 'MANAGER', 'OPERATOR')
    if not staff and account.role != 'GUARDIAN':
        raise PermissionDenied
    ticket = get_object_or_404(family_requests(account, staff=staff), pk=pk)
    form = ReplyForm(request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None, initial={'status': ticket.status})
    if not staff:
        form.fields.pop('status')
        form.fields.pop('attachment')
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            # Scope and recheck on write as well as read.
            ticket = get_object_or_404(family_requests(account, staff=staff).select_for_update(), pk=pk)
            RequestMessage.objects.create(request=ticket, author=request.user, text=form.cleaned_data['text'],
                attachment=form.cleaned_data.get('attachment', ''))
            ticket.status = form.cleaned_data['status'] if staff else FamilyRequest.Status.OPEN
            ticket.save(update_fields=['status', 'updated_at'])
            if staff:
                # Do not deliver student-specific notifications after a revoked link.
                if ticket.student_id is None or linked_children(ticket.guardian).filter(pk=ticket.student_id).exists():
                    notify_user(recipient=ticket.guardian.user, title='Resposta da instituição',
                        message=f'{ticket.title} · {ticket.get_status_display()} · Protocolo {ticket.protocol}')
            else:
                notify_staff(account.organization, 'Nova mensagem de responsável', f'Protocolo {ticket.protocol}')
        return redirect('family:request', pk=pk)
    return render(request, 'family/request.html', {**base_data(account), 'ticket': ticket, 'form': form,
        'staff': staff, 'thread': ticket.messages.select_related('author'), 'page_title': ticket.title})


@login_required
@never_cache
@require_http_methods(['GET'])
def attachment(request, pk):
    account = institutional_identity(request.user)
    staff = account.role in ('ADMIN', 'MANAGER', 'OPERATOR')
    if not staff and account.role != 'GUARDIAN':
        raise PermissionDenied
    message = get_object_or_404(RequestMessage, pk=pk, request__in=family_requests(account, staff=staff))
    if not message.attachment:
        raise Http404
    try:
        response = FileResponse(message.attachment.open('rb'), as_attachment=True, filename=f'documento-{message.request.protocol}.pdf', content_type='application/pdf')
    except FileNotFoundError:
        raise Http404
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@never_cache
@require_POST
def read_notification(request, pk):
    identity(request)
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=['read_at'])
    return redirect('family:module', module='notificacoes')


@login_required
@never_cache
@require_http_methods(['GET'])
def desk(request):
    account = identity(request, staff=True)
    return render(request, 'family/desk.html', {**base_data(account), 'page_title': 'Famílias e atendimento',
        'request_page': Paginator(family_requests(account, staff=True), 20).get_page(request.GET.get('page')),
        'links': GuardianLink.objects.filter(guardian__organization=account.organization).select_related('guardian__user', 'student__user'),
        'events': SchoolEvent.objects.filter(organization=account.organization)})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def edit_link(request, pk=None):
    account = identity(request, staff=True)
    obj = get_object_or_404(GuardianLink, pk=pk, guardian__organization=account.organization) if pk else GuardianLink(created_by=request.user)
    form = LinkForm(request.POST if request.method == 'POST' else None, account=account, instance=obj)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
        return redirect('family:desk')
    return render(request, 'family/form.html', {**base_data(account), 'form': form, 'page_title': 'Vincular responsável e aluno'})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def edit_event(request, pk=None):
    account = identity(request, staff=True)
    obj = get_object_or_404(SchoolEvent, pk=pk, organization=account.organization) if pk else SchoolEvent(organization=account.organization, created_by=request.user)
    form = EventForm(request.POST if request.method == 'POST' else None, account=account, instance=obj)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            event = form.save()
            if event.is_published and form.has_changed():
                notify_event(event)
        return redirect('family:desk')
    return render(request, 'family/form.html', {**base_data(account), 'form': form, 'page_title': 'Evento institucional'})
