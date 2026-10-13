from django.http import Http404
from .services import authorized
from .views import data


def home(request):
    match = request.resolver_match
    if not request.user.is_authenticated or not match or match.view_name not in (
        'institutions:professor','institutions:aluno','institutions:operador','institutions:responsavel',
        'institutions:gestor','family:index'):
        return {}
    account = getattr(request.user,'institutional_account',None)
    if not account or not account.organization.is_active:
        return {}
    selected = None
    try:
        if request.GET.get('chat'):
            selected = authorized(account,int(request.GET['chat']))
    except (ValueError,Http404):
        pass
    return {'communication_home':True,**data(account,selected,request.GET.get('contact_q',''))}
