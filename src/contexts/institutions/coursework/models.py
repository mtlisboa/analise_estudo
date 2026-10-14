from datetime import datetime

from django.db import models


class Publication(models.Model):
    class Kind(models.TextChoices):
        EXAM = 'EXAM', 'Prova'
        ACTIVITY = 'ACTIVITY', 'Atividade'

    offer = models.ForeignKey('institution_planning.Offer', on_delete=models.CASCADE, related_name='coursework')
    subject = models.CharField('disciplina', max_length=80)
    teacher = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT)
    assessment = models.ForeignKey('assessments.Assessment', on_delete=models.PROTECT)
    kind = models.CharField('tipo', max_length=10, choices=Kind.choices)
    title = models.CharField('título', max_length=160)
    instructions = models.TextField('instruções', max_length=3000, blank=True)
    due_at = models.DateTimeField('prazo / data da prova', null=True, blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    public_snapshot = models.JSONField(default=dict, blank=True)
    grading_snapshot = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-published_at', '-created_at', '-pk']

    @property
    def visible_title(self):
        return self.public_snapshot.get('title', self.title)

    @property
    def visible_due_at(self):
        value = self.public_snapshot.get('due_at')
        return datetime.fromisoformat(value) if value else None


class PDFModule(models.Model):
    offer = models.ForeignKey('institution_planning.Offer', on_delete=models.CASCADE, related_name='pdf_modules')
    subject = models.CharField('disciplina', max_length=80)
    teacher = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT)
    title = models.CharField('título', max_length=160)
    document = models.BinaryField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class Submission(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.PROTECT, related_name='submissions')
    student = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    answers = models.JSONField(default=dict)
    automatic_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    maximum_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    score = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    open_scores = models.JSONField(default=dict)
    feedback = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True)
    reviewed_by = models.ForeignKey('accounts.User', null=True, on_delete=models.PROTECT, related_name='+')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['publication', 'student'], name='one_submission_per_publication')]


class SubmissionReview(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    previous_scores = models.JSONField(default=dict)
    scores = models.JSONField(default=dict)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
