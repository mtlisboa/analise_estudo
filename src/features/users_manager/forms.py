from django import forms
from django.contrib.auth import get_user_model
from django.db import models, transaction

from .models import (
    Classroom,
    ClassroomMembership,
    ClassroomTest,
    EducationalRelationship,
    MembershipStatus,
    Organization,
    OrganizationMembership,
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


class OrganizationForm(forms.ModelForm):
    is_teacher = forms.BooleanField(label="Quero participar como professor", required=False)
    is_student = forms.BooleanField(label="Quero participar como aluno", required=False)

    class Meta:
        model = Organization
        fields = ("name", "description")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["is_teacher"] = True

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("is_teacher") and not cleaned_data.get("is_student"):
            raise forms.ValidationError("Escolha pelo menos um papel: professor ou aluno.")
        return cleaned_data


class OrganizationMemberForm(forms.Form):
    email = forms.EmailField(label="E-mail do usuário")
    is_teacher = forms.BooleanField(label="Professor", required=False)
    is_student = forms.BooleanField(label="Aluno", required=False)

    def __init__(self, *args, organization, added_by, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.added_by = added_by
        self.member_user = None

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        try:
            self.member_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise forms.ValidationError("Nenhum usuário foi encontrado com este e-mail.") from exc
        if self.member_user.is_system_admin:
            raise forms.ValidationError("Contas de sistema não podem participar de organizações.")
        if OrganizationMembership.objects.filter(
            organization=self.organization,
            user=self.member_user,
        ).exists():
            raise forms.ValidationError("Este usuário já pertence à organização.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("is_teacher") and not cleaned_data.get("is_student"):
            raise forms.ValidationError("Marque pelo menos um papel: professor ou aluno.")
        return cleaned_data

    def save(self) -> OrganizationMembership:
        return OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member_user,
            is_teacher=self.cleaned_data["is_teacher"],
            is_student=self.cleaned_data["is_student"],
            added_by=self.added_by,
        )


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
        organization_membership = OrganizationMembership.objects.filter(
            organization=self.classroom.organization,
            user=self.invited_user,
        ).first()
        if not organization_membership:
            raise forms.ValidationError("Adicione o usuário à organização antes de incluí-lo na turma.")
        if ClassroomMembership.objects.filter(
            classroom=self.classroom,
            user=self.invited_user,
            status__in=(MembershipStatus.PENDING, MembershipStatus.ACTIVE),
        ).exists():
            raise forms.ValidationError("Este usuário já participa ou possui um convite pendente.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if not self.invited_user or "email" not in cleaned_data or "role" not in cleaned_data:
            return cleaned_data
        membership = OrganizationMembership.objects.get(
            organization=self.classroom.organization,
            user=self.invited_user,
        )
        role = cleaned_data["role"]
        if role == ClassroomMembership.Role.TEACHER and not membership.is_teacher:
            raise forms.ValidationError("Este membro não possui a flag de professor na organização.")
        if role == ClassroomMembership.Role.STUDENT and not membership.is_student:
            raise forms.ValidationError("Este membro não possui a flag de aluno na organização.")
        return cleaned_data

    def save(self) -> ClassroomMembership:
        membership, _ = ClassroomMembership.objects.update_or_create(
            classroom=self.classroom,
            user=self.invited_user,
            defaults={
                "role": self.cleaned_data["role"],
                "status": MembershipStatus.ACTIVE,
                "invited_by": self.inviter,
            },
        )
        return membership


class ClassroomTestForm(forms.ModelForm):
    class Meta:
        model = ClassroomTest
        fields = ("title", "instructions", "max_score", "is_published")
        widgets = {"instructions": forms.Textarea(attrs={"rows": 5})}


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
