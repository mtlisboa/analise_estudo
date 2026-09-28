import uuid

from django.conf import settings
from django.db import models


class ExamRun(models.Model):
    """An immutable copy of the exam at issue time (including the answer key)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey('assessments.Assessment', on_delete=models.PROTECT)
    classroom = models.ForeignKey('users_manager.Classroom', on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    title = models.CharField(max_length=300)
    classroom_name = models.CharField(max_length=300)
    questions = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class AnswerSheet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ExamRun, on_delete=models.CASCADE, related_name='sheets')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    student_name = models.CharField(max_length=300)
    student_registration = models.CharField(max_length=150)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run', 'student'], name='one_sheet_per_student_run')]
        ordering = ['student_name', 'pk']


class ImportBatch(models.Model):
    run = models.ForeignKey(ExamRun, on_delete=models.CASCADE, related_name='imports')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    filename = models.CharField(max_length=255)
    errors = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class SheetResult(models.Model):
    class Status(models.TextChoices):
        REVIEW = 'review', 'Revisão necessária'
        GRADED = 'graded', 'Corrigido'

    sheet = models.OneToOneField(AnswerSheet, on_delete=models.CASCADE, related_name='result')
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name='results')
    source_name = models.CharField(max_length=255)
    # The original data is retained even after a manual review.
    detected = models.JSONField(default=list)
    answers = models.JSONField(default=list)
    issues = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REVIEW)
    score = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    maximum_score = models.DecimalField(max_digits=10, decimal_places=2)
    evidence = models.BinaryField(null=True, editable=False)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    review_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ResultReview(models.Model):
    result = models.ForeignKey(SheetResult, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    previous_answers = models.JSONField()
    answers = models.JSONField()
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
