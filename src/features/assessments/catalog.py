"""Offline, idempotent provisioning of the attributed MATH-PT catalog."""
import hashlib
import json
from pathlib import Path
from django.db import transaction
from .models import QuestionBankItem

SOURCE = 'https://huggingface.co/datasets/tiagoteixeira03/MATH-PT'
DATA_FILE = Path(__file__).parent / 'data' / 'math_pt_br_multiple_choice.json'


@transaction.atomic
def import_math_catalog(organization):
    rows = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    created = 0
    for row in rows:
        choices = row['choices']
        options = [f'{letter}) {text}' for letter, text in choices.items()]
        answer = f"{row['answer']}) {choices[row['answer']]}"
        key = 'math-pt:mc:' + hashlib.sha256(row['problem'].encode()).hexdigest()
        item = QuestionBankItem(
            organization=organization, owner_id=organization.owner_id,
            source_key=key, source_url=SOURCE,
            source_metadata={'dataset': 'MATH-PT', 'split': 'ptbr_multiple_choice_test',
                             'level': row.get('level'), 'license': 'MIT', 'reviewed': False},
            subject='Matemática', topic='MATH-PT · Problemas de competições',
            statement=row['problem'], options=options, correct_answer=answer,
            creation_method=QuestionBankItem.CreationMethod.IMPORTED,
        )
        # Validate content even when an earlier import already exists.
        item.clean()
        _, added = QuestionBankItem.objects.get_or_create(
            organization=organization, source_key=key,
            defaults={field.attname: getattr(item, field.attname)
                      for field in item._meta.fields
                      if field.name not in ('id', 'organization', 'source_key', 'created_at', 'updated_at')},
        )
        created += added
    return created
