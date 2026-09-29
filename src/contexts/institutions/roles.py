from dataclasses import dataclass


@dataclass(frozen=True)
class Workspace:
    slug: str
    title: str
    description: str


WORKSPACES = {
    'TEACHER': Workspace('professor', 'Professor', 'Acompanhe suas turmas e as atividades de ensino.'),
    'STUDENT': Workspace('aluno', 'Aluno', 'Consulte suas turmas e as atividades publicadas.'),
    'MANAGER': Workspace('gestor', 'Gestor', 'Acompanhe a estrutura e os acessos da instituição.'),
    'OPERATOR': Workspace('operador', 'Operador', 'Consulte os registros institucionais para apoiar a rotina administrativa.'),
    'GUARDIAN': Workspace('responsavel', 'Responsável', 'Espaço de acompanhamento dos alunos sob sua responsabilidade.'),
}


def workspace_for(account):
    # Preserve the existing administrator account and its exclusive permissions.
    return WORKSPACES.get('MANAGER' if account.role == 'ADMIN' else account.role)
