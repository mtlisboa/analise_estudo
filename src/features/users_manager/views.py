from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .access import active_classroom_memberships, managed_classrooms, visible_classrooms

from .forms import (
    ClassroomForm,
    ClassroomMemberForm,
    ClassroomTestForm,
    OrganizationForm,
    OrganizationMemberForm,
    SelfAssessmentForm,
)
from .models import (
    Classroom,
    ClassroomMembership,
    MembershipStatus,
    Organization,
    OrganizationMembership,
)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    organizations = list(
        Organization.objects.filter(
            Q(owner=request.user) | Q(memberships__user=request.user),
            is_active=True,
        )
        .prefetch_related("memberships")
        .distinct()
    )
    institution_cards = []
    for organization in organizations:
        membership = next(
            (
                item
                for item in organization.memberships.all()
                if item.user_id == request.user.pk
            ),
            None,
        )
        roles = []
        if organization.owner_id == request.user.pk:
            roles.append("Gestor")
        if membership and membership.is_teacher:
            roles.append("Professor")
        if membership and membership.is_student:
            roles.append("Aluno")
        institution_cards.append(
            {
                "organization": organization,
                "roles": roles,
                "member_count": len(organization.memberships.all()),
            }
        )
    return render(
        request,
        "users_manager/dashboard.html",
        {"institution_cards": institution_cards},
    )


def _can_manage_organization(user, organization: Organization) -> bool:
    return organization.owner_id == user.pk


def _organization_teacher_membership(user, organization: Organization):
    return OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
        is_teacher=True,
    ).first()


@login_required
@transaction.atomic
def create_organization(request: HttpRequest) -> HttpResponse:
    form = OrganizationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        organization = form.save(commit=False)
        organization.owner = request.user
        organization.save()
        OrganizationMembership.objects.create(
            organization=organization,
            user=request.user,
            is_teacher=form.cleaned_data["is_teacher"],
            is_student=form.cleaned_data["is_student"],
            added_by=request.user,
        )
        messages.success(request, "Organização criada com sucesso.")
        return redirect("users-manager:organization-detail", pk=organization.pk)
    return render(request, "users_manager/form.html", {"form": form, "title": "Nova organização"})


@login_required
def organization_detail(request: HttpRequest, pk: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=pk, is_active=True)
    membership = OrganizationMembership.objects.filter(
        organization=organization,
        user=request.user,
    ).first()
    if not membership and organization.owner_id != request.user.pk:
        return HttpResponseForbidden("Você não participa desta organização.")
    return render(
        request,
        "users_manager/organization_detail.html",
        {
            "organization": organization,
            "organization_memberships": organization.memberships.select_related("user", "added_by"),
            "classrooms": visible_classrooms(request.user).filter(organization=organization).select_related("owner"),
            "can_manage": _can_manage_organization(request.user, organization),
            "can_create_classroom": bool(membership and membership.is_teacher),
        },
    )


@login_required
def add_organization_member(request: HttpRequest, pk: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=pk, is_active=True)
    if not _can_manage_organization(request.user, organization):
        return HttpResponseForbidden("Somente o responsável pode adicionar membros.")
    form = OrganizationMemberForm(
        request.POST or None,
        organization=organization,
        added_by=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Membro adicionado à organização.")
        return redirect("users-manager:organization-detail", pk=organization.pk)
    return render(
        request,
        "users_manager/form.html",
        {"form": form, "title": f"Adicionar membro a {organization.name}", "back_url": reverse("users-manager:organization-detail", kwargs={"pk": organization.pk}), "back_label": organization.name},
    )


@login_required
def request_relationship(request: HttpRequest) -> HttpResponse:
    messages.info(request, "Os vínculos agora são gerenciados dentro das organizações.")
    return redirect("users-manager:dashboard")


@login_required
def decide_relationship(request: HttpRequest, pk: int, decision: str) -> HttpResponse:
    messages.info(request, "Os vínculos agora são gerenciados dentro das organizações.")
    return redirect("users-manager:dashboard")


@login_required
@transaction.atomic
def create_classroom(request: HttpRequest, organization_pk: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=organization_pk, is_active=True)
    if not _organization_teacher_membership(request.user, organization):
        return HttpResponseForbidden("Somente professores da organização podem criar turmas.")
    form = ClassroomForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        classroom = form.save(commit=False)
        classroom.organization = organization
        classroom.owner = request.user
        classroom.save()
        ClassroomMembership.objects.create(
            classroom=classroom,
            user=request.user,
            role=ClassroomMembership.Role.TEACHER,
            status=MembershipStatus.ACTIVE,
            invited_by=request.user,
        )
        messages.success(request, "Turma criada com sucesso.")
        return redirect("users-manager:classroom-detail", pk=classroom.pk)
    return render(
        request,
        "users_manager/form.html",
        {"form": form, "title": f"Nova turma em {organization.name}", "back_url": reverse("users-manager:organization-detail", kwargs={"pk": organization.pk}), "back_label": organization.name},
    )


def _can_manage_classroom(user, classroom: Classroom) -> bool:
    return managed_classrooms(user).filter(pk=classroom.pk).exists()


@login_required
def classroom_detail(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(Classroom, pk=pk, is_active=True, organization__is_active=True)
    can_manage = _can_manage_classroom(request.user, classroom)
    can_view = visible_classrooms(request.user).filter(pk=classroom.pk).exists()
    if not can_view:
        return HttpResponseForbidden("Você não participa desta turma.")
    return render(
        request,
        "users_manager/classroom_detail.html",
        {
            "classroom": classroom,
            "memberships": active_classroom_memberships().filter(classroom=classroom).select_related("user", "invited_by"),
            "tests": classroom.tests.filter(is_published=True)
            if not (can_manage or classroom.organization.owner_id == request.user.pk)
            else classroom.tests.all(),
            "can_manage": can_manage,
        },
    )


@login_required
def invite_classroom_member(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(Classroom, pk=pk, is_active=True, organization__is_active=True)
    if not _can_manage_classroom(request.user, classroom):
        return HttpResponseForbidden("Apenas professores da turma podem adicionar membros.")
    form = ClassroomMemberForm(
        request.POST or None,
        classroom=classroom,
        inviter=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Membro adicionado à turma.")
        return redirect("users-manager:classroom-detail", pk=classroom.pk)
    return render(
        request,
        "users_manager/form.html",
        {"form": form, "title": f"Adicionar membro a {classroom.name}", "back_url": reverse("users-manager:classroom-detail", kwargs={"pk": classroom.pk}), "back_label": classroom.name},
    )


@login_required
def create_classroom_test(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(Classroom, pk=pk, is_active=True, organization__is_active=True)
    if not _can_manage_classroom(request.user, classroom):
        return HttpResponseForbidden("Apenas professores da turma podem criar testes.")
    form = ClassroomTestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        classroom_test = form.save(commit=False)
        classroom_test.classroom = classroom
        classroom_test.created_by = request.user
        classroom_test.save()
        messages.success(request, "Teste criado com sucesso.")
        return redirect("users-manager:classroom-detail", pk=classroom.pk)
    return render(
        request,
        "users_manager/form.html",
        {"form": form, "title": f"Novo teste para {classroom.name}", "back_url": reverse("users-manager:classroom-detail", kwargs={"pk": classroom.pk}), "back_label": classroom.name},
    )


@login_required
def decide_classroom_invitation(request: HttpRequest, pk: int, decision: str) -> HttpResponse:
    messages.info(request, "Os vínculos agora são gerenciados dentro das organizações.")
    return redirect("users-manager:dashboard")


@login_required
def create_self_assessment(request: HttpRequest) -> HttpResponse:
    form = SelfAssessmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        assessment = form.save(commit=False)
        assessment.user = request.user
        assessment.save()
        messages.success(request, f"Autoavaliação salva. Resultado geral: {assessment.score}%.")
        return redirect("accounts:dashboard")
    return render(
        request,
        "users_manager/form.html",
        {"form": form, "title": "Nova autoavaliação", "back_url": reverse("accounts:dashboard"), "back_label": "meu painel"},
    )
