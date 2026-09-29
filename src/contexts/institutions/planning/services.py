"""Tenant-scoped planning. Call mutations inside an organization-locked transaction."""
import csv
import io
from collections import Counter, defaultdict
from datetime import date, time
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from features.users_manager.models import (
    Classroom, ClassroomGroup, ClassroomMembership, InstitutionalAccount, Organization,
)
from .models import Lesson, Offer, Period, Requirement, Student, Teacher


def authorize(actor):
    if not actor.is_authenticated:
        raise PermissionDenied("Entre com uma conta institucional.")
    account = InstitutionalAccount.objects.select_related("organization__school").filter(
        user=actor, role__in=["ADMIN", "OPERATOR"], organization__is_active=True,
        organization__school__isnull=False, user__is_active=True,
    ).first()
    if not actor.is_authenticated or not account:
        raise PermissionDenied("Somente o administrativo e o operador desta instituição podem montar turmas.")
    return account


def overlaps(a, b):
    return a.weekday == b.weekday and a.starts_at < b.ends_at and b.starts_at < a.ends_at


def concurrent_lessons(period):
    return Lesson.objects.filter(
        requirement__offer__period__organization=period.organization,
        requirement__offer__period__starts_on__lte=period.ends_on,
        requirement__offer__period__ends_on__gte=period.starts_on,
    ).select_related("slot", "requirement__teacher__account", "requirement__offer__period")


def occupied_lessons(period, exclude_id=None):
    rows = list(concurrent_lessons(period).exclude(pk=exclude_id))
    def key(row):
        teacher_id = row.requirement.teacher.account_id if row.requirement.teacher_id else None
        return (row.requirement.offer_id, row.requirement.subject, teacher_id,
                row.slot.weekday, row.slot.starts_at, row.slot.ends_at)
    seen = {key(row) for row in rows}
    # A draft in another period must not free a teacher's currently published time.
    for offer in Offer.objects.filter(period__organization=period.organization,
            period__published_at__isnull=False).exclude(period=period).select_related("period"):
        for entry in offer.published_schedule:
            start = date.fromisoformat(entry["period_start"])
            end = date.fromisoformat(entry["period_end"])
            if start > period.ends_on or end < period.starts_on:
                continue
            row = SimpleNamespace(
                slot=SimpleNamespace(weekday=entry["day"], starts_at=time.fromisoformat(entry["start"]),
                                     ends_at=time.fromisoformat(entry["end"])),
                requirement=SimpleNamespace(offer_id=offer.pk, subject=entry["subject"],
                    teacher_id=entry["teacher_id"], teacher=SimpleNamespace(account_id=entry["teacher_id"])))
            if key(row) not in seen:
                seen.add(key(row))
                rows.append(row)
    return rows


def validate_lesson(lesson):
    req, slot = lesson.requirement, lesson.slot
    period = req.offer.period
    if slot.period_id != period.pk or slot.shift != req.offer.shift:
        raise ValidationError("O horário deve pertencer ao mesmo período e turno da turma.")
    teacher = req.teacher
    if not teacher or teacher.period_id != period.pk or not teacher.teaches(req.subject):
        raise ValidationError("Defina um professor habilitado antes de adicionar a aula.")
    teacher.full_clean()
    if not teacher.availability.filter(pk=slot.pk, period=period).exists():
        raise ValidationError("O professor não está disponível neste horário.")
    others = occupied_lessons(period, exclude_id=lesson.pk)
    teacher_lessons = [v for v in others if v.requirement.teacher_id
                       and v.requirement.teacher.account_id == teacher.account_id]
    if len(teacher_lessons) >= teacher.max_lessons:
        raise ValidationError("O professor atingiu o limite semanal de aulas.")
    if req.lessons.exclude(pk=lesson.pk).count() >= req.weekly_lessons:
        raise ValidationError("A disciplina já atingiu a quantidade semanal de aulas.")
    for other in others:
        if overlaps(slot, other.slot):
            if other.requirement.offer_id == req.offer_id:
                raise ValidationError("A turma já tem aula neste intervalo.")
            if other.requirement.teacher_id and other.requirement.teacher.account_id == teacher.account_id:
                raise ValidationError("O professor já tem aula neste intervalo.")


def validate_existing(period):
    for teacher in period.teachers.select_related("account__user"):
        teacher.full_clean()
        if teacher.availability.exclude(period=period).exists():
            raise ValidationError("Disponibilidade de outro período.")
    for offer in period.offers.all():
        offer.full_clean()
    for student in period.students.select_related("offer"):
        student.full_clean()
    for req in Requirement.objects.filter(offer__period=period).select_related("offer__period", "teacher"):
        req.full_clean()
    for lesson in concurrent_lessons(period):
        # Changes can invalidate both this period and an overlapping period.
        lesson.full_clean()


def import_students(period, source):
    """Semicolon-separated text; all rows validated before the enclosing commit."""
    if len(source) > 200000:
        raise ValidationError("A lista deve ter no máximo 200 mil caracteres.")
    rows = list(csv.reader(io.StringIO(source), delimiter=";"))
    rows = [r for r in rows if any(v.strip() for v in r)]
    if not rows or len(rows) > 500:
        raise ValidationError("Informe de 1 a 500 alunos por lote.")
    seen = set()
    count = 0
    for number, row in enumerate(rows, 1):
        if len(row) not in (4, 5):
            raise ValidationError(f"Linha {number}: use matrícula;nome;série;turno;turma anterior (opcional).")
        registration, name, grade, shift = [v.strip() for v in row[:4]]
        from features.accounts.institutional import normalize_registration
        registration = normalize_registration(registration)
        if registration in seen:
            raise ValidationError(f"Linha {number}: matrícula repetida no lote.")
        seen.add(registration)
        obj = period.students.filter(registration=registration).first()
        if obj:
            raise ValidationError(f"Linha {number}: {registration} já está na lista. Use Editar.")
        obj = Student(period=period, registration=registration, name=name, grade=grade,
                      shift=shift.upper(), previous_cohort=row[4].strip() if len(row) == 5 else "")
        try:
            obj.full_clean()
        except ValidationError as exc:
            raise ValidationError(f"Linha {number}: {'; '.join(exc.messages)}") from exc
        obj.save()
        count += 1
    return count


def distribute(period):
    students = list(period.students.select_related("offer").order_by("registration"))
    offers = list(period.offers.order_by("name", "pk"))
    if len(students) > 3000 or len(offers) > 100:
        raise ValidationError("Limite por planejamento: 3.000 alunos e 100 ofertas.")
    history = defaultdict(set)
    for student in students:
        if student.previous_cohort.strip():
            history[student.registration].add(("imported", student.previous_cohort.strip().casefold()))
    # Only earlier, published periods count as known shared classes.
    for old_offer in Offer.objects.filter(
        period__organization=period.organization, period__ends_on__lt=period.starts_on,
        period__published_at__isnull=False,
    ).only("id", "published_roster"):
        for registration in old_offer.published_roster:
            history[registration].add(("offer", old_offer.pk))
    cohort_size = Counter(tag for tags in history.values() for tag in tags)
    assignments = defaultdict(list)
    for student in students:
        if student.locked:
            student.full_clean()
            assignments[student.offer_id].append(student)
    # Prefer well-connected cohorts first, with deterministic tie-breaking.
    pending = sorted((s for s in students if not s.locked),
        key=lambda s: (-sum(cohort_size[t] for t in history[s.registration]), s.registration))
    for student in pending:
        compatible = [o for o in offers if o.grade == student.grade and o.shift == student.shift
                      and len(assignments[o.pk]) < o.capacity]
        if not compatible:
            student.offer = None
            continue
        def score(offer):
            peers = sum(len(history[student.registration] & history[p.registration])
                        for p in assignments[offer.pk])
            return (-peers, len(assignments[offer.pk]) / offer.capacity, offer.name, offer.pk)
        chosen = min(compatible, key=score)
        student.offer = chosen
        assignments[chosen.pk].append(student)
    Student.objects.bulk_update(pending, ["offer"])
    return [f"{s.name}: sem vaga compatível em {s.grade} / {s.get_shift_display()}."
            for s in students if not s.offer_id]


def generate_timetable(period):
    reqs = list(Requirement.objects.filter(offer__period=period).select_related(
        "offer__period", "teacher").order_by("pk"))
    teachers = list(period.teachers.select_related("account__user").prefetch_related("availability"))
    slots = list(period.slots.all())
    if len(reqs) > 300 or len(slots) > 200:
        raise ValidationError("Limite por planejamento: 300 disciplinas/ofertas e 200 horários.")
    # Keep manually fixed lessons and their teacher assignment.
    Lesson.objects.filter(requirement__offer__period=period, locked=False).delete()
    fixed = set(Lesson.objects.filter(requirement__offer__period=period).values_list("requirement_id", flat=True))
    for req in reqs:
        if not req.locked and req.pk not in fixed:
            req.teacher = None
            req.save(update_fields=["teacher"])
    validate_existing(period)
    availability = {t.pk: list(t.availability.all()) for t in teachers}
    def candidates(req):
        if req.locked or req.pk in fixed:
            return [req.teacher] if req.teacher else []
        return [t for t in teachers if t.teaches(req.subject)]
    # Most constrained subjects first. Greedy proposal, not an optimality guarantee.
    reqs.sort(key=lambda r: (len(candidates(r)), -r.weekly_lessons, r.pk))
    issues = []
    for req in reqs:
        existing = req.lessons.count()
        needed = req.weekly_lessons - existing
        if needed <= 0:
            continue
        occupied = occupied_lessons(period)
        best = None
        for teacher in candidates(req):
            if not teacher:
                continue
            teacher_load = [v for v in occupied if v.requirement.teacher_id
                            and v.requirement.teacher.account_id == teacher.account_id]
            remaining = max(0, teacher.max_lessons - len(teacher_load))
            chosen = []
            eligible = [s for s in availability[teacher.pk] if s.period_id == period.pk
                        and s.shift == req.offer.shift]
            day_load = Counter(v.slot.weekday for v in teacher_load)
            for slot in sorted(eligible, key=lambda s: (day_load[s.weekday], s.weekday, s.starts_at, s.pk)):
                if len(chosen) >= min(needed, remaining):
                    break
                if any(overlaps(slot, s) for s in chosen):
                    continue
                if any(overlaps(slot, v.slot) and (v.requirement.offer_id == req.offer_id or
                        (v.requirement.teacher_id and v.requirement.teacher.account_id == teacher.account_id))
                        for v in occupied):
                    continue
                chosen.append(slot)
            rank = (-len(chosen), len(teacher_load), teacher.pk)
            if best is None or rank < best[0]:
                best = (rank, teacher, chosen)
        if best and best[2]:
            req.teacher = best[1]
            req.full_clean()
            req.save(update_fields=["teacher"])
            for slot in best[2]:
                lesson = Lesson(requirement=req, slot=slot)
                lesson.full_clean()
                lesson.save()
        missing = req.weekly_lessons - req.lessons.count()
        if missing:
            issues.append(f"{req}: faltam {missing} aula(s). Verifique disponibilidade e carga dos professores.")
    return issues


def pending_issues(period):
    issues = [f"{s}: sem turma." for s in period.students.filter(offer=None)]
    for offer in period.offers.all():
        if not offer.requirements.exists():
            issues.append(f"{offer.name}: cadastre as disciplinas e cargas semanais.")
        for req in offer.requirements.all():
            missing = req.weekly_lessons - req.lessons.count()
            if missing or not req.teacher_id:
                issues.append(f"{req}: grade incompleta ({req.lessons.count()}/{req.weekly_lessons}).")
    if not period.offers.exists():
        issues.append("Cadastre pelo menos uma oferta.")
    return issues


def publish(period, actor):
    validate_existing(period)
    issues = pending_issues(period)
    if issues:
        raise ValidationError(issues[:30])
    organization = period.organization
    group, _ = ClassroomGroup.objects.get_or_create(
        organization=organization, name=f"Ofertas · {period.pk} · {period.name}"[:120],
        defaults={"created_by": actor},
    )
    missing_accounts = 0
    for offer in period.offers.all():
        classroom = offer.classroom
        if classroom is None:
            classroom = Classroom.objects.create(organization=organization, group=group,
                owner=organization.owner, name=offer.name, shift=offer.shift,
                description=f"Oferta {offer.code} · {period.name} · {offer.grade}")
            offer.classroom = classroom
        else:
            classroom.name, classroom.shift = offer.name, offer.shift
            classroom.save(update_fields=["name", "shift"])
        registrations = list(offer.students.values_list("registration", flat=True))
        accounts = list(InstitutionalAccount.objects.filter(organization=organization,
            registration__in=registrations, role="STUDENT", user__is_active=True))
        missing_accounts += len(registrations) - len(accounts)
        desired = {a.user_id: "STUDENT" for a in accounts}
        for teacher in Teacher.objects.filter(requirements__offer=offer).select_related("account"):
            desired[teacher.account.user_id] = "TEACHER"
        ClassroomMembership.objects.filter(classroom=classroom,
            user_id__in=set(offer.published_members) - set(desired)).update(status="REMOVED")
        for user_id, role in desired.items():
            ClassroomMembership.objects.update_or_create(classroom=classroom, user_id=user_id,
                defaults={"role": role, "status": "ACTIVE", "invited_by": actor})
        offer.published_members = sorted(desired)
        offer.published_roster = registrations
        offer.published_schedule = [
            {"weekday": lesson.slot.get_weekday_display(), "day": lesson.slot.weekday,
             "start": lesson.slot.starts_at.strftime("%H:%M"), "end": lesson.slot.ends_at.strftime("%H:%M"),
             "teacher_id": lesson.requirement.teacher.account_id,
             "teacher": str(lesson.requirement.teacher), "subject": lesson.requirement.subject,
             "classroom": offer.name, "period": period.name, "code": str(offer.code),
             "period_start": period.starts_on.isoformat(), "period_end": period.ends_on.isoformat()}
            for lesson in Lesson.objects.filter(requirement__offer=offer).select_related(
                "slot", "requirement__teacher__account__user")
        ]
        offer.save(update_fields=["classroom", "published_members", "published_roster", "published_schedule"])
    period.published_at = timezone.now()
    period.published_revision = period.revision + 1
    period.save(update_fields=["published_at", "published_revision"])
    return missing_accounts


@transaction.atomic
def mutate(actor, period_id, revision, callback):
    account = authorize(actor)
    # Serializes all planning mutations, including overlapping periods.
    Organization.objects.select_for_update().get(pk=account.organization_id)
    period = Period.objects.select_for_update().get(pk=period_id, organization=account.organization)
    if period.revision != revision:
        raise ValidationError("O planejamento foi alterado em outra aba. Recarregue antes de salvar.")
    result = callback(period)
    period.revision += 1
    period.save(update_fields=["revision"])
    return result
