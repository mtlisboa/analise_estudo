import uuid
from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from features.users_manager.models import InstitutionalAccount
from features.notifications.services import notify_user
from ..views import institutional_identity
from .models import Conversation, Message, ReadState
from .services import classrooms, contacts, authorized, inbox, payload, title


class MessageForm(forms.Form):
    body = forms.CharField(max_length=4000,widget=forms.Textarea(attrs={'id':'chat-message-body','rows':2,'placeholder':'Escreva uma mensagem...'}),label='Mensagem')
    nonce = forms.UUIDField(initial=uuid.uuid4,widget=forms.HiddenInput(attrs={'id':'chat-message-nonce'}))


def data(account, selected=None, contact_query=''):
    return {**inbox(account,selected,contact_query),'message_form':MessageForm()}


def destination(request, account, conversation):
    from django.urls import reverse
    if room := request.POST.get('return_classroom'):
        try:
            room = int(room)
        except ValueError:
            return JsonResponse({'error':'Turma inválida.'},status=400)
        classroom = get_object_or_404(classrooms(account),pk=room)
        return redirect(reverse('institutions:classroom',args=[classroom.pk])+'?chat='+str(conversation.pk)+'#room-messages')
    from ..roles import workspace_for
    home = reverse('family:index') if account.role == 'GUARDIAN' else reverse('institutions:'+workspace_for(account).slug)
    if request.POST.get('return_home') == home:
        return redirect(home+'?chat='+str(conversation.pk)+'#communication')
    return redirect('communication:detail',pk=conversation.pk)


@login_required
@never_cache
@require_GET
def index(request, pk=None):
    account = institutional_identity(request.user)
    selected = authorized(account,pk) if pk is not None else None
    return render(request,'communication/index.html',data(account,selected,request.GET.get('contact_q','')))


@login_required
@require_POST
@transaction.atomic
def start(request, kind, pk):
    account = institutional_identity(request.user)
    if kind == 'grupo':
        classroom = get_object_or_404(classrooms(account),pk=pk)
        conversation,_ = Conversation.objects.get_or_create(classroom=classroom,
            defaults={'organization':account.organization})
    elif kind == 'direta':
        other = get_object_or_404(contacts(account),pk=pk)
        first,second = sorted([account.pk,other.pk])
        conversation,_ = Conversation.objects.get_or_create(first_id=first,second_id=second,
            defaults={'organization':account.organization})
    else:
        return JsonResponse({'error':'Conversa inválida.'},status=400)
    return destination(request,account,conversation)


@login_required
@require_POST
@transaction.atomic
def send(request, pk):
    account = institutional_identity(request.user)
    conversation = authorized(account,pk)
    form = MessageForm(request.POST)
    if not form.is_valid():
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error':'Escreva uma mensagem de até 4.000 caracteres.'},status=400)
        return render(request,'communication/index.html',{**data(account,conversation),'message_form':form},status=422)
    message,created = Message.objects.get_or_create(author=account,nonce=form.cleaned_data['nonce'],
        defaults={'conversation':conversation,'body':form.cleaned_data['body']})
    if message.conversation_id != conversation.pk or message.body != form.cleaned_data['body']:
        return JsonResponse({'error':'Identificador da mensagem já utilizado.'},status=409)
    if created:
        Conversation.objects.filter(pk=pk).update(updated_at=timezone.now())
        if conversation.classroom_id:
            recipients = InstitutionalAccount.objects.filter(organization=account.organization,user__is_active=True).filter(
                Q(role__in=['TEACHER','STUDENT'],user__classroom_memberships__classroom=conversation.classroom,
                  user__classroom_memberships__status='ACTIVE',user__classroom_memberships__role=F('role')) |
                Q(role='ADMIN',user_id=account.organization.owner_id)).exclude(pk=account.pk).distinct()
        else:
            recipients = InstitutionalAccount.objects.filter(pk=conversation.second_id if conversation.first_id==account.pk else conversation.first_id)
        notice_title = conversation.classroom.name if conversation.classroom_id else (account.user.get_full_name() or account.registration)
        for recipient in recipients:
            notify_user(recipient=recipient.user,title='Nova mensagem: '+notice_title[:100],message='Abra Comunicação para ler a mensagem.')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(payload(message,account),status=201 if created else 200)
    return destination(request,account,conversation)


@login_required
@never_cache
@require_GET
def updates(request, pk):
    account = institutional_identity(request.user)
    conversation = authorized(account,pk)
    try:
        after = max(0,int(request.GET.get('after','0')))
    except ValueError:
        return JsonResponse({'error':'Cursor inválido.'},status=400)
    if request.GET.get('before'):
        try:
            before = int(request.GET['before'])
        except ValueError:
            return JsonResponse({'error':'Cursor inválido.'},status=400)
        rows = list(conversation.messages.filter(pk__lt=before).select_related('author__user').order_by('-pk')[:50])
        rows.reverse()
        return JsonResponse({'messages':[payload(message,account) for message in rows],
            'has_older':bool(rows and conversation.messages.filter(pk__lt=rows[0].pk).exists())})
    rows = conversation.messages.filter(pk__gt=after).select_related('author__user')[:100]
    return JsonResponse({'messages':[payload(message,account) for message in rows]})


@login_required
@require_POST
@transaction.atomic
def read(request, pk):
    account = institutional_identity(request.user)
    conversation = authorized(account,pk)
    try:
        last = int(request.POST.get('last_id','0'))
    except ValueError:
        return JsonResponse({'error':'Mensagem inválida.'},status=400)
    if last < 0 or last > 9223372036854775807:
        return JsonResponse({'error':'Mensagem inválida.'},status=400)
    if last and not conversation.messages.filter(pk=last).exists():
        return JsonResponse({'error':'Mensagem não pertence à conversa.'},status=400)
    state,_ = ReadState.objects.get_or_create(conversation=conversation,account=account)
    ReadState.objects.filter(pk=state.pk,last_id__lt=last).update(last_id=last)
    return JsonResponse({'ok':True})
