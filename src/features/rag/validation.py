"""Provider-independent output checks; no network or database dependencies."""
from collections import Counter
from difflib import SequenceMatcher
import re
import json
import unicodedata
from .exceptions import InvalidGeneration

MAX_TEXT = 16000


def normalize(value):
    value = ''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'\w+', value))


def segments(text):
    for line in re.split(r'\n+|(?<=[.!?;])\s+', text):
        line = re.sub(r'^\s*(?:\d+[.)\-:]|[-*•])\s*', '', line)
        cleaned = normalize(line)
        if cleaned:
            yield cleaned


def validate_text(text):
    if not isinstance(text, str):
        raise InvalidGeneration('invalid_type')
    if len(text) > MAX_TEXT:
        raise InvalidGeneration('length')
    parts = [p for p in segments(text) if len(p) >= 32 and len(p.split()) >= 6]
    if any(count >= 3 for count in Counter(parts).values()):
        raise InvalidGeneration('repetition')
    # Catch small variations (numbers/punctuation/endings) without treating every
    # instruction beginning with "Clique" as an identical step.
    for i, part in enumerate(parts):
        neighbors = parts[max(0, i-10):i]
        if sum(SequenceMatcher(None, part[:500], p[:500], autojunk=False).ratio() >= .92
               for p in neighbors) >= 2:
            raise InvalidGeneration('repetition')
    # Also detect loops without punctuation or newlines. Count non-overlapping
    # occurrences so one repeated word in a normal sentence is not sufficient.
    words = normalize(text).split()
    positions = {}
    for i in range(max(0, len(words)-11)):
        key = tuple(words[i:i+12])
        previous = positions.setdefault(key, [])
        if not previous or i - previous[-1] >= 12:
            previous.append(i)
        if len(previous) >= 4:
            raise InvalidGeneration('repetition')


def validate_output(value):
    """Validate each generated text independently, preserving legitimate shared
    wording across separate questions. Validate before any proposal is accepted."""
    remaining = 1000
    def visit(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 12:
            raise InvalidGeneration('structure')
        if isinstance(item, str):
            validate_text(item)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child, depth+1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child, depth+1)
    visit(value)


def operational_request(query):
    text = normalize(query)
    help_request = re.search(r'\b(como|onde|passos?|tutorial|menu|botao|botoes)\b', text)
    app_topic = re.search(r'\b(atividade|atividades|questionario|questionarios|questao|questoes|aplicativo|lumini|avaliacao|avaliacoes|gabarito|gabaritos|turma|turmas|conta|contas)\b', text)
    return bool(help_request and app_topic)


def operational_answer(text):
    return bool(re.search(r'\b(clique|acesse|selecione|aperte|botao|menu|salvar questionario)\b', normalize(text)))


def validate_grounding(text, documents):
    """Conservative extractive policy for UI procedures, not a semantic fact checker.
    A paraphrase we cannot verify is replaced with the trusted source itself."""
    source_statements = [s for d in documents for s in segments(d['text'])]
    statements = list(segments(text))
    if not source_statements or not statements:
        raise InvalidGeneration('unsupported_procedure')
    cursor = 0
    for statement in statements:
        try:
            position = source_statements.index(statement, cursor)
        except ValueError:
            raise InvalidGeneration('unsupported_procedure') from None
        cursor = position + 1


def valid_history(text):
    try:
        try:
            value = json.loads(text) if text.lstrip().startswith('{') else text
        except ValueError:
            value = text
        validate_output(value)
        return True
    except (InvalidGeneration, TypeError, AttributeError):
        return False
