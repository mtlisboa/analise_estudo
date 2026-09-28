from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from features.users_manager.models import InstitutionalAccount


class InstitutionalBackend(ModelBackend):
    def user_can_authenticate(self, user):
        if not super().user_can_authenticate(user):
            return False
        identity = InstitutionalAccount.objects.filter(user=user).select_related('organization').first()
        return not identity or identity.organization.is_active

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        value = username.strip()
        User = get_user_model()
        identity = InstitutionalAccount.objects.filter(email__iexact=value).select_related('user').first()
        if identity:
            user = identity.user
        else:
            user = User.objects.filter(username=value).first()
            if user is None and '@' in value:
                matches = list(User.objects.filter(email__iexact=value)[:2])
                user = matches[0] if len(matches) == 1 else None
            if user and InstitutionalAccount.objects.filter(user=user).exists():
                return None  # Managed accounts use their institutional address only.
        if user is None:
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
