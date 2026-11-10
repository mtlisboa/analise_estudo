import uuid
from django.db import transaction
from contexts.ia_integrations.models import Conversation, ChatMessage


def load(user_id):
    conversation, _ = Conversation.objects.get_or_create(user_id=user_id)
    rows = list(conversation.messages.order_by('-id').values('id', 'role', 'content', 'metadata')[:200])
    return str(conversation.generation), list(reversed(rows))


@transaction.atomic
def append(user_id, generation, role, content, metadata=None):
    conversation = Conversation.objects.select_for_update().get(user_id=user_id)
    if str(conversation.generation) != generation:
        return False
    # Confirmation tokens are intentionally not replayable after reconnecting.
    metadata = {k: v for k, v in (metadata or {}).items() if k != 'confirmation_token'}
    ChatMessage.objects.create(conversation=conversation, role=role, content=content, metadata=metadata)
    return True


@transaction.atomic
def clear(user_id):
    conversation, _ = Conversation.objects.select_for_update().get_or_create(user_id=user_id)
    conversation.messages.all().delete()
    conversation.generation = uuid.uuid4()
    conversation.save(update_fields=['generation'])
    return str(conversation.generation)


def page(user_id, generation, before):
    return list(reversed(list(ChatMessage.objects.filter(conversation__user_id=user_id,
        conversation__generation=generation, id__lt=before).order_by('-id').values('id', 'role', 'content', 'metadata')[:200])))
