import uuid
from django.db import models


class Conversation(models.Model):
    organization = models.ForeignKey('users_manager.Organization', on_delete=models.CASCADE)
    classroom = models.OneToOneField('users_manager.Classroom', on_delete=models.CASCADE, null=True, blank=True)
    first = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.CASCADE, null=True, blank=True, related_name='first_chats')
    second = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.CASCADE, null=True, blank=True, related_name='second_chats')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['first','second'],name='chat_unique_pair'),
            models.CheckConstraint(condition=(models.Q(classroom__isnull=False,first__isnull=True,second__isnull=True) |
                (models.Q(classroom__isnull=True,first__isnull=False,second__isnull=False) & models.Q(first__lt=models.F('second')))),name='chat_group_or_sorted_pair')]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT)
    body = models.TextField(max_length=4000)
    nonce = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']
        constraints = [models.UniqueConstraint(fields=['author','nonce'],name='chat_sender_nonce_unique')]


class ReadState(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    account = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.CASCADE)
    last_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['conversation','account'],name='chat_read_state_unique')]
