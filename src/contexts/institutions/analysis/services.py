"""Internal methodology v1. No internal score is a Saeb proficiency or an Ideb."""
from collections import Counter, defaultdict
from decimal import Decimal
from statistics import mean
from django.db.models import Q
from features.paper_exams.models import SheetResult, AnswerSheet
from .models import Evidence, Attendance, Curriculum, Trajectory, Intervention, OfficialResult

VERSION = 'interna-1.0'
METHOD = ('Pontuação obtida / possível × 100. Provas: média dos percentuais por aplicação; '
          'rubricas: soma ponderada pelos pontos possíveis, por publicação/aluno. Provas reaplicadas: última aplicação corrigida da mesma avaliação/turma/aluno no recorte. Última tentativa avaliada '
          'de cada critério; tentativas pendentes não apagam evidência anterior. Itens anulados são excluídos. '
          'Ausência, revisão e denominador zero não são zero de aprendizagem. Variação descritiva, sem equiparação Saeb.')

def percent(n, d):
    return round(float(n)*100/float(d), 2) if d else None

def filtered(scope, model, f, dated=None):
    qs = scope.records(model)
    if f.get('offer'): qs = qs.filter(offer=f['offer'])
    if f.get('subject'): qs = qs.filter(subject=f['subject'])
    if f.get('year'): qs = qs.filter(offer__period__starts_on__year=f['year'])
    if f.get('grade'): qs = qs.filter(offer__grade=f['grade'])
    if f.get('stage'): qs = qs.filter(offer__analysis_context__stage=f['stage'])
    if f.get('student'): qs = qs.filter(student=f['student']) if any(x.name=='student' for x in model._meta.fields) else qs
    if dated:
        if f.get('start'): qs=qs.filter(**{dated+'__gte':f['start']})
        if f.get('end'): qs=qs.filter(**{dated+'__lte':f['end']})
    return qs

def selected_runs(scope, f):
    qs = scope.runs()
    if f.get('offer'): qs=qs.filter(classroom_id=f['offer'].classroom_id)
    if f.get('subject'): qs=qs.filter(Q(subject=f['subject'])|Q(subject='',assessment__subject__iexact=f['subject']))
    if f.get('year'): qs=qs.filter(classroom__planning_offer__period__starts_on__year=f['year'])
    if f.get('grade'): qs=qs.filter(classroom__planning_offer__grade=f['grade'])
    if f.get('stage'): qs=qs.filter(classroom__planning_offer__analysis_context__stage=f['stage'])
    if f.get('start'): qs=qs.filter(created_at__date__gte=f['start'])
    if f.get('end'): qs=qs.filter(created_at__date__lte=f['end'])
    if f.get('assessment'): qs=qs.filter(assessment=f['assessment'])
    return qs

def effective_questions(run, sheet=None):
    from copy import deepcopy
    source = run.variants.get(sheet.variant, run.questions) if sheet is not None else run.questions
    questions = deepcopy(source)
    for rev in sorted(run.key_revisions.all(), key=lambda r:(r.created_at,r.pk)):
        if not 1 <= rev.question_index <= len(run.questions):
            continue
        original = run.questions[rev.question_index - 1]
        for index, question in enumerate(questions):
            matches = question.get('id') == original.get('id') if original.get('id') is not None else index == rev.question_index - 1
            if not matches:
                continue
            correct = rev.correct
            order = question.get('option_order')
            if order and correct in 'ABCDE' and correct:
                correct = 'ABCDE'[order.index('ABCDE'.index(correct))]
            question.update(correct=correct, annulled=rev.annulled)
    return questions

def build(scope, f):
    rows, items, skill_rows = [], {}, defaultdict(lambda:{'count':0,'correct':0,'wrong':0,'score':0.0,'maximum':0.0,'dates':set(),'qualitative':0})
    skills_filter = f.get('skill')
    runs = selected_runs(scope,f).select_related('classroom__planning_offer','assessment').prefetch_related('key_revisions')
    run_map={r.pk:r for r in runs}
    results = SheetResult.objects.filter(sheet__run__in=runs).select_related('sheet__student')
    if f.get('student'): results=results.filter(sheet__student_id=f['student'].user_id)
    review=results.filter(status='review').count()
    eligible_qs=AnswerSheet.objects.filter(run__in=runs)
    if f.get('student'): eligible_qs=eligible_qs.filter(student_id=f['student'].user_id)
    eligible=set(eligible_qs.values_list('student_id',flat=True))
    hypotheses=Counter()
    latest_results={}
    for result in results.filter(status='graded',score__isnull=False).order_by('sheet__run__created_at','sheet__run_id'):
        run=run_map[result.sheet.run_id]
        latest_results[(run.assessment_id,run.classroom_id,result.sheet.student_id,run.pk if not run.questions else None)]=result
    for result in latest_results.values():
        run=run_map[result.sheet.run_id]
        offer=getattr(run.classroom,'planning_offer',None)
        questions=effective_questions(run, result.sheet)
        total=Decimal(0); score=Decimal(0); used=0
        for i,q in enumerate(questions):
            meta=q.get('diagnostic_metadata',{})
            skills=meta.get('skills',[])
            if q.get('annulled') or (skills_filter and skills_filter not in skills): continue
            points=Decimal(q['points']); answer=result.answers[i] if i<len(result.answers) else ''
            if q.get('type') == 'open_ended':
                total += points
                score += Decimal(result.open_scores.get(str(i+1), '0'))
                used += 1
                continue
            valid=answer in list('ABCDE'[:len(q.get('options',[]))]); correct=valid and answer==q['correct']
            total+=points; score+=points if correct else 0; used+=1
            canonical_index = next((index for index, original in enumerate(run.questions) if original.get('id') is not None and original.get('id') == q.get('id')), i)
            canonical_answer = 'ABCDE'[q['option_order']['ABCDE'.index(answer)]] if valid and q.get('option_order') else answer
            item_key=(str(run.pk),canonical_index)
            item=items.setdefault(item_key,{'run':str(run.pk),'number':canonical_index+1,'title':run.title,'statement':q.get('statement',''),
                'count':0,'correct':0,'blank':0,'invalid':0,'options':Counter(), 'available':list('ABCDE'[:len(q.get('options',[]))])})
            item['count']+=1;item['correct']+=int(correct)
            if not answer: item['blank']+=1
            elif not valid: item['invalid']+=1
            else: item['options'][canonical_answer]+=1
            for skill in skills:
                if skills_filter and skills_filter!=skill: continue
                s=skill_rows[(result.sheet.student_id,offer.pk if offer else None,run.subject or run.assessment.subject,skill)]
                s['count']+=1;s['correct']+=int(correct);s['wrong']+=int(not correct);s['score']+=float(points) if correct else 0;s['maximum']+=float(points);s['dates'].add(run.created_at.date().isoformat())
            diagnostic=meta.get('alternatives',{}).get(answer,{}) if valid else {}
            if not correct and diagnostic.get('reviewed') and diagnostic.get('hypothesis'):
                hypotheses[(result.sheet.student_id, offer.pk if offer else None, diagnostic['hypothesis'])]+=1
        if not questions and not skills_filter:
            score,total=result.score,result.maximum_score
        if total>0:
            rows.append({'source':'Prova impressa','id':str(result.pk),'student':result.sheet.student_id,
                'name':result.sheet.student.get_full_name() or result.sheet.student.username,'offer':offer.pk if offer else None,
                'classroom':run.classroom.name,'code':str(offer.code) if offer else 'Sem oferta',
                'subject':run.subject or run.assessment.subject,'date':run.created_at.date().isoformat(),
                'score':float(score),'maximum':float(total),'percentage':percent(score,total),'assessment':run.assessment_id,
                'demo':scope.organization.name=='Colégio Lumini Demo'})
    evidence=filtered(scope,Evidence,f,'date').select_related('student__user','offer__classroom','publication')
    if f.get('assessment'): evidence=evidence.filter(publication__assessment=f['assessment'])
    evidence_history=list(evidence.filter(skill=skills_filter).order_by('date','attempt','pk') if skills_filter else evidence.order_by('date','attempt','pk'))
    current={}
    for e in evidence.filter(status__in=['evaluated','annulled']).order_by('attempt','pk'):
        current[(e.publication_id,e.student_id,e.criterion)]=e
    current={key:value for key,value in current.items() if value.status=='evaluated' and (not skills_filter or value.skill==skills_filter)}
    # A publication assessed on paper is not counted a second time through manually entered rubrics.
    paper_pairs={(r['assessment'],r['student'],r['offer']) for r in rows}
    groups=defaultdict(list)
    for e in current.values():
        if (e.publication.assessment_id,e.student.user_id,e.offer_id) in paper_pairs: continue
        groups[(e.publication_id,e.student_id)].append(e)
        s=skill_rows[(e.student.user_id,e.offer_id,e.subject,e.skill)]
        s['count']+=1;s['dates'].add(e.date.isoformat())
        if e.score is None:s['qualitative']+=1
        else:s['score']+=float(e.score);s['maximum']+=float(e.maximum)
    for entries in groups.values():
        e=entries[0];numeric=[x for x in entries if x.score is not None]
        score=sum((x.score for x in numeric),Decimal(0));maximum=sum((x.maximum for x in numeric),Decimal(0))
        rows.append({'source':'Rubrica / atividade','id':str(e.pk),'student':e.student.user_id,
            'name':e.student.user.get_full_name() or e.student.registration,'offer':e.offer_id,'classroom':e.offer.name,
            'code':str(e.offer.code),'subject':e.subject,'date':max(x.date for x in entries).isoformat(),
            'score':float(score) if numeric else None,'maximum':float(maximum) if numeric else None,
            'percentage':percent(score,maximum),'assessment':e.publication.assessment_id,'demo':e.is_demo,
            'concept':'; '.join(x.concept for x in entries if x.concept)})
    # Eligible roster is the current active roster, plus issued sheets (historical participation).
    offers=scope.offers
    if f.get('offer'): offers=offers.filter(pk=f['offer'].pk)
    if f.get('year'): offers=offers.filter(period__starts_on__year=f['year'])
    if f.get('grade'): offers=offers.filter(grade=f['grade'])
    if f.get('stage'): offers=offers.filter(analysis_context__stage=f['stage'])
    if f.get('subject'): offers=offers.filter(pk__in=[o for o,s in scope.pairs if s==f['subject']])
    students=scope.students.filter(user__classroom_memberships__classroom_id__in=offers.values('classroom_id'),user__classroom_memberships__status='ACTIVE')
    if f.get('student'):students=students.filter(pk=f['student'].pk)
    eligible.update(students.values_list('user_id',flat=True))
    evaluated={r['student'] for r in rows};numeric=[r for r in rows if r['percentage'] is not None]
    average=mean(r['percentage'] for r in numeric) if numeric else None
    names={r['student']:r['name'] for r in rows}
    summaries=[]
    for uid in sorted(evaluated):
        vals=[r['percentage'] for r in numeric if r['student']==uid]
        summaries.append({'id':uid,'name':names[uid],'total':len(vals),'average':mean(vals) if vals else None})
    distribution=[{'label':label,'count':sum(low<=r['percentage']<high for r in numeric)} for label,low,high in [('0–24%',0,25),('25–49%',25,50),('50–74%',50,75),('75–100%',75,101)]]
    timeline=[]
    for day in sorted({r['date'] for r in numeric}):
        vals=[r['percentage'] for r in numeric if r['date']==day]
        timeline.append({'date':day,'average':round(mean(vals),2),'count':len(vals)})
    skill_matrix=[]
    offer_map={o.pk:o for o in offers}
    for (uid,oid,subject,skill),s in sorted(skill_rows.items(),key=lambda item:str(item[0])):
        policy=getattr(offer_map.get(oid),'analysis_context',None)
        minimum=policy.minimum_evidence if policy else 3
        s.update(student=names.get(uid,str(uid)), student_id=uid, offer=oid, subject=subject, skill=skill, dates=sorted(s['dates']),percentage=percent(s['score'],s['maximum']),
            status='Evidência insuficiente' if s['count']<minimum else 'Evidências disponíveis; interpretar pedagogicamente')
        skill_matrix.append(s)
    plans=filtered(scope,Curriculum,f)
    if skills_filter:plans=plans.filter(skill=skills_filter)
    observed={(s['offer'],s['subject'],s['skill']) for s in skill_matrix}
    coverage=[{'skill':p.skill,'description':p.description,'subject':p.subject,'offer':p.offer_id,'status':'Avaliada' if (p.offer_id,p.subject,p.skill) in observed else 'Não avaliada'} for p in plans]
    for item in items.values():
        item['percentage']=percent(item['correct'],item['count'])
        item['choices']=[{'letter':a,'count':item['options'][a],'percentage':percent(item['options'][a],item['count']),
            'review': item['count']>=20 and item['options'][a]/item['count']<.05} for a in item.pop('available')]
        item.pop('options')
    attendance=list(filtered(scope,Attendance,f,'date').select_related('student__user','offer__analysis_context').order_by('date','pk'))
    attendance_rows=[];alerts=[]
    for uid,oid,subject in sorted({(a.student_id,a.offer_id,a.subject) for a in attendance}):
        records=[a for a in attendance if (a.student_id,a.offer_id,a.subject)==(uid,oid,subject)];hours=sum(a.hours for a in records);present=sum(a.present for a in records)
        trailing=0
        for a in reversed(records):
            if a.present==0:trailing+=1
            else:break
        value=percent(present,hours);mid=len(records)//2
        first=percent(sum(a.present for a in records[:mid]),sum(a.hours for a in records[:mid]))
        last=percent(sum(a.present for a in records[mid:]),sum(a.hours for a in records[mid:]))
        attendance_rows.append({'student':records[0].student.user.get_full_name() or records[0].student.registration,
            'subject':subject,'offer':oid,'hours':hours,'present':present,'percentage':value,'absences':trailing,'change':round(last-first,2) if mid and first is not None else None})
        policy=getattr(records[0].offer,'analysis_context',None)
        if policy and policy.attendance_alert is not None and value<policy.attendance_alert:
            alerts.append(f'{attendance_rows[-1]["student"]}: frequência de {value}% em {subject}, abaixo do alerta interno de {policy.attendance_alert}%.')
        if mid and first is not None and last<first:alerts.append(f'{attendance_rows[-1]["student"]}: frequência em queda no recorte; conferir registros e carga horária.')
    for student in summaries:
        vals=[r for r in numeric if r['student']==student['id']]
        vals.sort(key=lambda r:r['date'])
        for o in offers:
            policy=getattr(o,'analysis_context',None)
            if policy and policy.stage!='infantil' and policy.low_score is not None:
                recent=[r for r in vals if r['offer']==o.pk][-policy.minimum_evidence:]
                if len(recent)>=policy.minimum_evidence and all(r['percentage']<policy.low_score for r in recent):
                    alerts.append(f'{student["name"]}: baixo rendimento recorrente; {len(recent)} evidências abaixo de {policy.low_score}%. Considerar intervenção.')
    interventions=filtered(scope,Intervention,f,'starts_on').select_related('student__user','before','after','responsible__user')
    if skills_filter:interventions=interventions.filter(skill=skills_filter)
    trajectory=Trajectory.objects.filter(offer__in=offers) if scope.manager else Trajectory.objects.none()
    if f.get('student'):trajectory=trajectory.filter(student=f['student'])
    outcomes=Counter(trajectory.values_list('outcome',flat=True));den=sum(outcomes[x] for x in ('approved','failed','abandoned'))
    rates=[{'label':label,'value':percent(outcomes[key],den),'count':outcomes[key]} for key,label in [('approved','Aprovação'),('failed','Reprovação'),('abandoned','Abandono')]]
    transitions=Counter(trajectory.exclude(transition='').values_list('transition',flat=True));td=sum(transitions[k] for k in ('promoted','repeated','dropout'))
    transition_rates=[{'label':label,'value':percent(transitions[k],td),'count':transitions[k]} for k,label in [('promoted','Promoção'),('repeated','Repetência'),('dropout','Evasão confirmada')]]
    age_n=age_d=0
    for t in trajectory.select_related('offer__analysis_context'):
        ctx=getattr(t.offer,'analysis_context',None)
        if t.birth_date and ctx and ctx.stage in ('fundamental','medio') and ctx.expected_age is not None and ctx.census_date:
            ref=ctx.census_date;age=ref.year-t.birth_date.year-((ref.month,ref.day)<(t.birth_date.month,t.birth_date.day))
            age_d+=1;age_n+=int(age>=ctx.expected_age+2)
    official=OfficialResult.objects.filter(organization=scope.organization) if scope.manager else OfficialResult.objects.none()
    if f.get('year'):official=official.filter(year=f['year'])
    if f.get('stage'):official=official.filter(stage=f['stage'])
    if f.get('subject'):official=official.filter(area=f['subject'])
    class_summary=[]
    for o in offers:
        cohort=set(students.filter(user__classroom_memberships__classroom_id=o.classroom_id).values_list('user_id',flat=True))
        selected=[r for r in rows if r['offer']==o.pk]
        assessed={r['student'] for r in selected};values=[r['percentage'] for r in selected if r['percentage'] is not None]
        class_summary.append({'offer':o,'eligible':len(cohort|assessed),'evaluated':len(assessed),'missing':len(cohort-assessed),'average':mean(values) if values else None, 'participation':percent(len(assessed),len(cohort|assessed))})
    line_points=' '.join(f'{20+i*560/max(1,len(timeline)-1):.1f},{180-t["average"]*1.5:.1f}' for i,t in enumerate(timeline))
    purposes=[e for e in current.values() if e.purpose in ('retention','transfer') and e.instrument_notes]
    return dict(rows=sorted(rows,key=lambda r:(r['date'],r['id']),reverse=True),student_rows=summaries,
        metrics=[('Provas corrigidas',sum(r['source']=='Prova impressa' for r in rows)),('Aguardando revisão',review),('Alunos avaliados',len(evaluated)),('Aproveitamento médio',f'{average:.1f}%'.replace('.',',') if average is not None else '—')],
        eligible=len(eligible),evaluated=len(evaluated),participation=percent(len(evaluated),len(eligible)),missing=len(eligible-evaluated),
        distribution=distribution,result_count=len(numeric),timeline=timeline,line_points=line_points,class_summary=class_summary,skills=skill_matrix,coverage=coverage,items=list(items.values()),
        hypotheses=[{'student':names.get(uid,str(uid)),'offer':oid,'hypothesis':h,'count':n} for (uid,oid,h),n in hypotheses.items()],
        attendance=attendance_rows,alerts=alerts,interventions=interventions,official=official.order_by('-year','indicator'),
        rates=rates,rate_denominator=den,trajectory_missing=outcomes['unknown']+outcomes['ongoing'],transferred=outcomes['transferred'],
        transition_rates=transition_rates,transition_denominator=td,age_grade=percent(age_n,age_d),age_denominator=age_d,
        pending=evidence.exclude(status='evaluated').count(),evidence=list(current.values()),evidence_history=evidence_history,purposes=purposes,
        method=METHOD,version=VERSION, demo=scope.organization.name=='Colégio Lumini Demo')
