from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count, F, OuterRef, Subquery, Value, BigIntegerField
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from features.users_manager.models import Classroom, ClassroomMembership, InstitutionalAccount

from .models import Conversation, ReadState


def classrooms(account):
    rows = Classroom.objects.filter(organization=account.organization, is_active=True)
    if account.role == 'ADMIN' and account.organization.owner_id == account.user_id:
        return rows
    if account.role not in ('TEACHER','STUDENT'):
        return rows.none()
    return rows.filter(memberships__user=account.user, memberships__role=account.role,
        memberships__status='ACTIVE').distinct()


def contacts(account):
    rows = InstitutionalAccount.objects.filter(organization=account.organization,user__is_active=True).exclude(pk=account.pk)
    if account.role in ('ADMIN','MANAGER','OPERATOR'):
        return rows.select_related('user').order_by('user__first_name','pk')
    own_classes = classrooms(account)
    student_ids = ClassroomMembership.objects.filter(classroom__in=own_classes,role='STUDENT',status='ACTIVE',user__institutional_account__role='STUDENT',user__institutional_account__organization=account.organization).values_list('user_id',flat=True)
    from ..family.models import GuardianLink
    guardian_ids = GuardianLink.objects.filter(student__user_id__in=student_ids,is_active=True,
        student__organization=account.organization,guardian__organization=account.organization,student__role='STUDENT',guardian__role='GUARDIAN').values_list('guardian_id',flat=True)
    if account.role == 'GUARDIAN':
        child_ids = GuardianLink.objects.filter(guardian=account,is_active=True,student__role='STUDENT',
            student__organization=account.organization,student__user__is_active=True).values_list('student__user_id',flat=True)
        own_classes = Classroom.objects.filter(organization=account.organization,is_active=True,
            memberships__user_id__in=child_ids,memberships__role='STUDENT',memberships__status='ACTIVE')
    if account.role == 'GUARDIAN':
        return rows.filter(Q(role__in=['ADMIN','MANAGER','OPERATOR']) | Q(user_id__in=child_ids) | Q(role='TEACHER', user__classroom_memberships__classroom__in=own_classes, user__classroom_memberships__status='ACTIVE')).distinct().select_related('user').order_by('user__first_name','pk')
    return rows.filter(Q(role__in=['ADMIN','MANAGER','OPERATOR']) |
        Q(role__in=['TEACHER','STUDENT'],user__classroom_memberships__classroom__in=own_classes,
          user__classroom_memberships__status='ACTIVE',user__classroom_memberships__role=F('role')) |
        (Q(pk__in=guardian_ids) if account.role == 'TEACHER' else Q(pk__in=[]))).distinct().select_related('user').order_by('user__first_name','pk')


def visible(account):
    ids = contacts(account).values_list('pk',flat=True)
    states = ReadState.objects.filter(conversation=OuterRef('pk'),account=account).values('last_id')[:1]
    return Conversation.objects.filter(organization=account.organization).filter(
        Q(classroom__in=classrooms(account)) | Q(first=account,second_id__in=ids) |
        Q(second=account,first_id__in=ids)).select_related('classroom','first__user','second__user').annotate(
        last_seen=Coalesce(Subquery(states),Value(0),output_field=BigIntegerField())).annotate(unread=Count('messages',filter=
            Q(messages__pk__gt=F('last_seen')) & ~Q(messages__author=account)))


def authorized(account, pk):
    return get_object_or_404(visible(account),pk=pk)


def room_teachers(account, classroom):
    return contacts(account).filter(role='TEACHER',
        user__classroom_memberships__classroom=classroom,
        user__classroom_memberships__role='TEACHER',
        user__classroom_memberships__status='ACTIVE').distinct()


def room_conversations(account, classroom):
    teachers = room_teachers(account, classroom).values_list('pk', flat=True)
    private = Q(first=account, second_id__in=teachers) | Q(second=account, first_id__in=teachers)
    # A professor can also reply to private messages from this classroom's students.
    if classroom.memberships.filter(user=account.user, role='TEACHER', status='ACTIVE').exists() and account.role == 'TEACHER':
        students = contacts(account).filter(role='STUDENT',
            user__classroom_memberships__classroom=classroom,
            user__classroom_memberships__role='STUDENT',
            user__classroom_memberships__status='ACTIVE').values_list('pk', flat=True)
        private |= Q(first=account, second_id__in=students) | Q(second=account, first_id__in=students)
    return visible(account).filter(Q(classroom=classroom) | private)


def title(conversation, account):
    if conversation.classroom_id:
        return conversation.classroom.name + ' · Grupo da turma'
    other = conversation.second if conversation.first_id == account.pk else conversation.first
    return other.user.get_full_name() or other.registration


def payload(message, account):
    return {'id':message.pk,'body':message.body,'mine':message.author_id==account.pk,
        'author':message.author.user.get_full_name() or message.author.registration,
        'time':message.created_at.isoformat()}


def inbox(account, selected=None, contact_query=''):
    contact_query = contact_query.strip()[:100]
    people = contacts(account)
    groups = classrooms(account)
    if contact_query:
        people = people.filter(Q(user__first_name__icontains=contact_query)|Q(user__last_name__icontains=contact_query)|Q(registration__icontains=contact_query))
        groups = groups.filter(name__icontains=contact_query)
    conversations = list(visible(account)[:50])
    for row in conversations:
        row.chat_title = title(row,account)
    return {'chat_account':account,'chat_conversations':conversations,'chat_contacts':people[:100], 'chat_contact_query':contact_query,
        'chat_classrooms':groups[:100],'selected_chat':selected,
        'chat_messages':list(reversed(list(selected.messages.select_related('author__user').order_by('-pk')[:50]))) if selected else [],
        'chat_title':title(selected,account) if selected else '', 'has_older_messages':selected.messages.count()>50 if selected else False}
