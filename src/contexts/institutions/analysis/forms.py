from django import forms
from django.core.exceptions import ValidationError
from features.assessments.models import Assessment
from features.users_manager.models import InstitutionalAccount
from ..coursework.models import Publication
from .models import (OfferContext, Curriculum, Evidence, Attendance, Trajectory, Intervention, OfficialResult, KeyRevision, STAGES)

class Filters(forms.Form):
    year = forms.IntegerField(label='Ano letivo', required=False,min_value=1990,max_value=2200)
    start = forms.DateField(label='Início', required=False,widget=forms.DateInput(attrs={'type':'date'}))
    end = forms.DateField(label='Fim', required=False,widget=forms.DateInput(attrs={'type':'date'}))
    stage = forms.ChoiceField(label='Etapa',required=False,choices=[('','Todas')]+STAGES)
    grade = forms.ChoiceField(label='Série', required=False)
    offer = forms.ModelChoiceField(label='Turma / oferta',queryset=None,required=False)
    subject = forms.ChoiceField(label='Disciplina',required=False)
    assessment = forms.ModelChoiceField(label='Avaliação',queryset=None,required=False)
    skill = forms.ChoiceField(label='Habilidade',required=False)
    student = forms.ModelChoiceField(label='Aluno',queryset=None,required=False)
    def __init__(self, scope, *args, **kwargs):
        super().__init__(*args,**kwargs)
        self.fields['offer'].queryset=scope.offers
        self.fields['offer'].label_from_instance=lambda o:f'{o.name} · {o.code}'
        self.fields['subject'].choices=[('','Todas')]+[(s,s) for s in sorted({s for o,s in scope.pairs})]
        self.fields['grade'].choices=[('','Todas')]+[(g,g) for g in scope.offers.values_list('grade',flat=True).distinct()]
        pubs=Publication.objects.filter(scope.query())
        self.fields['assessment'].queryset=Assessment.objects.filter(pk__in=list(scope.runs().values_list('assessment_id',flat=True))+list(pubs.values_list('assessment_id',flat=True)))
        skills=set(scope.records(Curriculum).values_list('skill',flat=True))|set(scope.records(Evidence).values_list('skill',flat=True))
        for run in scope.runs():
            for q in run.questions:skills.update(q.get('diagnostic_metadata',{}).get('skills',[]))
        self.fields['skill'].choices=[('','Todas')]+[(s,s) for s in sorted(skills)]
        self.fields['student'].queryset=scope.students
        self.fields['student'].label_from_instance=lambda s:s.user.get_full_name() or s.registration
    def clean(self):
        data=super().clean()
        if data.get('start') and data.get('end') and data['start']>data['end']:raise ValidationError('Período inválido.')
        return data

REGISTRY={
    'curriculo':(Curriculum,['offer','subject','skill','description','source'],'Cobertura curricular'),
    'evidencia':(Evidence,['offer','subject','student','publication','skill','criterion','attempt','date','score','maximum','concept','observation','status','purpose','comparability','instrument_notes'],'Evidência / rubrica'),
    'frequencia':(Attendance,['offer','subject','student','date','hours','present'],'Frequência em horas'),
    'trajetoria':(Trajectory,['offer','student','birth_date','outcome','transition','next_year','verification','consolidated'],'Trajetória escolar'),
    'intervencao':(Intervention,['offer','subject','student','skill','difficulty','action','responsible','starts_on','ends_on','before','after','outcome'],'Intervenção / recuperação'),
    'oficial':(OfficialResult,['indicator','year','stage','area','value','unit','status','source','methodology'],'Resultado oficial'),
    'configuracao':(OfferContext,['offer','stage','expected_age','census_date','regulation','minimum_evidence','low_score','attendance_alert'],'Regras e contexto da oferta'),
    'gabarito':(KeyRevision,['run','question_index','correct','annulled','reason'],'Revisão do gabarito da aplicação'),
}
MANAGER_ONLY={'trajetoria','oficial','configuracao'}

def record_form(scope, kind, data=None, instance=None):
    model,fields,title=REGISTRY[kind]
    class Form(forms.modelform_factory(model, fields=fields)):
        change_reason=forms.CharField(label='Motivo do registro / revisão',widget=forms.Textarea(attrs={'rows':2}))
        def clean(self):
            values=super().clean()
            if self.instance.pk:
                for field in ('offer','subject','student','publication','criterion','attempt','skill'):
                    if field in values and values[field] != getattr(self.instance,field):
                        raise ValidationError('A identidade do registro é preservada. Crie outro registro para mudar aluno, oferta, disciplina ou critério.')
            offer=values.get('offer');subject=values.get('subject')
            if offer and subject and (offer.pk,subject) not in scope.pairs:raise ValidationError('Disciplina não autorizada nesta oferta.')
            student=values.get('student')
            if offer and student and not student.user.classroom_memberships.filter(classroom_id=offer.classroom_id,role='STUDENT',status='ACTIVE').exists():
                raise ValidationError('Aluno sem matrícula ativa nesta oferta.')
            return values
    form=Form(data=data,instance=instance)
    if 'offer' in form.fields:form.fields['offer'].queryset=scope.offers
    if 'subject' in form.fields:form.fields['subject']=forms.ChoiceField(label='Disciplina',choices=[(s,s) for s in sorted({s for o,s in scope.pairs})])
    if 'student' in form.fields:form.fields['student'].queryset=scope.students
    if 'publication' in form.fields:form.fields['publication'].queryset=Publication.objects.filter(scope.query())
    if 'responsible' in form.fields:
        form.fields['responsible'].queryset=InstitutionalAccount.objects.filter(organization=scope.organization,role__in=['TEACHER','MANAGER','ADMIN']) if scope.manager else InstitutionalAccount.objects.filter(pk=scope.account.pk)
    for key in ('before','after'):
        if key in form.fields:form.fields[key].queryset=scope.records(Evidence)
    if 'run' in form.fields:form.fields['run'].queryset=scope.runs()
    for field in form.fields.values():
        if isinstance(field,forms.DateField):field.widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d')
    return form
