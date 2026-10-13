from django import forms
from django.core.exceptions import ValidationError
from .bank_access import teaching_organizations
from .models import QuestionBankItem


class TeacherSharingMixin:
    """Sharing is opt-in; browser-supplied institution IDs are never trusted."""
    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sharing_owner = owner
        organizations = teaching_organizations(owner)
        item = getattr(self, 'instance', None)
        self.imported_item = bool(item and getattr(item, 'source_key', ''))
        if self.imported_item:
            return
        self.fields['share_with_institution'] = forms.BooleanField(
            label='Compartilhar no banco de questões da instituição', required=False,
            initial=bool(item and getattr(item, 'organization_id', None)),
            help_text='Desmarcada: somente seu banco pessoal. Marcada: os professores da instituição podem usar; o gestor decide a liberação externa.',
            disabled=not organizations.exists(),
        )
        self.fields['sharing_organization'] = forms.ModelChoiceField(
            label='Instituição do compartilhamento', queryset=organizations, required=False,
            initial=getattr(item, 'organization_id', None),
        )
        if organizations.count() <= 1:
            self.fields['sharing_organization'].widget = forms.HiddenInput()
            self.fields['sharing_organization'].initial = organizations.first()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('share_with_institution'):
            organization = cleaned.get('sharing_organization')
            organizations = teaching_organizations(self.sharing_owner)
            if organization is None and organizations.count() == 1:
                organization = organizations.first()
                cleaned['sharing_organization'] = organization
            if organization is None:
                self.add_error('sharing_organization', 'Escolha uma instituição em que você é professor.')
        return cleaned

    def apply_sharing(self, item, owner):
        if not self.imported_item:
            organization = self.cleaned_data.get('sharing_organization') if self.cleaned_data.get('share_with_institution') else None
            if organization and not teaching_organizations(owner).filter(pk=organization.pk).exists():
                raise ValidationError('Você não pode compartilhar nesta instituição.')
            item.organization = organization
        # Content edits and withdrawal revoke the manager's earlier decision.
        item.external_visibility = QuestionBankItem.Visibility.INSTITUTION
        item.sharing_approved_by = None
        item.sharing_approved_at = None
        return item
