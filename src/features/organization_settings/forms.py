from django import forms
from django.db import transaction

from features.users_manager.models import Organization, OrganizationMembership


class OrganizationSettingsForm(forms.ModelForm):
    is_teacher = forms.BooleanField(label="Participar como professor", required=False)
    is_student = forms.BooleanField(label="Participar como aluno", required=False)

    class Meta:
        model = Organization
        fields = ("name", "description")

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.membership = OrganizationMembership.objects.filter(
            organization=self.instance,
            user=owner,
        ).first()
        if not self.is_bound and self.membership:
            self.initial["is_teacher"] = self.membership.is_teacher
            self.initial["is_student"] = self.membership.is_student

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("is_teacher") and not cleaned_data.get("is_student"):
            raise forms.ValidationError("Escolha pelo menos um papel: professor ou aluno.")
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        organization = super().save(commit=commit)
        membership, _ = OrganizationMembership.objects.get_or_create(
            organization=organization,
            user=self.owner,
            defaults={
                "is_teacher": self.cleaned_data["is_teacher"],
                "is_student": self.cleaned_data["is_student"],
                "added_by": self.owner,
            },
        )
        membership.is_teacher = self.cleaned_data["is_teacher"]
        membership.is_student = self.cleaned_data["is_student"]
        membership.save(update_fields=("is_teacher", "is_student"))
        return organization
