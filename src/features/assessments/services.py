from .bank_access import available_questions
import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q

from .models import Assessment, Question, QuestionBankItem


def request_ai_json(prompt, user_id):
    from features.rag.bootstrap import complete
    return complete([
        {"role": "system", "content": "Você cria material pedagógico em português. Responda somente o objeto JSON solicitado, sem inventar IDs."},
        {"role": "user", "content": prompt},
    ], structured=True, user_id=user_id)


def _question_from_payload(owner, subject, topic, payload, *, method, source=None, prompt=""):
    if not isinstance(payload, dict):
        raise ValidationError("A IA retornou uma questão inválida.")
    from features.rag.infrastructure.actions import question_payload
    payload = question_payload(payload)
    item = QuestionBankItem(
        owner=owner,
        subject=subject,
        topic=topic,
        support_text=str(payload.get("support_text", source.support_text if source else "")).strip(),
        statement=str(payload.get("statement", "")).strip(),
        question_type=payload.get("question_type", Question.Type.MULTIPLE_CHOICE),
        options=payload.get("options") or [],
        correct_answer=str(payload.get("correct_answer", "")).strip(),
        explanation=str(payload.get("explanation", "")).strip(),
        default_points=Decimal(str(payload.get("points", "1"))),
        creation_method=method,
        source_question=source,
        assessment_method=source.assessment_method if source else '',
        metadata_tags=source.metadata_tags if source else [],
        ai_instructions=prompt,
    )
    item.full_clean()
    item.save()
    if source:
        item.images.set(source.images.all())
    return item


def generate_question_with_ai(owner, subject, topic, instructions):
    prompt = f"""
Crie uma questão educacional inédita de {subject}, assunto {topic}.
Instruções: {instructions}
Responda somente JSON no formato:
{{"statement":"...","question_type":"multiple_choice ou open_ended",\
"options":["..."],"correct_answer":"...","explanation":"...","points":1}}
Para múltipla escolha, use ao menos duas alternativas e faça correct_answer ser idêntica
a uma alternativa. Para discursiva, use options como lista vazia.
""".strip()
    payload = request_ai_json(prompt, owner.pk)
    return _question_from_payload(
        owner,
        subject,
        topic,
        payload,
        method=QuestionBankItem.CreationMethod.AI_GENERATED,
        prompt=instructions,
    )


def edit_question_with_ai(source, instructions):
    prompt = f"""
Edite a questão abaixo sem perder sua finalidade pedagógica.
Matéria: {source.subject}. Assunto: {source.topic}.
Pedido de edição: {instructions}
Questão atual: {json.dumps({
    "support_text": source.support_text,
    "statement": source.statement,
    "question_type": source.question_type,
    "options": source.options,
    "correct_answer": source.correct_answer,
    "explanation": source.explanation,
    "points": str(source.default_points),
}, ensure_ascii=False)}
Responda somente JSON com statement, question_type, options, correct_answer,
explanation e points.
""".strip()
    payload = request_ai_json(prompt, source.owner_id)
    return _question_from_payload(
        source.owner,
        source.subject,
        source.topic,
        payload,
        method=QuestionBankItem.CreationMethod.AI_EDITED,
        source=source,
        prompt=instructions,
    )


@transaction.atomic
def add_bank_item_to_assessment(assessment, item):
    if not available_questions(assessment.owner).filter(pk=item.pk).exists():
        raise ValidationError("A questão não está disponível para o responsável pela avaliação.")
    existing = assessment.questions.filter(bank_item=item).first()
    if existing:
        return existing
    order = (assessment.questions.aggregate(last=Max("order"))["last"] or 0) + 1
    question = Question.objects.create(
        assessment=assessment,
        bank_item=item,
        support_text=item.support_text,
        content_blocks=item.content_blocks,
        answer_lines=item.answer_lines,
        assessment_method=item.assessment_method,
        metadata_tags=item.metadata_tags,
        statement=item.statement,
        question_type=item.question_type,
        options=item.options,
        diagnostic_metadata=item.diagnostic_metadata,
        correct_answer=item.correct_answer,
        explanation=item.explanation,
        points=item.default_points,
        order=order,
    )
    question.images.set(item.images.all())
    return question


def assemble_assessment(assessment):
    method = assessment.assembly_method
    if method == Assessment.AssemblyMethod.MANUAL:
        assessment.assembly_status = Assessment.AssemblyStatus.DRAFT
        assessment.assembly_notes = "Aguardando seleção manual de questões."
        assessment.save(update_fields=("assembly_status", "assembly_notes", "updated_at"))
        return assessment

    candidates = available_questions(assessment.owner).filter(
        Q(subject__iexact=assessment.subject) | Q(topic__icontains=assessment.topic)
    )
    count = assessment.desired_question_count
    try:
        if method == Assessment.AssemblyMethod.ALGORITHMIC:
            selected = list(
                candidates.annotate(usage_count=Count("assessment_copies")).order_by(
                    "usage_count", "-updated_at"
                )[:count]
            )
        elif method == Assessment.AssemblyMethod.AI_CURATED:
            catalog = [
                {"id": item.pk, "statement": item.statement, "type": item.question_type}
                for item in candidates[:100]
            ]
            payload = request_ai_json(
                f"Selecione {count} questões para uma avaliação de {assessment.subject}, "
                f"assunto {assessment.topic}. Critérios: {assessment.generation_prompt}. "
                f"Banco: {json.dumps(catalog, ensure_ascii=False)}. "
                'Responda somente JSON como {"question_ids":[1,2]}.',
                assessment.owner_id,
            )
            ids = payload.get("question_ids")
            allowed = {item['id'] for item in catalog}
            if not isinstance(ids, list) or len(ids) != count or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids) or not set(ids) <= allowed:
                raise ValidationError("A IA deve selecionar a quantidade solicitada, sem repetir ou inventar questões.")
            selected_by_id = {item.pk: item for item in candidates.filter(pk__in=ids)}
            selected = [selected_by_id[item_id] for item_id in ids]
        else:
            payload = request_ai_json(
                f"Crie {count} questões para uma avaliação de {assessment.subject}, assunto "
                f"{assessment.topic}. Instruções: {assessment.generation_prompt}. "
                'Responda somente JSON como {"questions":[{"statement":"...",'
                '"question_type":"multiple_choice","options":["A","B"],'
                '"correct_answer":"A","explanation":"...","points":1}]}.',
                assessment.owner_id,
            )
            question_payloads = payload.get("questions", [])
            if not isinstance(question_payloads, list) or len(question_payloads) != count:
                raise ValidationError("A IA não retornou uma lista de questões.")
            selected = None
        with transaction.atomic():
            if selected is None:
                selected = [
                    _question_from_payload(assessment.owner, assessment.subject, assessment.topic, item,
                        method=QuestionBankItem.CreationMethod.AI_GENERATED, prompt=assessment.generation_prompt)
                    for item in question_payloads
                ]
            if not selected:
                raise ValidationError("Nenhuma questão compatível foi encontrada ou gerada.")
            for item in selected:
                add_bank_item_to_assessment(assessment, item)
            assessment.assembly_status = Assessment.AssemblyStatus.READY
            assessment.assembly_notes = f"{len(selected)} questão(ões) adicionada(s)."
    except Exception as exc:
        assessment.assembly_status = Assessment.AssemblyStatus.FAILED
        assessment.assembly_notes = str(exc)
        assessment.save(update_fields=("assembly_status", "assembly_notes", "updated_at"))
        raise
    assessment.save(update_fields=("assembly_status", "assembly_notes", "updated_at"))
    return assessment
