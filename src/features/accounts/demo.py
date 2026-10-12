"""Explicit identities managed by the demonstration seed command."""
import os

DEMO_DOMAIN = 'demo.lumini.local'
DEMO_ROLES = {
    'demo_admin': 'ADMIN',
    'demo_gestor': 'MANAGER',
    'demo_operador': 'OPERATOR',
    'demo_professor': 'TEACHER',
    'demo_professor_aux': 'TEACHER',
    'demo_aluno': 'STUDENT',
    'demo_responsavel': 'GUARDIAN',
}


def permits_demo_alias(user, identity):
    return (
        os.getenv('DEPLOY_MODE') == 'MOCK'
        and DEMO_ROLES.get(user.username) == identity.role
        and identity.registration == user.username
        and identity.email == f'{user.username}@{DEMO_DOMAIN}'
        and getattr(getattr(identity.organization, 'school', None), 'email_domain', None) == DEMO_DOMAIN
    )
