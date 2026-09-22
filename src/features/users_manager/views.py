from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ClassroomForm,
    ClassroomGroupForm,
    ClassroomMemberForm,
    ClassroomTestForm,
    OrganizationForm,
    OrganizationMemberForm,
    RelationshipRequestForm,
    SchoolApplicationForm,
    SelfAssessmentForm,
)
from .models import (
    Classroom,
    ClassroomGroup,
    ClassroomMembership,
    EducationalRelationship,
    InstitutionDataExport,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    SchoolVerificationDocument,
)
from .permissions import (
    accessible_group_ids,
    can_manage_classroom,
    can_manage_organization,
    can_view_classroom,
    has_teacher_role,
    visible_classrooms,
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
                "member_count": len(organization.memberships.all())
                if organization.owner_id == request.user.pk
                else ClassroomMembership.objects.filter(
                    classroom__in=visible_classrooms(
                        request.user,
                        organization=organization,
                    ),
                    status=MembershipStatus.ACTIVE,
                )
                .values("user_id")
                .distinct()
                .count(),
                "group_count": sum(
                    group.is_active for group in organization.classroom_groups.all()
                )
                if organization.owner_id == request.user.pk
                else len(accessible_group_ids(request.user, organization)),
            }
        )
    return render(
        request,
        "users_manager/dashboard.html",
        {
            "institution_cards": institution_cards,
            "can_request_school": request.user.is_manager,
            "school_applications": request.user.school_applications.select_related(
                "approved_school__organization"
            ).all(),
        },
    )


@login_required
def create_school_application(request: HttpRequest) -> HttpResponse:
    if not request.user.is_manager:
        return HttpResponseForbidden("Somente gestores podem solicitar o cadastro de escolas.")
    form = SchoolApplicationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save_for(request.user)
        messages.success(
            request,
            "Solicitação enviada. A escola será criada após a aprovação do sysadmin.",
        )
        return redirect("users-manager:dashboard")
    return render(
        request,
        "users_manager/school_application_form.html",
        {"form": form},
    )


@login_required
def download_school_document(request: HttpRequest, pk: int) -> FileResponse:
    if not request.user.is_system_admin:
        return HttpResponseForbidden("Somente o sysadmin pode acessar estes documentos.")
    document = get_object_or_404(SchoolVerificationDocument, pk=pk)
    return FileResponse(
        document.file.open("rb"),
        as_attachment=True,
        filename=document.original_name,
    )


@login_required
def download_institution_export(request: HttpRequest, pk: int) -> FileResponse:
    if not request.user.is_system_admin:
        return HttpResponseForbidden("Somente o sysadmin pode acessar estas exportações.")
    export = get_object_or_404(InstitutionDataExport, pk=pk)
    return FileResponse(
        export.file.open("rb"),
        as_attachment=True,
        filename=export.file.name.rsplit("/", 1)[-1],
        content_type="text/csv; charset=utf-8",
    )


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
    can_manage = can_manage_organization(request.user, organization)
    can_create_classroom = can_manage or bool(membership and membership.is_teacher)
    groups = organization.classroom_groups.filter(is_active=True, parent__isnull=True)
    classroom_queryset = Classroom.objects.filter(is_active=True)
    if not can_manage:
        groups = groups.filter(pk__in=accessible_group_ids(request.user, organization))
        classroom_queryset = visible_classrooms(
            request.user,
            organization=organization,
        )
    return render(
        request,
        "users_manager/organization_detail.html",
        {
            "organization": organization,
            "organization_memberships": organization.memberships.select_related("user", "added_by"),
            "classroom_groups": groups.prefetch_related(
                Prefetch(
                    "classrooms",
                    queryset=classroom_queryset,
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

    can_manage = can_manage_organization(request.user, organization)
    can_create_classroom = can_manage or bool(membership and membership.is_teacher)
    classrooms = group.classrooms.filter(is_active=True)
    child_groups = group.children.filter(is_active=True)
    if not can_manage:
        group_ids = accessible_group_ids(request.user, organization)
        if group.pk not in group_ids:
            return HttpResponseForbidden("Você não possui acesso a este grupo de turmas.")
        child_groups = child_groups.filter(pk__in=group_ids)
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
            "can_create_classroom": can_create_classroom,
        },
    )


@login_required
def create_classroom_group(request: HttpRequest, organization_pk: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=organization_pk, is_active=True)
    can_manage = can_manage_organization(request.user, organization)
    if not can_manage and not has_teacher_role(request.user, organization):
        return HttpResponseForbidden(
            "Somente gestores e professores da organização podem criar grupos."
        )
    initial = None
    if request.method == "GET" and request.GET.get("parent"):
        initial = {"parent": request.GET["parent"]}
    parent_queryset = organization.classroom_groups.filter(is_active=True)
    if not can_manage:
        parent_queryset = parent_queryset.filter(
            pk__in=accessible_group_ids(request.user, organization)
        )
    form = ClassroomGroupForm(
        request.POST or None,
        organization=organization,
        parent_queryset=parent_queryset,
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
    if not can_manage_organization(request.user, organization):
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
    can_manage = can_manage_organization(request.user, organization)
    is_teacher = has_teacher_role(request.user, organization)
    if not can_manage and not is_teacher:
        return HttpResponseForbidden(
            "Somente gestores e professores da organização podem criar turmas."
        )
    if group is not None and not can_manage:
        if group.pk not in accessible_group_ids(request.user, organization):
            return HttpResponseForbidden("Você não possui acesso a este grupo de turmas.")
    if group is None:
        available_groups = organization.classroom_groups.filter(is_active=True)
        if not can_manage:
            available_groups = available_groups.filter(
                pk__in=accessible_group_ids(request.user, organization)
            )
        group = available_groups.first()
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
        if is_teacher:
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


@login_required
def classroom_detail(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(
        Classroom.objects.select_related("organization", "group"),
        pk=pk,
        is_active=True,
    )
    can_manage = can_manage_classroom(request.user, classroom)
    if not can_view_classroom(request.user, classroom):
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
    if not can_manage_classroom(request.user, classroom):
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
    if not can_manage_classroom(request.user, classroom):
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
