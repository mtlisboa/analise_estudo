import uuid
from django.test import TestCase
from django.urls import reverse
from features.users_manager.models import ClassroomMembership, InstitutionalAccount
from features.notifications.models import Notification
from .models import Conversation, Message, ReadState


class CommunicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from features.accounts.tests.test_institutional_contexts import InstitutionalContextTests
        InstitutionalContextTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.teacher=self.users['TEACHER'].institutional_account
        self.student=self.users['STUDENT'].institutional_account
        self.client.force_login(self.student.user)

    def direct(self):
        response=self.client.post(reverse('communication:start',args=['direta',self.teacher.pk]))
        self.assertEqual(response.status_code,302)
        return Conversation.objects.get(classroom__isnull=True)

    def send(self,conversation,body='Olá professor',nonce=None):
        return self.client.post(reverse('communication:send',args=[conversation.pk]),
            {'body':body,'nonce':nonce or uuid.uuid4()},HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_private_messages_persist_and_retry_does_not_duplicate(self):
        conversation=self.direct()
        nonce=uuid.uuid4()
        self.assertEqual(self.send(conversation,nonce=nonce).status_code,201)
        self.assertEqual(self.send(conversation,nonce=nonce).status_code,200)
        self.assertEqual(Message.objects.count(),1)
        self.assertEqual(Notification.objects.filter(recipient=self.teacher.user).count(),1)
        self.client.force_login(self.teacher.user)
        response=self.client.get(reverse('communication:detail',args=[conversation.pk]))
        self.assertContains(response,'Olá professor')
        self.assertEqual(response.context['chat_conversations'][0].unread,1)
        message=Message.objects.get()
        self.assertEqual(self.client.post(reverse('communication:read',args=[conversation.pk]),{'last_id':message.pk}).status_code,200)
        response=self.client.get(reverse('communication:detail',args=[conversation.pk]))
        self.assertEqual(response.context['chat_conversations'][0].unread,0)

    def test_group_access_is_dynamic_and_notifies_current_participants(self):
        self.assertEqual(self.client.post(reverse('communication:start',args=['grupo',self.classroom.pk])).status_code,302)
        conversation=Conversation.objects.get(classroom=self.classroom)
        self.assertEqual(self.send(conversation,'Mensagem do grupo').status_code,201)
        self.client.force_login(self.teacher.user)
        self.assertContains(self.client.get(reverse('communication:detail',args=[conversation.pk])),'Mensagem do grupo')
        ClassroomMembership.objects.filter(classroom=self.classroom,user=self.teacher.user).update(status='REMOVED')
        self.assertEqual(self.client.get(reverse('communication:updates',args=[conversation.pk])).status_code,404)
        self.assertEqual(self.send(conversation).status_code,404)

    def test_cross_tenant_and_unrelated_users_cannot_start_or_read_conversations(self):
        conversation=self.direct()
        other=self.other.institutional_accounts.first()
        self.assertEqual(self.client.post(reverse('communication:start',args=['direta',other.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('communication:start',args=['grupo',self.other_classroom.pk])).status_code,404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('communication:detail',args=[conversation.pk])).status_code,404)
        self.client.force_login(self.users['GUARDIAN'])
        self.assertEqual(self.client.get(reverse('communication:detail',args=[conversation.pk])).status_code,404)
        self.assertEqual(self.send(conversation).status_code,404)
        other.user.must_change_password=False
        other.user.save(update_fields=['must_change_password'])
        self.client.force_login(other.user)
        self.assertEqual(self.client.get(reverse('communication:detail',args=[conversation.pk])).status_code,404)

    def test_home_and_room_embed_chat_and_allow_context_preserving_start(self):
        home=reverse('institutions:aluno')
        self.assertContains(self.client.get(home),'Comunicação')
        response=self.client.post(reverse('communication:start',args=['direta',self.teacher.pk]),{'return_home':home})
        conversation=Conversation.objects.get(classroom__isnull=True)
        self.assertEqual(response.url,home+'?chat='+str(conversation.pk)+'#communication')
        self.assertContains(self.client.get(home,{'chat':conversation.pk}),'chat-send')
        room=reverse('institutions:classroom',args=[self.classroom.pk])
        self.assertContains(self.client.get(room),'Conversar com o grupo')
        response=self.client.post(reverse('communication:start',args=['grupo',self.classroom.pk]),{'return_classroom':self.classroom.pk})
        group=Conversation.objects.get(classroom=self.classroom)
        self.assertEqual(response.url,room+'?chat='+str(group.pk)+'#room-messages')
        self.assertContains(self.client.get(room,{'chat':group.pk}),'data-chat-updates')

    def test_history_cursors_unread_and_no_cross_conversation_read_receipts(self):
        conversation=self.direct()
        Message.objects.bulk_create([Message(conversation=conversation,author=self.teacher,body=str(i)) for i in range(65)])
        response=self.client.get(reverse('communication:detail',args=[conversation.pk]))
        self.assertEqual(len(response.context['chat_messages']),50)
        oldest=response.context['chat_messages'][0].pk
        data=self.client.get(reverse('communication:updates',args=[conversation.pk]),{'before':oldest}).json()
        self.assertEqual(len(data['messages']),15)
        self.assertFalse(data['has_older'])
        last=conversation.messages.last().pk
        self.assertEqual(len(self.client.get(reverse('communication:updates',args=[conversation.pk]),{'after':last}).json()['messages']),0)
        self.client.post(reverse('communication:read',args=[conversation.pk]),{'last_id':last})
        self.client.post(reverse('communication:read',args=[conversation.pk]),{'last_id':oldest})
        self.assertEqual(ReadState.objects.get(account=self.student).last_id,last)
        self.assertEqual(self.client.post(reverse('communication:read',args=[conversation.pk]),{'last_id':last+999}).status_code,400)

    def test_validation_and_idempotency_conflict(self):
        conversation=self.direct()
        self.assertEqual(self.send(conversation,' ').status_code,400)
        self.assertEqual(self.send(conversation,'x'*4001).status_code,400)
        nonce=uuid.uuid4()
        self.send(conversation,nonce=nonce)
        self.client.post(reverse('communication:start',args=['grupo',self.classroom.pk]))
        group=Conversation.objects.get(classroom=self.classroom)
        self.assertEqual(self.send(group,nonce=nonce).status_code,409)
        self.assertEqual(group.messages.count(),0)

    def test_anonymous_and_read_endpoints_cannot_write(self):
        conversation=self.direct()
        self.assertEqual(self.client.get(reverse('communication:send',args=[conversation.pk])).status_code,405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('communication:index')).status_code,302)

    def test_guardian_only_contacts_linked_child_teachers_and_staff(self):
        from ..family.models import GuardianLink
        from features.accounts.institutional import provision_member
        guardian=self.users['GUARDIAN'].institutional_account
        GuardianLink.objects.create(guardian=guardian,student=self.student,is_active=True,
            relationship='Pai',created_by=self.admin)
        peer=provision_member(self.organization,self.admin,registration='colega',role='STUDENT',password='Initial-secret!92837')
        ClassroomMembership.objects.create(classroom=self.classroom,user=peer.user,role='STUDENT',status='ACTIVE',invited_by=self.admin)
        self.client.force_login(guardian.user)
        from .services import contacts
        self.assertTrue(contacts(guardian).filter(pk=self.teacher.pk).exists())
        self.assertFalse(contacts(guardian).filter(pk=peer.pk).exists())
        self.assertEqual(self.client.post(reverse('communication:start',args=['direta',peer.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('communication:start',args=['grupo',self.classroom.pk])).status_code,404)
        GuardianLink.objects.filter(guardian=guardian).update(is_active=False)
        self.assertFalse(contacts(guardian).filter(pk=self.teacher.pk).exists())

    def test_text_is_escaped_and_contact_search_is_scoped(self):
        conversation=self.direct()
        text='<script>alert(1)</script>'
        self.assertEqual(self.send(conversation,text).status_code,201)
        response=self.client.get(reverse('communication:detail',args=[conversation.pk]))
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,text)
        response=self.client.get(reverse('communication:index'),{'contact_q':'TEACHER'})
        self.assertEqual(list(response.context['chat_contacts'].values_list('pk',flat=True)),[self.teacher.pk])

    def test_csrf_required_for_message_mutations(self):
        from django.test import Client
        conversation=self.direct()
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.student.user)
        self.assertEqual(client.post(reverse('communication:send',args=[conversation.pk]),
            {'body':'Sem token','nonce':uuid.uuid4()}).status_code,403)
        self.assertEqual(Message.objects.count(),0)

    def test_room_excludes_general_contacts_and_rejects_outside_conversations(self):
        admin = self.admin.institutional_account
        self.client.post(reverse('communication:start', args=['direta', admin.pk]))
        outside = Conversation.objects.get(classroom__isnull=True)
        self.send(outside, 'Mensagem fora da turma')
        self.client.post(reverse('communication:start', args=['direta', self.teacher.pk]))
        room = reverse('institutions:classroom', args=[self.classroom.pk])
        response = self.client.get(room, {'chat': outside.pk})
        self.assertNotContains(response, 'Mensagem fora da turma')
        self.assertNotContains(response, 'Abrir central')
        self.assertNotContains(response, 'Nova conversa')
        self.assertNotContains(response, 'Buscar contato ou turma')
        self.assertNotIn(outside.pk, [row.pk for row in response.context['chat_conversations']])
        self.assertContains(self.client.get(reverse('institutions:aluno')), 'Abrir central')
        self.assertEqual(self.client.post(reverse('communication:start', args=['direta', admin.pk]),
            {'return_classroom': self.classroom.pk}).status_code, 404)
        self.assertEqual(self.client.post(reverse('communication:send', args=[outside.pk]),
            {'return_classroom': self.classroom.pk, 'body': 'Bloqueada', 'nonce': uuid.uuid4()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 404)
        self.assertEqual(outside.messages.count(), 1)

    def test_room_keeps_teacher_student_replies_and_rejects_other_groups(self):
        conversation = self.direct()
        room = reverse('institutions:classroom', args=[self.classroom.pk])
        self.send(conversation, 'Pergunta ao professor')
        self.assertContains(self.client.get(room, {'chat': conversation.pk}), 'Pergunta ao professor')
        self.client.force_login(self.teacher.user)
        self.assertContains(self.client.get(room, {'chat': conversation.pk}), 'Pergunta ao professor')
        self.assertEqual(self.client.post(reverse('communication:send', args=[conversation.pk]),
            {'return_classroom': self.classroom.pk, 'body': 'Resposta', 'nonce': uuid.uuid4()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 201)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('communication:start', args=['grupo', self.other_classroom.pk]),
            {'return_classroom': self.classroom.pk}).status_code, 404)
        self.assertFalse(Conversation.objects.filter(classroom=self.other_classroom).exists())
