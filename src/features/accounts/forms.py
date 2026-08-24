from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import User


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

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este e-mail já está em uso.")
        return email


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
