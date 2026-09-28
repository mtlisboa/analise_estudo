"""Provision institutional login identities, not external email mailboxes."""
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q

from features.users_manager.models import InstitutionalAccount, Organization, OrganizationMembership, School


def normalize_domain(value):
    domain = value.strip().lower()
    if len(domain) > 100 or '@' in domain:
        raise ValidationError('Informe apenas o domínio, como escola.edu.br (até 100 caracteres).')
    validate_email('conta@' + domain)
    return domain


def normalize_registration(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,39}', value):
        raise ValidationError('Use até 40 letras sem acento, números, pontos, hífens ou sublinhados; comece com letra ou número.')
    return value


def available_email(email):
    email = email.strip().lower()
    validate_email(email)
    if len(email) > 150:
        raise ValidationError('O e-mail deve ter até 150 caracteres.')
    User = get_user_model()
    if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists() or InstitutionalAccount.objects.filter(email__iexact=email).exists():
        raise ValidationError('Este e-mail já pertence a uma conta. Nenhuma conta existente será substituída.')
    return email


def can_provision(user, organization):
    return user.is_authenticated and (user.is_system_admin or (
        organization.is_active and organization.owner_id == user.pk and
        InstitutionalAccount.objects.filter(user=user, organization=organization, role='ADMIN').exists()))


def _new_identity(organization, actor, registration, role, password, first_name='', last_name='', domain=None):
    registration = normalize_registration(registration)
    email = available_email(f'{registration}@{domain or organization.school.email_domain}')
    if InstitutionalAccount.objects.filter(organization=organization, registration=registration).exists():
        raise ValidationError('Este registro já existe na instituição.')
    User = get_user_model()
    user = User(username=email, email=email, first_name=first_name, last_name=last_name,
                must_change_password=True, onboarding_role=role if role != 'ADMIN' else 'MANAGER')
    validate_password(password, user)
    user.set_password(password)
    user.save()
    identity = InstitutionalAccount.objects.create(user=user, organization=organization, registration=registration,
        email=email, role=role, created_by=actor)
    if role != 'ADMIN':
        OrganizationMembership.objects.create(organization=organization, user=user,
            is_student=role == 'STUDENT', is_teacher=role == 'TEACHER', added_by=actor)
    return identity


@transaction.atomic
def provision_administrator(organization, actor, *, domain, registration, password, first_name='', last_name=''):
    if not actor.is_authenticated or not actor.is_system_admin:
        raise PermissionDenied('Somente o administrador da plataforma pode criar o acesso administrativo.')
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    school = School.objects.select_for_update().get(organization=organization)
    if not organization.is_active:
        raise ValidationError('A organização está desativada.')
    if organization.institutional_accounts.filter(role='ADMIN').exists():
        raise ValidationError('Esta instituição já possui acesso administrativo. Use a redefinição de senha.')
    domain = normalize_domain(domain)
    if school.email_domain and school.email_domain != domain:
        raise ValidationError('Use o domínio já configurado para esta instituição.')
    if School.objects.filter(email_domain__iexact=domain).exclude(pk=school.pk).exists():
        raise ValidationError('Este domínio já está configurado em outra instituição.')
    identity = _new_identity(organization, actor, registration, 'ADMIN', password, first_name, last_name, domain)
    school.email_domain = domain
    school.save(update_fields=['email_domain'])
    organization.owner = identity.user
    organization.save(update_fields=['owner'])
    return identity


@transaction.atomic
def provision_member(organization, actor, *, registration, role, password, first_name='', last_name=''):
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    if not can_provision(actor, organization):
        raise PermissionDenied('Somente o administrativo desta instituição pode cadastrar acessos.')
    if not organization.is_active or not School.objects.filter(organization=organization).exclude(email_domain__isnull=True).exclude(email_domain='').exists():
        raise ValidationError('Configure o domínio institucional antes de cadastrar usuários.')
    if role not in ('STUDENT', 'TEACHER'):
        raise ValidationError('Selecione estudante ou professor.')
    return _new_identity(organization, actor, registration, role, password, first_name, last_name)


@transaction.atomic
def reset_institutional_password(identity, actor, password):
    identity = InstitutionalAccount.objects.select_for_update().select_related('organization', 'user').get(pk=identity.pk)
    if not can_provision(actor, identity.organization) or (identity.role == 'ADMIN' and not actor.is_system_admin):
        raise PermissionDenied('Você não pode redefinir esta senha.')
    validate_password(password, identity.user)
    identity.user.set_password(password)
    identity.user.must_change_password = True
    identity.user.save(update_fields=['password', 'must_change_password'])
