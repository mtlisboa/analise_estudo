from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import User
from .institutional import ROLES, normalize_code, find_school, attach_membership
from django.db import transaction


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Usuário",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def confirm_login_allowed(self, user: User) -> None:
        super().confirm_login_allowed(user)
        if user.is_system_admin:
            raise ValidationError(
                "Contas de sistema devem utilizar o acesso exclusivo de sysadmin.",
                code="sysadmin_separate_login",
            )


class SysAdminLoginForm(LoginForm):
    def confirm_login_allowed(self, user: User) -> None:
        AuthenticationForm.confirm_login_allowed(self, user)
        if not user.is_system_admin:
            raise ValidationError(
                "Este acesso é exclusivo para administradores de sistema.",
                code="sysadmin_only",
            )


class SignUpForm(UserCreationForm):
    email = forms.EmailField(label="E-mail", required=True)
    registration_role = forms.ChoiceField(label='Tipo de conta',
        choices=ROLES + [('PERSONAL', 'Conta pessoal, sem instituição')], initial='STUDENT', required=False)
    institutional_code = forms.CharField(label='Código institucional', max_length=20, required=False,
        help_text='Obrigatório para estudante ou professor. Solicite o código à sua instituição.',
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'placeholder': 'LUM-…', 'autocapitalize': 'characters'}))
    field_order = ['registration_role', 'institutional_code', 'username', 'email', 'password1', 'password2']

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este e-mail já está em uso.")
        return email


    def clean(self):
        data = super().clean()
        role = data.get('registration_role') or 'PERSONAL'
        data['registration_role'] = role
        code = normalize_code(data.get('institutional_code', ''))
        data['institutional_code'] = code
        if role in dict(ROLES):
            if not code:
                self.add_error('institutional_code', 'Informe o código fornecido pela instituição.')
            else:
                try:
                    find_school(code)
                except ValidationError as exc:
                    self.add_error('institutional_code', exc)
        elif code:
            self.add_error('registration_role', 'Para usar um código, selecione estudante ou professor.')
        return data

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            raise ValueError('O cadastro deve salvar a conta e o vínculo na mesma transação.')
        user = super().save(commit=False)
        role = self.cleaned_data['registration_role']
        if role in dict(ROLES):
            user.onboarding_role = role
            # Revalidate before creating the account in case the code was disabled.
            find_school(self.cleaned_data['institutional_code'], lock=True)
        user.save()
        if role in dict(ROLES):
            attach_membership(user, self.cleaned_data['institutional_code'], role)
        return user


class OnboardingForm(forms.ModelForm):
    app_goal_details = forms.CharField(
        label="Conte um pouco mais (opcional)",
        required=False,
        max_length=240,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Ex.: passar no ENEM, acompanhar uma turma ou criar uma rotina de estudos.",
            }
        ),
    )

    class Meta:
        model = User
        fields = (
            "onboarding_role",
            "discovery_source",
            "education_level",
            "app_goal",
            "app_goal_details",
        )
        labels = {
            "onboarding_role": "Quem é você?",
            "discovery_source": "Como conheceu a Lumini?",
            "education_level": "Qual é o seu grau de escolaridade?",
            "app_goal": "Qual é o seu principal objetivo com o app?",
        }
        widgets = {
            "onboarding_role": forms.RadioSelect,
            "discovery_source": forms.Select,
            "education_level": forms.Select,
            "app_goal": forms.Select,
        }

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if cleaned_data.get("app_goal") == User.AppGoal.OTHER and not cleaned_data.get(
            "app_goal_details"
        ):
            self.add_error(
                "app_goal_details",
                "Descreva brevemente o seu objetivo.",
            )
        return cleaned_data



class ProfileForm(forms.ModelForm):
    email = forms.EmailField(label="E-mail", required=True)
    current_password = forms.CharField(
        label="Senha atual", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        help_text="Obrigatória somente para alterar seu e-mail ou nome de usuário.",
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")
        labels = {"first_name": "Nome", "last_name": "Sobrenome", "username": "Nome de usuário"}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Este e-mail já está em uso.")
        return email

    def clean(self):
        data = super().clean()
        if {"username", "email"}.intersection(self.changed_data):
            if not self.instance.check_password(data.get("current_password", "")):
                self.add_error("current_password", "Informe sua senha atual para alterar estes dados.")
        return data


class PreferencesForm(OnboardingForm):
    class Meta(OnboardingForm.Meta):
        fields = ("theme_preference", "onboarding_role", "education_level", "app_goal", "app_goal_details")
        labels = {**OnboardingForm.Meta.labels, "onboarding_role": "Seu perfil", "theme_preference": "Tema da interface"}
        widgets = {**OnboardingForm.Meta.widgets, "onboarding_role": forms.Select}


class AvatarForm(forms.Form):
    photo = forms.FileField(label="Escolher foto", widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))

    def clean_photo(self):
        from io import BytesIO
        import warnings
        from PIL import Image, ImageOps, UnidentifiedImageError
        from django.core.files.base import ContentFile

        photo = self.cleaned_data["photo"]
        if photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("A foto deve ter no máximo 5 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(photo) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP"}:
                        raise forms.ValidationError("Envie uma imagem JPG, PNG ou WebP.")
                    if image.width * image.height > 16_000_000:
                        raise forms.ValidationError("A imagem deve ter no máximo 16 megapixels.")
                    image.load()
                    image = ImageOps.exif_transpose(image).convert("RGBA")
                    image.thumbnail((512, 512))
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    output = BytesIO()
                    background.save(output, "JPEG", quality=88)
                    return ContentFile(output.getvalue(), name="avatar.jpg")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError("Não foi possível ler a imagem. Envie uma foto válida.")

