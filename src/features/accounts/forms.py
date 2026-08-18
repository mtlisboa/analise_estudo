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
