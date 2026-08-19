from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from features.users_manager.models import Organization

from .forms import OrganizationSettingsForm


@login_required
def organization_settings(request: HttpRequest, pk: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=pk, is_active=True)
    if organization.owner_id != request.user.pk:
        return HttpResponseForbidden("Somente o criador pode alterar as configurações.")

    form = OrganizationSettingsForm(
        request.POST or None,
        instance=organization,
        owner=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Configurações da organização atualizadas.")
        return redirect("users-manager:organization-detail", pk=organization.pk)

    return render(
        request,
        "organization_settings/detail.html",
        {"form": form, "organization": organization},
    )
