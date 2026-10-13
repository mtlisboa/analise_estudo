import uuid

from django.core.exceptions import ValidationError
from django.db import models


def private_attachment(instance, filename):
    from pathlib import Path
    return f'family_documents/{uuid.uuid4()}{Path(filename).suffix.lower()}'


class GuardianLink(models.Model):
    guardian = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.CASCADE, related_name='child_links')
    student = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.CASCADE, related_name='guardian_links')
    relationship = models.CharField('parentesco / responsabilidade', max_length=80)
    is_active = models.BooleanField('vínculo ativo', default=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['guardian', 'student'], name='family_guardian_student_unique')]

    def clean(self):
        if self.guardian_id and self.student_id:
            if (self.guardian.role != 'GUARDIAN' or self.student.role != 'STUDENT'
                    or self.guardian.organization_id != self.student.organization_id):
                raise ValidationError('Vincule um responsável e um aluno da mesma instituição.')


class FamilyRequest(models.Model):
    class Kind(models.TextChoices):
        CONTACT = 'CONTACT', 'Contato com a instituição'
        DOCUMENT = 'DOCUMENT', 'Solicitação de documento'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Aberto'
        PROGRESS = 'PROGRESS', 'Em atendimento'
        RESOLVED = 'RESOLVED', 'Concluído'
        REJECTED = 'REJECTED', 'Indeferido'

    protocol = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey('users_manager.Organization', on_delete=models.CASCADE)
    guardian = models.ForeignKey('users_manager.InstitutionalAccount', on_delete=models.PROTECT)
    student = models.ForeignKey('users_manager.InstitutionalAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='family_requests')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField('assunto / documento solicitado', max_length=160)
    description = models.TextField('mensagem / finalidade', max_length=3000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']

    def clean(self):
        if self.guardian_id and (self.guardian.role != 'GUARDIAN' or self.guardian.organization_id != self.organization_id):
            raise ValidationError('Responsável incompatível com a instituição.')
        if self.kind == self.Kind.DOCUMENT and not self.student_id:
            raise ValidationError('Selecione o aluno para solicitar um documento.')
        if self.student_id and not GuardianLink.objects.filter(guardian=self.guardian, student=self.student,
                student__role='STUDENT', student__user__is_active=True, is_active=True).exists():
            raise ValidationError('O aluno precisa ter um vínculo ativo com este responsável.')


class RequestMessage(models.Model):
    request = models.ForeignKey(FamilyRequest, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    text = models.TextField('resposta', max_length=3000)
    attachment = models.FileField('documento PDF', upload_to=private_attachment, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class SchoolEvent(models.Model):
    organization = models.ForeignKey('users_manager.Organization', on_delete=models.CASCADE)
    classroom = models.ForeignKey('users_manager.Classroom', null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField('evento', max_length=160)
    description = models.TextField('descrição', max_length=3000)
    starts_at = models.DateTimeField('início')
    ends_at = models.DateTimeField('fim')
    location = models.CharField('local', max_length=200, blank=True)
    is_published = models.BooleanField('publicado', default=False)
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)

    class Meta:
        ordering = ['starts_at', 'pk']

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValidationError('O fim do evento não pode ser anterior ao início.')
        if self.classroom_id and self.classroom.organization_id != self.organization_id:
            raise ValidationError('Selecione uma turma desta instituição.')
