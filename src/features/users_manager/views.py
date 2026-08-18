from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ClassroomForm,
    ClassroomMemberForm,
    RelationshipRequestForm,
    SelfAssessmentForm,
)
from .models import (
    Classroom,
    ClassroomMembership,
    EducationalRelationship,
    MembershipStatus,
)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    relationships = EducationalRelationship.objects.filter(
        Q(teacher=request.user) | Q(student=request.user)
    ).select_related("teacher", "student", "requested_by")
    memberships = ClassroomMembership.objects.filter(user=request.user).select_related(
        "classroom", "invited_by"
    )
    classrooms = Classroom.objects.filter(
        Q(owner=request.user)
        | Q(memberships__user=request.user, memberships__status=MembershipStatus.ACTIVE)
    ).distinct()
    return render(
        request,
        "users_manager/dashboard.html",
        {
            "relationships": relationships,
            "memberships": memberships,
            "classrooms": classrooms,
            "assessments": request.user.self_assessments.all()[:5],
        },
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
def create_classroom(request: HttpRequest) -> HttpResponse:
    form = ClassroomForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        classroom = form.save(commit=False)
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
    return render(request, "users_manager/form.html", {"form": form, "title": "Nova turma"})


def _can_manage_classroom(user, classroom: Classroom) -> bool:
    return classroom.owner_id == user.pk or ClassroomMembership.objects.filter(
        classroom=classroom,
        user=user,
        role=ClassroomMembership.Role.TEACHER,
        status=MembershipStatus.ACTIVE,
    ).exists()


@login_required
def classroom_detail(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(Classroom, pk=pk, is_active=True)
    can_view = _can_manage_classroom(request.user, classroom) or ClassroomMembership.objects.filter(
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
            "can_manage": _can_manage_classroom(request.user, classroom),
        },
    )


@login_required
def invite_classroom_member(request: HttpRequest, pk: int) -> HttpResponse:
    classroom = get_object_or_404(Classroom, pk=pk, is_active=True)
    if not _can_manage_classroom(request.user, classroom):
        return HttpResponseForbidden("Apenas professores da turma podem enviar convites.")
    form = ClassroomMemberForm(
        request.POST or None,
        classroom=classroom,
        inviter=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Convite enviado.")
        return redirect("users-manager:classroom-detail", pk=classroom.pk)
    return render(
        request,
        "users_manager/form.html",
        {"form": form, "title": f"Convidar para {classroom.name}"},
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
