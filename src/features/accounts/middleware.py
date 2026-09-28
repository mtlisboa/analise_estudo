from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin


class InstitutionalPasswordMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.user.is_authenticated and request.user.must_change_password:
            if request.resolver_match.view_name not in {'accounts:institutional-password', 'accounts:logout'}:
                return redirect('accounts:institutional-password')
