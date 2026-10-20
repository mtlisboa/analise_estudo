"""Stable per-run booklet permutations and answer-key translations."""
import copy
import random
import unicodedata
from django.core.exceptions import ValidationError

LETTERS = 'ABCDE'


def make_variants(questions, seed, shuffle_questions=False, shuffle_options=False):
    variants, signatures, answer_keys = {}, set(), set()
    for version in 'ABC':
        for attempt in range(200):
            rng = random.Random(f'{seed}:{version}:{attempt}')
            closed = copy.deepcopy([q for q in questions if q.get('type') != 'open_ended'])
            opened = copy.deepcopy([q for q in questions if q.get('type') == 'open_ended'])
            if shuffle_questions:
                rng.shuffle(closed)
                rng.shuffle(opened)
            rows = closed + opened
            for question in rows:
                indices = list(range(len(question['options'])))
                if shuffle_options and indices:
                    rng.shuffle(indices)
                original_correct = question.get('correct', '')
                question['option_order'] = indices
                question['options'] = [question['options'][index] for index in indices]
                if original_correct:
                    question['correct'] = LETTERS[indices.index(LETTERS.index(original_correct))]
                metadata = question.get('diagnostic_metadata', {})
                old = metadata.get('alternatives', {})
                if old:
                    metadata['alternatives'] = {LETTERS[i]: old[LETTERS[source]] for i, source in enumerate(indices) if LETTERS[source] in old}
            signature = tuple((q['id'], tuple(q['options'])) for q in rows)
            answer_key = tuple(q.get('correct', '') for q in rows if q.get('type') != 'open_ended')
            if signature not in signatures and (not answer_key or answer_key not in answer_keys):
                variants[version] = rows
                signatures.add(signature)
                answer_keys.add(answer_key)
                break
        else:
            raise ValidationError('Não há combinações suficientes para três versões e gabaritos distintos. Ative os dois embaralhamentos ou adicione questões/alternativas.')
    return variants


def alphabetical_key(name):
    return ''.join(char for char in unicodedata.normalize('NFKD', name.casefold())
                   if not unicodedata.combining(char))


def assign_student_variants(members):
    """Sort the complete application roster, then assign A, B, C cyclically."""
    ordered = sorted(members, key=lambda member: (
        alphabetical_key(member.user.get_full_name() or member.user.username),
        member.user_id, member.classroom_id))
    return {(member.classroom_id, member.user_id): 'ABC'[index % 3]
            for index, member in enumerate(ordered)}
