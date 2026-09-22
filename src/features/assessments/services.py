import json
from decimal import Decimal
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q

from contexts.ia_integrations.features.chat_bot.application.contracts import ChatRequest
from contexts.ia_integrations.features.chat_bot.infrastructure.mcp_agent_gateway import (
    McpAgentGateway,
)

from .models import Assessment, Question, QuestionBankItem


def request_ai_json(prompt, user_id):
    gateway = McpAgentGateway(
        server_url=settings.IA_MCP_SERVER_URL,
        tool_name=settings.IA_MCP_CHAT_TOOL,
        timeout_seconds=settings.IA_MCP_TIMEOUT_SECONDS,
    )
    response = async_to_sync(gateway.ask)(
        ChatRequest(
            message=prompt,
            conversation_id=str(uuid4()),
            user_id=str(user_id),
        )
    )
    content = response.message.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationError("A IA não retornou dados estruturados válidos.") from exc
    if not isinstance(payload, dict):
        raise ValidationError("A IA retornou um formato inesperado.")
    return payload


def _question_from_payload(owner, subject, topic, payload, *, method, source=None, prompt=""):
    if not isinstance(payload, dict):
        raise ValidationError("A IA retornou uma questão inválida.")
    item = QuestionBankItem(
        owner=owner,
        subject=subject,
        topic=topic,
        statement=str(payload.get("statement", "")).strip(),
        question_type=payload.get("question_type", Question.Type.MULTIPLE_CHOICE),
        options=payload.get("options") or [],
        correct_answer=str(payload.get("correct_answer", "")).strip(),
        explanation=str(payload.get("explanation", "")).strip(),
        default_points=Decimal(str(payload.get("points", "1"))),
        creation_method=method,
        source_question=source,
        ai_instructions=prompt,
    )
    item.full_clean()
    item.save()
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
    if item.owner_id != assessment.owner_id:
        raise ValidationError("A questão não pertence ao responsável pela avaliação.")
    existing = assessment.questions.filter(bank_item=item).first()
    if existing:
        return existing
    order = (assessment.questions.aggregate(last=Max("order"))["last"] or 0) + 1
    return Question.objects.create(
        assessment=assessment,
        bank_item=item,
        statement=item.statement,
        question_type=item.question_type,
        options=item.options,
        correct_answer=item.correct_answer,
        explanation=item.explanation,
        points=item.default_points,
        order=order,
    )


def assemble_assessment(assessment):
    method = assessment.assembly_method
    if method == Assessment.AssemblyMethod.MANUAL:
        assessment.assembly_status = Assessment.AssemblyStatus.DRAFT
        assessment.assembly_notes = "Aguardando seleção manual de questões."
        assessment.save(update_fields=("assembly_status", "assembly_notes", "updated_at"))
        return assessment

    candidates = QuestionBankItem.objects.filter(owner=assessment.owner, is_active=True).filter(
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
            try:
                ids = [int(item_id) for item_id in payload.get("question_ids", [])]
            except (TypeError, ValueError) as exc:
                raise ValidationError("A IA retornou identificadores de questões inválidos.") from exc
            selected_by_id = {item.pk: item for item in candidates.filter(pk__in=ids)}
            selected = [selected_by_id[item_id] for item_id in ids if item_id in selected_by_id][
                :count
            ]
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
            if not isinstance(question_payloads, list):
                raise ValidationError("A IA não retornou uma lista de questões.")
            selected = [
                _question_from_payload(
                    assessment.owner,
                    assessment.subject,
                    assessment.topic,
                    item,
                    method=QuestionBankItem.CreationMethod.AI_GENERATED,
                    prompt=assessment.generation_prompt,
                )
                for item in question_payloads[:count]
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
