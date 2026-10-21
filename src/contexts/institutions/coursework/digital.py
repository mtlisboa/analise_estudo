"""Digital delivery keeps question and option identities independent of display order."""
from copy import deepcopy
import random
import uuid


def option_ids(question):
    return [uuid.uuid5(uuid.NAMESPACE_URL, f'question:{question.pk}:option:{index}:{text}').hex
            for index, text in enumerate(question.options)]


def presentation(publication, student_id=None):
    content = deepcopy(publication.public_snapshot)
    rows = content.get('questions', [])
    rng = random.Random(f'virtual:{publication.pk}:{student_id}')
    configuration = publication.application_metadata
    for index, question in enumerate(rows):
        question['_field'] = f'q{index + 1}'
        ids = question.get('option_ids', [str(i) for i in range(len(question.get('options', [])))])
        pairs = list(zip(ids, question.get('options', [])))
        if configuration.get('virtual_shuffle_options'):
            rng.shuffle(pairs)
        question['_choices'] = [(identifier, f'{chr(65 + position)}) {text}')
                                for position, (identifier, text) in enumerate(pairs)]
        if pairs:
            if 'option_ids' in question:
                question['option_ids'] = [identifier for identifier, _ in pairs]
            question['options'] = [text for _, text in pairs]
    if configuration.get('virtual_shuffle_questions'):
        rng.shuffle(rows)
    return content
