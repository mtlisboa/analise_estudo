from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

STAGES = [('infantil', 'Educação infantil'), ('fundamental', 'Ensino fundamental'), ('medio', 'Ensino médio'), ('outro', 'Outra modalidade')]

class OfferContext(models.Model):
    offer = models.OneToOneField('institution_planning.Offer', on_delete=models.CASCADE, related_name='analysis_context')
    stage = models.CharField('etapa', max_length=20, choices=STAGES)
    expected_age = models.PositiveSmallIntegerField('idade esperada na série', null=True, blank=True)
    census_date = models.DateField('data de referência etária', null=True, blank=True)
    regulation = models.TextField('regimento / regras de avaliação', blank=True)
    minimum_evidence = models.PositiveSmallIntegerField('mínimo de evidências para alerta', default=3, validators=[MinValueValidator(2)])
    low_score = models.PositiveSmallIntegerField('limiar de alerta interno (%)', null=True, blank=True, validators=[MaxValueValidator(100)])
    attendance_alert = models.PositiveSmallIntegerField('limiar de alerta de frequência (%)', null=True, blank=True, validators=[MaxValueValidator(100)])

class ScopedRecord(models.Model):
    offer = models.ForeignKey('institution_planning.Offer', on_delete=models.PROTECT)
    subject = models.CharField('disciplina', max_length=80)
    is_demo = models.BooleanField(default=False, editable=False)
    class Meta:
        abstract = True
    def clean(self):
        self.subject = self.subject.strip().upper()
        if self.offer_id and not any(x.get('subject') == self.subject for x in self.offer.published_schedule):
            raise ValidationError('A disciplina deve existir na oferta publicada.')
        student = self.student if getattr(self, 'student_id', None) else None
        if self.offer_id and student and (student.organization_id != self.offer.period.organization_id or student.role != 'STUDENT'):
            raise ValidationError('O aluno deve pertencer à instituição da oferta.')

class Curriculum(ScopedRecord):
    skill = models.CharField('código BNCC / descritor / objetivo local', max_length=80)
    description = models.TextField('objetivo de aprendizagem')
    source = models.CharField('referência curricular e versão', max_length=240)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['offer','subject','skill'], name='analysis_curriculum_unique')]
    def __str__(self):
        return f'{self.skill} · {self.description[:70]}'

class Evidence(ScopedRecord):
    student = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT)
    publication = models.ForeignKey('institution_coursework.Publication', on_delete=models.PROTECT)
    skill = models.CharField('habilidade / critério', max_length=80)
    criterion = models.CharField('identificador do item / critério', max_length=80)
    attempt = models.PositiveSmallIntegerField('tentativa', default=1, validators=[MinValueValidator(1)])
    date = models.DateField('data da evidência')
    score = models.DecimalField('pontos obtidos', max_digits=9, decimal_places=2, null=True, blank=True)
    maximum = models.DecimalField('pontos possíveis (inclua peso da rubrica)', max_digits=9, decimal_places=2, null=True, blank=True)
    concept = models.CharField('conceito', max_length=80, blank=True)
    observation = models.TextField('evidência qualitativa / rubrica', blank=True)
    status = models.CharField(max_length=12, choices=[('evaluated','Avaliado'),('pending','Pendente'),('absent','Ausente'),('annulled','Anulado')], default='evaluated')
    purpose = models.CharField('finalidade', max_length=12, choices=[('regular','Regular'),('recovery','Recuperação'),('retention','Retenção após intervalo'),('transfer','Aplicação em situação nova')], default='regular')
    comparability = models.CharField('grupo de instrumentos comparáveis (validado pelo docente)', max_length=100, blank=True)
    instrument_notes = models.TextField('justificativa da comparabilidade / adequação do instrumento', blank=True)
    snapshot = models.JSONField(default=dict, editable=False)
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['publication','student','criterion','attempt'], name='analysis_evidence_attempt')]
        indexes = [models.Index(fields=['offer','subject','date'])]
    def clean(self):
        super().clean()
        if self.offer_id and self.publication_id and (self.publication.offer_id != self.offer_id or self.publication.subject != self.subject):
            raise ValidationError('A publicação deve ser da oferta e disciplina selecionadas.')
        if (self.score is None) != (self.maximum is None):
            raise ValidationError('Informe ambos os pontos, ou somente evidência qualitativa.')
        if self.score is not None and (self.maximum <= 0 or not 0 <= self.score <= self.maximum):
            raise ValidationError('Pontos devem estar entre zero e o máximo positivo.')
        if self.status == 'evaluated' and self.score is None and not (self.observation or self.concept):
            raise ValidationError('Registre pontos, conceito ou evidência qualitativa.')
        if (self.comparability or self.purpose in ('retention','transfer')) and not self.instrument_notes:
            raise ValidationError('Documente a adequação do instrumento / comparabilidade.')

class Attendance(ScopedRecord):
    student = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT)
    date = models.DateField('data')
    hours = models.DecimalField('horas letivas ministradas', max_digits=6, decimal_places=2)
    present = models.DecimalField('horas presentes', max_digits=6, decimal_places=2)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['offer','subject','student','date'], name='analysis_attendance_day')]
    def clean(self):
        super().clean()
        if self.hours is not None and self.present is not None and (self.hours <= 0 or not 0 <= self.present <= self.hours):
            raise ValidationError('Horas presentes devem estar entre zero e as horas ministradas positivas.')

class Trajectory(models.Model):
    offer = models.ForeignKey('institution_planning.Offer', on_delete=models.PROTECT)
    student = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT)
    birth_date = models.DateField('nascimento', null=True, blank=True)
    outcome = models.CharField('situação no ano', max_length=12, choices=[('ongoing','Em curso'),('approved','Aprovado'),('failed','Reprovado'),('abandoned','Abandono'),('transferred','Transferência'),('unknown','Sem informação')])
    transition = models.CharField('situação no ano seguinte verificada', max_length=12, blank=True, choices=[('promoted','Promoção'),('repeated','Repetência'),('dropout','Evasão confirmada'),('transferred','Transferência')])
    next_year = models.PositiveSmallIntegerField('ano seguinte verificado', null=True, blank=True)
    verification = models.TextField('fonte / verificação longitudinal', blank=True)
    consolidated = models.BooleanField('ano encerrado e conferido', default=False)
    is_demo = models.BooleanField(default=False, editable=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['offer','student'], name='analysis_trajectory_unique')]
    def clean(self):
        if self.offer_id and self.student_id and (self.student.organization_id != self.offer.period.organization_id or self.student.role != 'STUDENT'):
            raise ValidationError('Aluno de outra instituição.')
        if self.offer_id and self.transition and (self.next_year != self.offer.period.starts_on.year + 1 or not self.verification):
            raise ValidationError('Confirme o ano seguinte e a fonte; falta de matrícula não comprova evasão.')
        if self.outcome == 'transferred' and self.transition == 'dropout':
            raise ValidationError('Transferência não pode ser automaticamente registrada como evasão.')
        if self.offer_id and getattr(self.offer, 'analysis_context', None) and self.offer.analysis_context.stage == 'infantil' and self.outcome in ('approved','failed'):
            raise ValidationError('Educação infantil: acompanhamento sem aprovação por nota.')

class Intervention(ScopedRecord):
    student = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT)
    skill = models.CharField('habilidade', max_length=80)
    difficulty = models.TextField('dificuldade observada')
    action = models.TextField('ação pedagógica')
    responsible = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT, related_name='+')
    starts_on = models.DateField('início')
    ends_on = models.DateField('fim')
    before = models.ForeignKey(Evidence, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    after = models.ForeignKey(Evidence, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    outcome = models.TextField('resultado / dificuldades persistentes', blank=True)
    def clean(self):
        super().clean()
        if self.starts_on and self.ends_on and self.starts_on > self.ends_on:
            raise ValidationError('Período inválido.')
        if self.offer_id and self.responsible_id and (self.responsible.organization_id != self.offer.period.organization_id or self.responsible.role not in ('TEACHER','MANAGER','ADMIN')):
            raise ValidationError('Responsável deve ser educador da instituição.')
        for record in (self.before, self.after):
            if record and (record.student_id != self.student_id or record.offer_id != self.offer_id or record.subject != self.subject or record.skill != self.skill):
                raise ValidationError('As evidências devem ser do mesmo aluno, oferta, disciplina e habilidade.')
        if self.before and self.after and self.before.date >= self.after.date:
            raise ValidationError('A evidência posterior deve ocorrer depois da anterior.')

INDICATORS = [(key, label) for key, label in [
    ('ideb','Ideb'),('saeb','Proficiência Saeb'),('saeb_levels','Distribuição por níveis Saeb'),('participation','Participação externa'),
    ('literacy','Alfabetização ao final do 2º ano'),('approval','Aprovação'),('failure','Reprovação'),('abandonment','Abandono'),
    ('promotion','Promoção'),('repetition','Repetência'),('dropout','Evasão'),('age_grade','Distorção idade-série'),
    ('training','Adequação da formação docente'),('regularity','Regularidade docente'),('effort','Esforço docente'),
    ('class_size','Média de alunos por turma'),('hours','Horas-aula diárias'),('inse','Inse'),('complexity','Complexidade de gestão')]]

class OfficialResult(models.Model):
    organization = models.ForeignKey('users_manager.Organization', on_delete=models.PROTECT)
    inep_code = models.CharField('código Inep', max_length=12)
    indicator = models.CharField('indicador', max_length=20, choices=INDICATORS)
    year = models.PositiveSmallIntegerField('ano / edição', validators=[MinValueValidator(1990),MaxValueValidator(2200)])
    stage = models.CharField('etapa', max_length=20, choices=STAGES)
    area = models.CharField('área / disciplina / nível de proficiência', max_length=120)
    value = models.DecimalField('valor', max_digits=12, decimal_places=4, null=True, blank=True)
    unit = models.CharField('unidade', max_length=50)
    status = models.CharField('publicação', max_length=16, choices=[('published','Publicado'),('not_published','Não publicado para a escola')])
    source = models.URLField('URL da fonte oficial', max_length=500)
    methodology = models.TextField('metodologia, população, denominador e exclusões')
    imported_at = models.DateTimeField(auto_now_add=True)
    imported_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    is_demo = models.BooleanField(default=False, editable=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['organization','indicator','year','stage','area','is_demo'], name='analysis_official_unique')]
    def clean(self):
        from urllib.parse import urlparse
        host = urlparse(self.source).hostname or ''
        if not self.is_demo and not (host.endswith('.gov.br') or host == 'gov.br'):
            raise ValidationError('Registre a URL da publicação oficial em domínio gov.br.')
        if self.value is not None and (self.value < 0 or (self.indicator == 'ideb' and self.value > 10) or (self.indicator in ('approval','failure','abandonment','promotion','repetition','dropout','age_grade','participation') and self.value > 100)):
            raise ValidationError('Valor fora da escala do indicador.')
        if self.inep_code != (self.organization.school.inep_code or ''):
            raise ValidationError('O código Inep deve corresponder à instituição.')
        if (self.status == 'published') != (self.value is not None):
            raise ValidationError('Informe valor somente para resultado publicado.')

class Audit(models.Model):
    organization = models.ForeignKey('users_manager.Organization', on_delete=models.PROTECT)
    actor = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    model = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class KeyRevision(models.Model):
    run = models.ForeignKey('paper_exams.ExamRun', on_delete=models.PROTECT, related_name='key_revisions')
    question_index = models.PositiveSmallIntegerField('número da questão (iniciando em 1)', validators=[MinValueValidator(1)])
    correct = models.CharField('gabarito revisado (letra)', max_length=1, blank=True)
    annulled = models.BooleanField('anular e excluir do denominador', default=False)
    reason = models.TextField('justificativa')
    author = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    def clean(self):
        if self.run_id and self.question_index is not None:
            if not 1 <= self.question_index <= len(self.run.questions):
                raise ValidationError('Questão inexistente nesta aplicação.')
            letters = 'ABCDE'[:len(self.run.questions[self.question_index-1]['options'])]
            if not self.annulled and self.correct not in letters:
                raise ValidationError('Selecione um gabarito válido.')
