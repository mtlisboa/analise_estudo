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
