from django import forms
from django.contrib.auth import get_user_model
from django.db import models, transaction

from .models import (
    Classroom,
    ClassroomMembership,
    EducationalRelationship,
    MembershipStatus,
    SelfAssessment,
)

User = get_user_model()


class RelationshipRequestForm(forms.Form):
    class Position(models.TextChoices):
        TEACHER = "TEACHER", "Sou professor desta pessoa"
        STUDENT = "STUDENT", "Sou aluno desta pessoa"

    email = forms.EmailField(label="E-mail da outra pessoa")
    position = forms.ChoiceField(label="Relação", choices=Position.choices)

    def __init__(self, *args, requester, **kwargs):
        super().__init__(*args, **kwargs)
        self.requester = requester
        self.other_user = None

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        try:
            self.other_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise forms.ValidationError("Nenhum usuário foi encontrado com este e-mail.") from exc
        if self.other_user == self.requester:
            raise forms.ValidationError("Você não pode criar uma relação consigo mesmo.")
        if self.other_user.is_system_admin:
            raise forms.ValidationError("Contas de sistema não podem participar de relações educacionais.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if not self.other_user or "position" not in cleaned_data:
            return cleaned_data
        teacher, student = self._participants(cleaned_data["position"])
        existing = EducationalRelationship.objects.filter(teacher=teacher, student=student).first()
        if existing and existing.status in {MembershipStatus.PENDING, MembershipStatus.ACTIVE}:
            raise forms.ValidationError("Esta relação já existe ou aguarda confirmação.")
        return cleaned_data

    def _participants(self, position):
        if position == self.Position.TEACHER:
            return self.requester, self.other_user
        return self.other_user, self.requester

    @transaction.atomic
    def save(self) -> EducationalRelationship:
        teacher, student = self._participants(self.cleaned_data["position"])
        relationship, _ = EducationalRelationship.objects.update_or_create(
            teacher=teacher,
            student=student,
            defaults={
                "requested_by": self.requester,
                "status": MembershipStatus.PENDING,
            },
        )
        return relationship


class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ("name", "description")


class ClassroomMemberForm(forms.Form):
    email = forms.EmailField(label="E-mail do usuário")
    role = forms.ChoiceField(label="Papel na turma", choices=ClassroomMembership.Role.choices)

    def __init__(self, *args, classroom, inviter, **kwargs):
        super().__init__(*args, **kwargs)
        self.classroom = classroom
        self.inviter = inviter
        self.invited_user = None

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        try:
            self.invited_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise forms.ValidationError("Nenhum usuário foi encontrado com este e-mail.") from exc
        if self.invited_user.is_system_admin:
            raise forms.ValidationError("Contas de sistema não podem participar de turmas.")
        if ClassroomMembership.objects.filter(
            classroom=self.classroom,
            user=self.invited_user,
            status__in=(MembershipStatus.PENDING, MembershipStatus.ACTIVE),
        ).exists():
            raise forms.ValidationError("Este usuário já participa ou possui um convite pendente.")
        return email

    def save(self) -> ClassroomMembership:
        membership, _ = ClassroomMembership.objects.update_or_create(
            classroom=self.classroom,
            user=self.invited_user,
            defaults={
                "role": self.cleaned_data["role"],
                "status": MembershipStatus.PENDING,
                "invited_by": self.inviter,
            },
        )
        return membership


class SelfAssessmentForm(forms.ModelForm):
    SCALE_CHOICES = (
        (1, "1 — Muito baixo"),
        (2, "2 — Baixo"),
        (3, "3 — Regular"),
        (4, "4 — Bom"),
        (5, "5 — Muito bom"),
    )

    focus = forms.TypedChoiceField(label="Foco", choices=SCALE_CHOICES, coerce=int)
    organization = forms.TypedChoiceField(label="Organização", choices=SCALE_CHOICES, coerce=int)
    comprehension = forms.TypedChoiceField(label="Compreensão", choices=SCALE_CHOICES, coerce=int)
    motivation = forms.TypedChoiceField(label="Motivação", choices=SCALE_CHOICES, coerce=int)

    class Meta:
        model = SelfAssessment
        fields = ("focus", "organization", "comprehension", "motivation", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}
