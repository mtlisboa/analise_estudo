"""Server-owned knowledge retrieval and access-scoped application data."""
import re
from pathlib import Path
from django.conf import settings
from django.core.exceptions import PermissionDenied
from features.assessments.bank_access import available_questions
from features.assessments.models import Assessment
from features.users_manager.models import SelfAssessment


def documentation(query):
    path = Path(settings.BASE_DIR) / 'contexts/ia_integrations/knowledge/manual.md'
    sections = path.read_text(encoding='utf-8').split('\n## ')
    terms = set(re.findall(r'\w{3,}', query.lower()))
    ranked = sorted(enumerate(sections), key=lambda pair: sum(t in pair[1].lower() for t in terms), reverse=True)
    return [{'source': 'Manual Lumini — ' + text.splitlines()[0].lstrip('# '), 'text': text[:3000]}
            for _, text in ranked[:4]]


def user_context(user):
    from contexts.institutions.coursework.models import Submission
    data = {'user_id': user.pk, 'results': list(Submission.objects.filter(student=user, reviewed_at__isnull=False).values(
        'publication__title', 'score', 'maximum_score', 'feedback', 'submitted_at').order_by('-submitted_at')[:30]),
        'self_assessments': list(SelfAssessment.objects.filter(user=user).values(
        'focus', 'organization', 'comprehension', 'motivation', 'created_at')[:10]),
        'questionnaires': list(Assessment.objects.filter(owner=user).values('id', 'subject', 'topic', 'assembly_status')[:30]),
        'questions': list(available_questions(user).values('id', 'subject', 'topic', 'statement', 'owner_id', 'updated_at')[:30]),
        'limits': 'Catálogos, alunos e resultados limitados a 30 registros; autoavaliações a 10; evolução às últimas 30 datas. Enunciados do catálogo são abreviados; consulte a questão para ler tudo.'}
    for row in data['questions']:
        row['statement'] = row['statement'][:800]
    for row in data['results']:
        row['feedback'] = row['feedback'][:1000]
    try:
        from contexts.institutions.analysis.scope import Scope
        from contexts.institutions.analysis.services import build
        scope = Scope(user)
    except PermissionDenied:
        data['institutional_analysis'] = 'Sem acesso à análise institucional de gestores/professores.'
    else:
        report = build(scope, {})
        data['institutional_analysis'] = {k: report[k] for k in (
            'metrics', 'eligible', 'evaluated', 'participation', 'missing', 'distribution', 'timeline', 'method', 'version', 'demo')}
        data['institutional_analysis']['timeline'] = report['timeline'][-30:]
        data['analysis_filters'] = {'offers': list(scope.offers.values('id', 'name')[:30]),
            'students': list(scope.students.values('id', 'user__first_name', 'user__last_name')[:30]),
            'subjects': sorted({s for _, s in scope.pairs})}
        data['institutional_analysis']['students'] = report['student_rows'][:30]
        data['institutional_analysis']['hypotheses'] = report['hypotheses'][:30]
    return data


def read_tool(user, tool):
    """Closed allowlist: the model never supplies SQL, paths or permission scopes."""
    from django.core.exceptions import ValidationError
    from django.db.models import Q
    if not isinstance(tool, dict):
        raise ValidationError('Consulta inválida.')
    name = tool.get('name')
    if name == 'search_questions':
        query = tool.get('query', '')
        if not isinstance(query, str) or len(query) > 160:
            raise ValidationError('Busca inválida.')
        qs = available_questions(user).filter(Q(subject__icontains=query) | Q(topic__icontains=query) | Q(statement__icontains=query))
        rows = list(qs.values('id', 'subject', 'topic', 'statement', 'owner_id')[:30])
        for row in rows:
            row['statement'] = row['statement'][:800]
        return {'questions': rows, 'limit': 30}
    if name in ('get_question', 'get_questionnaire') and type(tool.get('id')) is not int:
        raise ValidationError('Identificador inválido.')
    if name == 'get_question':
        q = available_questions(user).filter(pk=tool.get('id')).values('id', 'owner_id', 'subject', 'topic', 'statement', 'support_text', 'question_type', 'options', 'correct_answer', 'explanation', 'default_points', 'updated_at').first()
        if not q:
            raise ValidationError('Questão indisponível.')
        return q
    if name == 'get_questionnaire':
        a = Assessment.objects.filter(owner=user, pk=tool.get('id')).first()
        if not a:
            raise ValidationError('Questionário indisponível.')
        return {'id': a.pk, 'subject': a.subject, 'topic': a.topic, 'questions': list(a.questions.values('id', 'statement', 'points', 'order')[:30])}
    if name == 'analysis':
        from contexts.institutions.analysis.scope import Scope
        from contexts.institutions.analysis.forms import Filters
        from contexts.institutions.analysis.services import build
        params = tool.get('filters', {})
        if not isinstance(params, dict) or any(not isinstance(v, (str, int)) for v in params.values()):
            raise ValidationError('Filtros inválidos.')
        scope = Scope(user)
        form = Filters(scope, params)
        if set(params) - set(form.fields) or not form.is_valid():
            raise ValidationError('Filtros inválidos ou fora do seu acesso.')
        report = build(scope, form.cleaned_data)
        return {k: report[k][:30] if isinstance(report[k], list) else report[k] for k in (
            'metrics', 'eligible', 'evaluated', 'participation', 'missing', 'distribution', 'timeline', 'student_rows', 'hypotheses', 'method', 'version', 'demo')}
    raise ValidationError('Consulta não permitida.')
