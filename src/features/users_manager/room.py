"""Classroom room: published coursework, cover and a shared notice hub."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from features.assessments.image_forms import MultipleImageField
from contexts.institutions.planning.models import Offer
from contexts.institutions.coursework.models import Publication
from .models import Classroom, ClassroomNotice, MembershipStatus
from .permissions import can_view_classroom, can_manage_classroom


class CoverForm(forms.Form):
    image = forms.FileField(label='Imagem da sala', required=False,
        widget=forms.FileInput(attrs={'accept': 'image/png,image/jpeg,image/webp'}),
        help_text='PNG, JPEG ou WebP, até 2 MB. Prefira uma imagem horizontal.')
    description = forms.CharField(label='Descrição da imagem', max_length=300, required=False)
    remove = forms.BooleanField(label='Remover a imagem atual', required=False)

    def clean_image(self):
        value = self.cleaned_data.get('image')
        return MultipleImageField().clean(value)[0] if value else None

    def clean(self):
        data = super().clean()
        if data.get('image') and data.get('remove'):
            self.add_error('remove', 'Escolha enviar uma imagem ou remover a atual.')
        return data


class NoticeForm(forms.ModelForm):
    class Meta:
        model = ClassroomNotice
        fields = ['title', 'body']
        widgets = {'body': forms.Textarea(attrs={'rows': 4})}


def authorized_classroom(request, pk, *, write=False):
    classroom = get_object_or_404(Classroom.objects.select_related('organization', 'group'),
        pk=pk, is_active=True, organization__is_active=True)
    identity = getattr(request.user, 'institutional_account', None)
    if identity and identity.organization_id != classroom.organization_id:
        raise PermissionDenied('Esta sala pertence a outra instituição.')
    institutional_read = identity and identity.role in ('ADMIN', 'MANAGER', 'OPERATOR')
    allowed = can_manage_classroom(request.user, classroom) if write else (institutional_read or can_view_classroom(request.user, classroom))
    if write and identity and identity.role not in ('ADMIN', 'TEACHER'):
        allowed = False
    if not allowed:
        raise PermissionDenied('Você não possui acesso a esta sala.')
    return classroom


def room_url(request, pk):
    name = 'institutions:classroom' if getattr(request.user, 'institutional_account', None) else 'users-manager:classroom-detail'
    return reverse(name, args=[pk])


def room_data(request, classroom):
    offers = list(Offer.objects.filter(classroom=classroom, period__organization=classroom.organization,
        period__published_at__isnull=False).select_related('period').order_by('-period__starts_on', '-pk'))
    today = timezone.localdate()
    selected = next((o for o in offers if o.period.starts_on <= today <= o.period.ends_on), offers[0] if offers else None)
    if code := request.GET.get('offer'):
        selected = next((o for o in offers if str(o.code) == code), None)
        if selected is None:
            raise Http404('Oferta não encontrada nesta sala.')
    subjects = sorted({lesson['subject'] for lesson in selected.published_schedule}) if selected else []
    publications = list(Publication.objects.filter(offer=selected, is_published=True, subject__in=subjects)
        .select_related('teacher__user').order_by('-published_at', '-pk')) if selected else []
    items = [{'publication': p, 'title': p.visible_title, 'kind': p.public_snapshot.get('kind_label', ''),
              'due_at': p.visible_due_at, 'url': reverse('coursework:student-detail', args=[p.pk])}
             for p in publications]
    identity = getattr(request.user, 'institutional_account', None)
    for item in items:
        p = item['publication']
        if not identity or identity.role != 'STUDENT':
            item['url'] = reverse('coursework:edit', args=[p.pk]) if identity and identity.pk == p.teacher_id else ''
    now = timezone.now()
    available_exams = [item for item in items if item['kind'] == 'Prova'
                       and (item['due_at'] is None or item['due_at'] >= now)]
    available_exams.sort(key=lambda item: (item['due_at'] is None, item['due_at'] or now))
    manage = can_manage_classroom(request.user, classroom) and (not identity or identity.role in ('ADMIN', 'TEACHER'))
    directories = []
    for subject in subjects:
        folder = {'name': subject, 'items': [item for item in items if item['publication'].subject == subject]}
        if identity and identity.role == 'TEACHER' and any(lesson['subject'] == subject and lesson['teacher_id'] == identity.pk
                for lesson in selected.published_schedule):
            folder['create_url'] = reverse('coursework:create', args=[selected.code, subject])
        directories.append(folder)
    notices = classroom.notices.filter(is_active=True).select_related('author')
    return {'is_classroom_environment': True, 'institutional_room': identity is not None, 'classroom': classroom, 'offers': offers, 'selected_offer': selected,
        'can_manage': manage, 'memberships': classroom.memberships.select_related('user', 'invited_by'),
        'tests': classroom.tests.all() if manage else classroom.tests.filter(is_published=True),
        'notices': list(notices[:3]), 'notice_count': notices.count(),
        'notice_page': Paginator(notices, 20).get_page(request.GET.get('notices_page')),
        'notice_form': NoticeForm(), 'cover_form': CoverForm(initial={'description': classroom.cover_description}),
        'available_exams': available_exams, 'agenda_items': sorted([i for i in items if i['due_at']], key=lambda i: i['due_at']), 'directories': directories, 'recent_activities': items[:5]}


def detail(request, pk, *, cover_form=None, notice_form=None, status=200):
    classroom = authorized_classroom(request, pk)
    data = room_data(request, classroom)
    if cover_form is not None:
        data['cover_form'] = cover_form
    if notice_form is not None:
        data['notice_form'] = notice_form
    return render(request, 'users_manager/classroom_detail.html', data, status=status)


@login_required
@never_cache
@require_GET
def cover(request, pk):
    classroom = authorized_classroom(request, pk)
    if not classroom.cover_image:
        raise Http404
    try:
        response = FileResponse(classroom.cover_image.open('rb'), content_type='image/png')
    except OSError:
        raise Http404
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_POST
def update_cover(request, pk):
    classroom = authorized_classroom(request, pk, write=True)
    form = CoverForm(request.POST, request.FILES)
    if not form.is_valid():
        return detail(request, pk, cover_form=form, status=422)
    if form.cleaned_data['remove']:
        classroom.cover_image = ''
    elif form.cleaned_data['image']:
        classroom.cover_image = form.cleaned_data['image']
    classroom.cover_description = form.cleaned_data['description']
    classroom.save(update_fields=['cover_image', 'cover_description'])
    messages.success(request, 'Imagem da sala atualizada.')
    return redirect(room_url(request, pk))


@login_required
@require_POST
@transaction.atomic
def add_notice(request, pk):
    classroom = authorized_classroom(request, pk, write=True)
    form = NoticeForm(request.POST)
    if not form.is_valid():
        return detail(request, pk, notice_form=form, status=422)
    notice = form.save(commit=False)
    notice.classroom = classroom
    notice.author = request.user
    notice.save()
    from features.notifications.services import notify_user
    members = classroom.memberships.filter(status=MembershipStatus.ACTIVE, user__is_active=True).exclude(user=request.user).select_related('user')
    for member in members:
        notify_user(recipient=member.user, title=f'Aviso na sala: {notice.title}', message=classroom.name)
    messages.success(request, 'Aviso publicado no hub da sala.')
    return redirect(room_url(request, pk) + '#room-notices')


@login_required
@require_POST
def withdraw_notice(request, pk, notice_pk):
    classroom = authorized_classroom(request, pk, write=True)
    notice = get_object_or_404(ClassroomNotice, pk=notice_pk, classroom=classroom, is_active=True)
    notice.is_active = False
    notice.save(update_fields=['is_active'])
    messages.success(request, 'Aviso retirado do hub.')
    return redirect(room_url(request, pk) + '#room-notices')
