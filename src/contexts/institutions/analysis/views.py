import csv
import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.forms.models import model_to_dict
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from .scope import Scope
from .forms import Filters, REGISTRY, MANAGER_ONLY, record_form
from .models import Audit, Evidence, KeyRevision
from .services import build, effective_questions

SECTIONS=[('overview','Visão geral'),('learning','Aprendizagem e habilidades'),('classes','Turmas e disciplinas'),('students','Alunos'),('items','Questões e distratores'),('attendance','Frequência e atividades'),('interventions','Intervenções e recuperação'),('trajectory','Rendimento e permanência'),('official','Indicadores oficiais e contexto escolar')]

def snapshot(obj):
    return json.loads(json.dumps(model_to_dict(obj),cls=DjangoJSONEncoder))

@login_required
@never_cache
@require_GET
def index(request, teacher_only=False):
    scope=Scope(request.user)
    if teacher_only and scope.account.role!='TEACHER':raise PermissionDenied
    params=request.GET.copy()
    # Keep existing links to the old teacher filters usable.
    if params.get('classroom'):
        if not params['classroom'].isdigit():return HttpResponse('Turma inválida.',status=400)
        offer=scope.offers.filter(classroom_id=params['classroom']).first()
        if not offer:return HttpResponse('Turma não autorizada.',status=400)
        params['offer']=str(offer.pk)
    if params.get('period') in ('30','90') and not params.get('start'):
        from datetime import timedelta
        from django.utils import timezone
        params['start']=(timezone.localdate()-timedelta(days=int(params['period']))).isoformat()
    form=Filters(scope,params)
    section=request.GET.get('section','overview')
    sections=[(key,label) for key,label in SECTIONS if scope.manager or key not in ('official','trajectory')]
    if section not in dict(sections):raise PermissionDenied
    context={'scope':scope,'institution':scope.organization.school,'filter_form':form,'sections':sections,'section':section,
        'title':dict(sections)[section], 'collect':[(k,v[2]) for k,v in REGISTRY.items() if scope.manager or k not in MANAGER_ONLY]}
    if not form.is_valid():return render(request,'institutions/analysis/index.html',context,status=400)
    data=build(scope,form.cleaned_data)
    if request.GET.get('format')=='csv':
        response=HttpResponse(content_type='text/csv; charset=utf-8');response['Content-Disposition']='attachment; filename="analise.csv"'
        response.write('\ufeff');writer=csv.writer(response)
        def safe(v):
            s=str(v if v is not None else 'Indisponível');return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
        writer.writerow(['Metodologia',data['version'],data['method']]);writer.writerow(['Filtros',safe(params.urlencode())]);writer.writerow(['Origem','Demonstração' if data['demo'] else 'Registros internos autorizados'])
        writer.writerow(['Fonte','Aluno (ID interno)','Oferta','Disciplina','Data','Obtido','Possível','Percentual'])
        for r in data['rows']:writer.writerow([safe(r[k]) for k in ('source','student','code','subject','date','score','maximum','percentage')])
        return response
    if request.GET.get('format')=='json':
        return JsonResponse({k:data[k] for k in ('metrics','eligible','evaluated','participation','missing','distribution','timeline','skills','items','hypotheses','method','version','demo')})
    context.update(data)
    if request.resolver_match.view_name == 'institutions:manager-performance':
        context['metrics'] = [m for m in data['metrics'] if m[0] != 'Alunos avaliados']
    context['performance_page'] = Paginator(list({r['classroom'] for r in data['rows']}),25).get_page(request.GET.get('page'))
    context['row_page']=Paginator(data['rows'],25).get_page(request.GET.get('page'))
    context['student_page']=Paginator(data['student_rows'],25).get_page(request.GET.get('page'))
    context['classroom_summary']={r['offer'] for r in data['rows']}
    query=params.copy();query.pop('page',None);query.pop('format',None);query.pop('section',None)
    context['query']=query.urlencode()
    student_ids=dict(scope.students.values_list('user_id','pk'))
    for r in context['row_page']:
        r['detail_query']=query.copy();
        if r['offer']: r['detail_query']['offer']=r['offer']
        if r['student'] in student_ids:r['detail_query']['student']=student_ids[r['student']]
        r['detail_query']['assessment']=r['assessment'];r['detail_query']=r['detail_query'].urlencode()
    return render(request,'institutions/analysis/index.html',context)

@login_required
@never_cache
@require_http_methods(['GET','POST'])
def record(request,kind,pk=None):
    scope=Scope(request.user)
    if kind not in REGISTRY:raise Http404
    if kind in MANAGER_ONLY and not scope.manager:raise PermissionDenied
    model,fields,title=REGISTRY[kind]
    if kind=='oficial':qs=model.objects.filter(organization=scope.organization)
    elif kind in ('trajetoria','configuracao'):qs=model.objects.filter(offer__in=scope.offers)
    elif kind=='gabarito':qs=model.objects.filter(run__in=scope.runs())
    else:qs=scope.records(model)
    obj=get_object_or_404(qs,pk=pk) if pk else model()
    if kind=='gabarito' and pk:raise PermissionDenied('Revisões são imutáveis; registre outra revisão.')
    if kind=='oficial':obj.organization=scope.organization;obj.inep_code=scope.organization.school.inep_code or '';obj.imported_by=request.user
    if kind=='evidencia':obj.created_by=request.user
    if kind=='gabarito':obj.author=request.user
    if hasattr(obj,'is_demo'):obj.is_demo=scope.organization.name=='Colégio Lumini Demo'
    before=snapshot(obj) if pk else {}
    form=record_form(scope,kind,request.POST if request.method=='POST' else None,instance=obj)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                if pk:
                    # Prevent concurrent edits from silently overwriting the audit's before image.
                    previous=qs.select_for_update().get(pk=pk)
                    if snapshot(previous)!=before:raise ValidationError('Registro alterado. Recarregue e tente novamente.')
                obj=form.save(commit=False)
                if kind=='evidencia' and not pk:
                    obj.snapshot={'publication':obj.publication.public_snapshot,'rubric':obj.observation,'maximum':str(obj.maximum)}
                obj.full_clean();obj.save()
                Audit.objects.create(organization=scope.organization,actor=request.user,model=model._meta.label,
                    object_id=str(obj.pk),before=before,after=snapshot(obj),reason=form.cleaned_data['change_reason'])
                if kind=='gabarito':
                    # Existing printed results and family views must agree with the new answer key.
                    from features.paper_exams.models import SheetResult
                    from features.paper_exams.services import grade
                    questions=[q for q in effective_questions(obj.run) if not q.get('annulled')]
                    all_questions=effective_questions(obj.run)
                    for result in SheetResult.objects.select_for_update().filter(sheet__run=obj.run):
                        old={'score':str(result.score)};answers=[a for q,a in zip(all_questions,result.answers) if not q.get('annulled')]
                        score,maximum=grade(questions,answers);result.maximum_score=maximum
                        if result.status=='graded':result.score=score
                        result.save(update_fields=['score','maximum_score'])
                        # Binary scan data never enters the audit.
                        old.pop('evidence',None)
                        Audit.objects.create(organization=scope.organization,actor=request.user,model='paper_exams.SheetResult',object_id=str(result.pk),
                            before={'score':str(old.get('score'))},after={'score':str(result.score),'maximum':str(maximum)},reason=obj.reason)
            messages.success(request,'Registro salvo com histórico de revisão.')
            return redirect('institutions:institution-analysis:index')
        except ValidationError as exc:form.add_error(None,exc)
    return render(request,'institutions/analysis/record.html',{'form':form,'title':title,'kind':kind,'records':Paginator(qs.order_by('-pk'),25).get_page(request.GET.get('page')),'scope':scope,'history':Audit.objects.filter(organization=scope.organization,model=model._meta.label,object_id=str(pk)).order_by('-created_at')[:25] if pk else []})
