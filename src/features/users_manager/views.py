from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ClassroomForm,
    ClassroomGroupForm,
    ClassroomMemberForm,
    ClassroomTestForm,
    OrganizationForm,
    OrganizationMemberForm,
    RelationshipRequestForm,
    SelfAssessmentForm,
)
from .models import (
    Classroom,
    ClassroomGroup,
    ClassroomMembership,
    EducationalRelationship,
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
        .prefetch_related("memberships", "classroom_groups")
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
                "group_count": sum(
                    group.is_active for group in organization.classroom_groups.all()
                ),
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


def _visible_group_ids(user, organization: Organization) -> set[int]:
    groups = list(
        organization.classroom_groups.filter(is_active=True).values("id", "parent_id")
    )
    parent_by_id = {item["id"]: item["parent_id"] for item in groups}
    visible_ids = set(
        ClassroomMembership.objects.filter(
            user=user,
            status=MembershipStatus.ACTIVE,
            classroom__organization=organization,
            classroom__is_active=True,
            classroom__group__is_active=True,
        ).values_list("classroom__group_id", flat=True)
    )
    pending = list(visible_ids)
    while pending:
        parent_id = parent_by_id.get(pending.pop())
        if parent_id and parent_id not in visible_ids:
            visible_ids.add(parent_id)
            pending.append(parent_id)
    return visible_ids


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
    can_manage = _can_manage_organization(request.user, organization)
    can_create_classroom = bool(membership and membership.is_teacher)
    groups = organization.classroom_groups.filter(is_active=True, parent__isnull=True)
    visible_classrooms = Classroom.objects.filter(is_active=True)
    if not can_manage and not can_create_classroom:
        groups = groups.filter(pk__in=_visible_group_ids(request.user, organization))
        visible_classrooms = visible_classrooms.filter(
            memberships__user=request.user,
            memberships__status=MembershipStatus.ACTIVE,
        ).distinct()
    return render(
        request,
        "users_manager/organization_detail.html",
        {
            "organization": organization,
            "organization_memberships": organization.memberships.select_related("user", "added_by"),
            "classroom_groups": groups.prefetch_related(
                Prefetch(
                    "classrooms",
                    queryset=visible_classrooms,
                    to_attr="visible_classrooms",
                )
            ),
            "can_manage": can_manage,
            "can_create_classroom": can_create_classroom,
        },
    )


@login_required
def classroom_group_detail(request: HttpRequest, pk: int) -> HttpResponse:
    group = get_object_or_404(
        ClassroomGroup.objects.select_related("organization", "parent"),
        pk=pk,
        is_active=True,
        organization__is_active=True,
    )
    organization = group.organization
    membership = OrganizationMembership.objects.filter(
        organization=organization,
        user=request.user,
    ).first()
    if not membership and organization.owner_id != request.user.pk:
        return HttpResponseForbidden("Você não participa desta organização.")

    can_manage = organization.owner_id == request.user.pk or bool(
        membership and membership.is_teacher
    )
    classrooms = group.classrooms.filter(is_active=True)
    child_groups = group.children.filter(is_active=True)
    if not can_manage:
        visible_group_ids = _visible_group_ids(request.user, organization)
        child_groups = child_groups.filter(pk__in=visible_group_ids)
        classrooms = classrooms.filter(
            memberships__user=request.user,
            memberships__status=MembershipStatus.ACTIVE,
        ).distinct()
    classroom_list = list(classrooms.select_related("owner").prefetch_related("memberships"))
    classroom_sections = [
        {
            "key": shift,
            "label": label,
            "classrooms": [item for item in classroom_list if item.shift == shift],
        }
        for shift, label in Classroom.Shift.choices
    ]
    classroom_sections = [section for section in classroom_sections if section["classrooms"]]
    return render(
        request,
        "users_manager/classroom_group_detail.html",
        {
            "group": group,
            "organization": organization,
            "classroom_sections": classroom_sections,
            "classroom_count": len(classroom_list),
            "child_groups": child_groups.prefetch_related("classrooms"),
            "can_create_classroom": can_manage,
        },
    )


@login_required
def create_classroom_group(request: HttpRequest, organization_pk: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=organization_pk, is_active=True)
    if not _organization_teacher_membership(request.user, organization):
        return HttpResponseForbidden("Somente professores da organização podem criar grupos.")
    initial = None
    if request.method == "GET" and request.GET.get("parent"):
        initial = {"parent": request.GET["parent"]}
    form = ClassroomGroupForm(
        request.POST or None,
        organization=organization,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        group.organization = organization
        group.created_by = request.user
        group.save()
        messages.success(request, "Grupo de turmas criado com sucesso.")
        return redirect("users-manager:classroom-group-detail", pk=group.pk)
    return render(
        request,
        "users_manager/form.html",
        {"form": form, "title": f"Novo grupo em {organization.name}"},
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
        {"form": form, "title": f"Adicionar membro a {organization.name}"},
    )


@login_required
def request_relationship(request: HttpRequest) -> HttpResponse:
    form = RelationshipRequestForm(request.POST or None, requester=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Solicitação de vínculo enviada.")
        return redirect("users-manager:dashboard")
    return render(request, "users_manager/form.html", {"form": form, "title": "Novo vínculo"})


@login_required
def decide_relationship(request: HttpRequest, pk: int, decision: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)
    if decision not in {"accept", "reject"}:
        raise Http404
    relationship = get_object_or_404(EducationalRelationship, pk=pk)
    if relationship.recipient_id != request.user.pk:
        return HttpResponseForbidden("Somente o destinatário pode responder à solicitação.")
    if relationship.status != MembershipStatus.PENDING:
        messages.info(request, "Esta solicitação já foi respondida.")
        return redirect("users-manager:dashboard")
    relationship.status = (
        MembershipStatus.ACTIVE if decision == "accept" else MembershipStatus.REJECTED
    )
    relationship.save(update_fields=("status", "updated_at"))
    messages.success(request, "Vínculo atualizado.")
    return redirect("users-manager:dashboard")


@login_required
@transaction.atomic
def create_classroom(
    request: HttpRequest,
    organization_pk: int | None = None,
    group_pk: int | None = None,
) -> HttpResponse:
    group = None
    if group_pk is not None:
        group = get_object_or_404(
            ClassroomGroup.objects.select_related("organization"),
            pk=group_pk,
            is_active=True,
            organization__is_active=True,
        )
        organization = group.organization
    else:
        organization = get_object_or_404(Organization, pk=organization_pk, is_active=True)
    if not _organization_teacher_membership(request.user, organization):
        return HttpResponseForbidden("Somente professores da organização podem criar turmas.")
    if group is None:
        group = organization.classroom_groups.filter(is_active=True).first()
        if group is None and request.method == "POST":
            group = ClassroomGroup.objects.create(
                name="Turmas gerais",
                organization=organization,
                created_by=request.user,
            )
        elif group is None:
            messages.info(request, "Crie um grupo antes de adicionar a primeira turma.")
            return redirect("users-manager:classroom-group-create", organization_pk=organization.pk)
    form = ClassroomForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        classroom = form.save(commit=False)
        classroom.organization = organization
        classroom.group = group
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
        {"form": form, "title": f"Nova turma em {group.name}"},
    )


def _can_manage_classroom(user, classroom: Classroom) -> bool:
    return bool(_organization_teacher_membership(user, classroom.organization)) and (
        classroom.owner_id == user.pk
        or ClassroomMembership.objects.filter(
            classroom=classroom,
            user=user,
            role=ClassroomMembership.Role.TEACHER,
            status=MembershipStatus.ACTIVE,
        ).exists()
    )


@login_required
def classroom_detail(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(
        Classroom.objects.select_related("organization", "group"),
        pk=pk,
        is_active=True,
    )
    can_manage = _can_manage_classroom(request.user, classroom)
    can_view = can_manage or ClassroomMembership.objects.filter(
        classroom=classroom,
        user=request.user,
        status=MembershipStatus.ACTIVE,
    ).exists()
    if not can_view:
        return HttpResponseForbidden("Você não participa desta turma.")
    return render(
        request,
        "users_manager/classroom_detail.html",
        {
            "classroom": classroom,
            "memberships": classroom.memberships.select_related("user", "invited_by"),
            "tests": classroom.tests.filter(is_published=True)
            if not can_manage
            else classroom.tests.all(),
            "can_manage": can_manage,
        },
    )


@login_required
def invite_classroom_member(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(Classroom, pk=pk, is_active=True)
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
        {"form": form, "title": f"Adicionar membro a {classroom.name}"},
    )


@login_required
def create_classroom_test(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(Classroom, pk=pk, is_active=True)
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
        {"form": form, "title": f"Novo teste para {classroom.name}"},
    )


@login_required
def decide_classroom_invitation(request: HttpRequest, pk: int, decision: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)
    if decision not in {"accept", "reject"}:
        raise Http404
    membership = get_object_or_404(ClassroomMembership, pk=pk, user=request.user)
    if membership.status != MembershipStatus.PENDING:
        messages.info(request, "Este convite já foi respondido.")
        return redirect("users-manager:dashboard")
    membership.status = (
        MembershipStatus.ACTIVE if decision == "accept" else MembershipStatus.REJECTED
    )
    membership.save(update_fields=("status",))
    messages.success(request, "Convite atualizado.")
    return redirect("users-manager:dashboard")


@login_required
def create_self_assessment(request: HttpRequest) -> HttpResponse:
    form = SelfAssessmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        assessment = form.save(commit=False)
        assessment.user = request.user
        assessment.save()
        messages.success(request, f"Autoavaliação salva. Resultado geral: {assessment.score}%.")
        return redirect("users-manager:dashboard")
    return render(
        request,
        "users_manager/form.html",
        {"form": form, "title": "Nova autoavaliação"},
    )
