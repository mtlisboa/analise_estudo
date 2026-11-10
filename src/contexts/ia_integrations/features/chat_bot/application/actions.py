"""Validate model suggestions, then save only an explicitly accepted proposal."""
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from features.assessments.models import Assessment, AssessmentTechnique, QuestionBankItem
from features.assessments.bank_access import available_questions
from features.assessments.services import _question_from_payload, add_bank_item_to_assessment


def text(value, limit, label):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValidationError(f'{label} inválido ou ausente.')
    return value.strip()


def question_payload(data):
    if not isinstance(data, dict):
        raise ValidationError('Questão inválida.')
    result = {key: text(data.get(key), limit, key) for key, limit in [('statement', 12000), ('correct_answer', 4000)]}
    result['question_type'] = data.get('question_type')
    if result['question_type'] not in ('multiple_choice', 'open_ended'):
        raise ValidationError('Tipo de questão inválido.')
    options = data.get('options', [])
    if not isinstance(options, list) or len(options) > 5:
        raise ValidationError('Use no máximo cinco alternativas.')
    result['options'] = [text(o, 2000, 'Alternativa') for o in options]
    if result['question_type'] == 'multiple_choice':
        if len(options) < 2 or len(set(result['options'])) != len(options) or result['correct_answer'] not in result['options']:
            raise ValidationError('Revise alternativas e gabarito.')
    elif options:
        raise ValidationError('Questões discursivas não usam alternativas.')
    for key in ('support_text', 'explanation'):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > 12000:
            raise ValidationError('Texto da questão inválido.')
        result[key] = value
    try:
        points = Decimal(str(data.get('points', 1)))
        if not points.is_finite() or not Decimal('.01') <= points <= Decimal('9999.99') or points.as_tuple().exponent < -2:
            raise ValueError
    except (ValueError, InvalidOperation):
        raise ValidationError('Pontuação inválida.')
    result['points'] = str(points)
    return result


def validate_proposal(user, proposal):
    if not user.is_active or getattr(user, 'must_change_password', False):
        raise ValidationError('Acesso indisponível.')
    if not isinstance(proposal, dict):
        raise ValidationError('Proposta inválida.')
    action = proposal.get('action')
    if action not in ('create_question', 'edit_question', 'create_questionnaire'):
        raise ValidationError('Ação não permitida.')
    result = {'action': action}
    if action == 'edit_question':
        if type(proposal.get('source_id')) is not int:
            raise ValidationError('Identificador de questão inválido.')
        source = QuestionBankItem.objects.filter(owner=user, pk=proposal.get('source_id'), is_active=True).first()
        if source is None:
            raise ValidationError('A questão não está disponível para edição.')
        if proposal.get('source_version') and proposal['source_version'] != source.updated_at.isoformat():
            raise ValidationError('A questão foi alterada. Solicite uma nova proposta.')
        result.update(source_id=source.pk, source_version=source.updated_at.isoformat(), subject=source.subject, topic=source.topic)
    else:
        result.update(subject=text(proposal.get('subject'), 120, 'Disciplina'), topic=text(proposal.get('topic'), 160, 'Assunto'))
    if action in ('create_question', 'edit_question'):
        result['question'] = question_payload(proposal.get('question'))
    else:
        questions = proposal.get('questions', [])
        ids = proposal.get('question_ids', [])
        if not isinstance(questions, list) or not isinstance(ids, list) or not 1 <= len(questions) + len(ids) <= 10:
            raise ValidationError('Selecione ou gere de 1 a 10 questões por proposta.')
        if any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
            raise ValidationError('Identificadores inválidos ou repetidos.')
        if available_questions(user).filter(pk__in=ids).count() != len(ids):
            raise ValidationError('Há questões fora do seu banco autorizado.')
        selected = list(available_questions(user).filter(pk__in=ids))
        versions = {str(q.pk): q.updated_at.isoformat() for q in selected}
        if proposal.get('question_versions') is not None and proposal['question_versions'] != versions:
            raise ValidationError('Uma questão selecionada foi alterada. Solicite uma nova proposta.')
        result.update(questions=[question_payload(q) for q in questions], question_ids=ids,
            question_versions=versions, selected_questions=[{'id': q.pk, 'statement': q.statement,
                'options': q.options, 'correct_answer': q.correct_answer, 'explanation': q.explanation,
                'support_text': q.support_text, 'points': str(q.default_points)} for q in selected])
    return result


@transaction.atomic
def execute_proposal(user, proposal):
    data = validate_proposal(user, proposal)
    action = data['action']
    source = None
    if action == 'edit_question':
        source = QuestionBankItem.objects.select_for_update().get(pk=data['source_id'], owner=user)
        if source.updated_at.isoformat() != data['source_version']:
            raise ValidationError('A questão foi alterada. Gere uma nova proposta.')
    if action != 'create_questionnaire':
        item = _question_from_payload(user, data['subject'], data['topic'], data['question'],
            method=QuestionBankItem.CreationMethod.AI_EDITED if source else QuestionBankItem.CreationMethod.AI_GENERATED, source=source)
        return {'message': 'Nova versão salva no banco.' if source else 'Questão salva no banco.',
                'url': reverse('assessments:bank-question-update', args=[item.pk])}
    technique = AssessmentTechnique.objects.order_by('pk').first()
    if not technique:
        raise ValidationError('Cadastre uma técnica avaliativa antes de montar o questionário.')
    assessment = Assessment(owner=user, subject=data['subject'], topic=data['topic'],
        technique=technique, kind='ACTIVITY', is_visible=False,
        desired_question_count=len(data['questions']) + len(data['question_ids']))
    assessment.full_clean()
    assessment.save()
    by_id = {q.pk: q for q in available_questions(user).filter(pk__in=data['question_ids'])}
    for pk in data['question_ids']:
        add_bank_item_to_assessment(assessment, by_id[pk])
    for payload in data['questions']:
        item = _question_from_payload(user, data['subject'], data['topic'], payload,
            method=QuestionBankItem.CreationMethod.AI_GENERATED)
        add_bank_item_to_assessment(assessment, item)
    assessment.has_open_questions = assessment.questions.filter(question_type='open_ended').exists()
    assessment.save(update_fields=['has_open_questions'])
    return {'message': 'Atividade salva como questionário privado. Revise antes de aplicar.',
            'url': reverse('assessments:questionnaire-edit', args=[assessment.pk])}
