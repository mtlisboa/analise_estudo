from datetime import timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, FloatField, Value
from django.db.models.functions import Cast
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from features.paper_exams.models import SheetResult
from features.users_manager.models import Classroom
from .views import institutional_identity


class AnalysisFilters(forms.Form):
    classroom = forms.ModelChoiceField(label='Turma', required=False, empty_label='Todas as minhas turmas',
        queryset=Classroom.objects.none())
    period = forms.ChoiceField(label='Período', choices=[('all','Todo o período'),('30','Últimos 30 dias'),('90','Últimos 90 dias')], initial='all', help_text='Considera a data de emissão das provas.')

    def __init__(self, classrooms, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['classroom'].queryset = classrooms


@login_required
@never_cache
@require_GET
def index(request):
    account = institutional_identity(request.user)
    if account.role != 'TEACHER':
        raise PermissionDenied('Este módulo é exclusivo do professor.')
    classrooms = Classroom.objects.filter(organization=account.organization, is_active=True,
        memberships__user=request.user, memberships__role='TEACHER', memberships__status='ACTIVE').distinct()
    params = request.GET.copy()
    params.setdefault('period', 'all')
    form = AnalysisFilters(classrooms, params)
    data = {'institution': account.organization.school, 'filter_form': form}
    if not form.is_valid():
        return render(request, 'institutions/teacher_analysis.html', data, status=400)
    selected = form.cleaned_data['classroom']
    results = SheetResult.objects.filter(sheet__run__classroom__in=classrooms,
        sheet__run__created_by=request.user, sheet__run__assessment__owner=request.user)
    if selected:
        results = results.filter(sheet__run__classroom=selected)
    period = form.cleaned_data['period']
    if period != 'all':
        results = results.filter(sheet__run__created_at__gte=timezone.now()-timedelta(days=int(period)))
    graded = results.filter(status='graded', score__isnull=False, maximum_score__gt=0)
    percentage = Cast('score', FloatField()) * Value(100.0) / Cast('maximum_score', FloatField())
    average = graded.aggregate(value=Avg(percentage))['value']
    data['metrics'] = [('Provas corrigidas', graded.count()),
        ('Aguardando revisão', results.filter(status='review').count()),
        ('Alunos avaliados', graded.values('sheet__student_id').distinct().count()),
        ('Aproveitamento médio', f'{average:.1f}%'.replace('.', ',') if average is not None else '—')]
    data['classroom_summary'] = graded.order_by().values('sheet__run__classroom_id', 'sheet__run__classroom__name').annotate(
        total=Count('pk'), average=Avg(percentage)).order_by('sheet__run__classroom__name')
    students = graded.order_by().values('sheet__student_id', 'sheet__student__first_name',
        'sheet__student__last_name', 'sheet__student__username').annotate(total=Count('pk'),
        average=Avg(percentage)).order_by('sheet__student__first_name','sheet__student_id')
    data['student_page'] = Paginator(students, 25).get_page(request.GET.get('page'))
    data['selected_classroom'] = str(selected.pk) if selected else ''
    data['selected_period'] = period
    return render(request, 'institutions/teacher_analysis.html', data)
