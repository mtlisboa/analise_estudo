from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from features.accounts.institutional import can_provision, provision_administrator, provision_member, reset_institutional_password
from .models import Organization, InstitutionalAccount
from .institutional_forms import InstitutionAdministratorForm, InstitutionalUserForm, TemporaryPasswordForm


def managed_organization(user, pk):
    organization = get_object_or_404(Organization.objects.select_related('school'), pk=pk, is_active=True)
    if not can_provision(user, organization):
        raise PermissionDenied('Você não administra esta instituição.')
    if not hasattr(organization, 'school'):
        raise PermissionDenied('A organização precisa ser cadastrada como instituição pela plataforma.')
    return organization


@login_required
@never_cache
@sensitive_post_parameters('password', 'password_confirm')
@require_http_methods(['GET', 'POST'])
def accounts(request, pk):
    organization = managed_organization(request.user, pk)
    has_admin = organization.institutional_accounts.filter(role='ADMIN').exists()
    if not has_admin:
        if not request.user.is_system_admin:
            raise PermissionDenied
        form = InstitutionAdministratorForm(request.POST if request.method == 'POST' else None,
            initial={'domain': organization.school.email_domain or ''})
    else:
        form = InstitutionalUserForm(request.POST if request.method == 'POST' else None, organization=organization)
    if request.method == 'POST' and form.is_valid():
        data = {key: value for key, value in form.cleaned_data.items() if key != 'password_confirm'}
        try:
            service = provision_member if has_admin else provision_administrator
            account = service(organization, request.user, **data)
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, exc if isinstance(exc, ValidationError) else 'E-mail, registro ou domínio já está em uso. Atualize a página e confira os dados.')
        else:
            messages.success(request, f'Acesso criado: {account.email}. Entregue a senha provisória à pessoa; ela deverá alterá-la no primeiro acesso.')
            return redirect('users-manager:institutional-accounts', pk=organization.pk)
    return render(request, 'users_manager/institutional_accounts.html', {
        'organization': organization, 'form': form, 'has_admin': has_admin,
        'accounts': organization.institutional_accounts.select_related('user')})


@login_required
@never_cache
@sensitive_post_parameters('password', 'password_confirm')
@require_http_methods(['GET', 'POST'])
def reset_password(request, pk, account_pk):
    organization = managed_organization(request.user, pk)
    account = get_object_or_404(InstitutionalAccount, pk=account_pk, organization=organization)
    if account.role == 'ADMIN' and not request.user.is_system_admin:
        raise PermissionDenied('Somente a plataforma pode redefinir a senha do administrativo.')
    form = TemporaryPasswordForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            reset_institutional_password(account, request.user, form.cleaned_data['password'])
        except ValidationError as exc:
            form.add_error('password', exc)
        else:
            messages.success(request, 'Senha provisória atualizada. A troca será obrigatória no próximo acesso.')
            return redirect('users-manager:institutional-accounts', pk=organization.pk)
    return render(request, 'users_manager/form.html', {'form': form, 'title': f'Redefinir senha de {account.email}'})
