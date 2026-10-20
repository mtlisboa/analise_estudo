"""Validate application-specific scores without changing authored questions."""
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError


def application_points(questions, overrides=None):
    if overrides is not None and set(overrides) != {str(q.pk) for q in questions}:
        raise ValidationError('As questões foram alteradas. Recarregue a aplicação e confira a pontuação.')
    result = {}
    for question in questions:
        try:
            value = Decimal(str(overrides[str(question.pk)] if overrides is not None else question.points))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError('Pontuação inválida.')
        if not value.is_finite() or value <= 0 or value > Decimal('999999.99') or value.as_tuple().exponent < -2:
            raise ValidationError('Cada questão deve ter pontuação positiva com até duas casas decimais.')
        result[str(question.pk)] = str(value)
    return result
