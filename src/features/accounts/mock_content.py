"""Related demo records, keyed explicitly so repeated loads preserve identity."""
import io
import uuid
from datetime import time, timedelta

from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageDraw

from contexts.institutions.planning.models import Period, Offer, Student, Slot, Teacher, Requirement, Lesson
from contexts.institutions.coursework.models import Publication, PDFModule
from contexts.institutions.coursework.services import publish
from contexts.institutions.communication.models import Conversation, Message
from contexts.institutions.family.models import GuardianLink, FamilyRequest, RequestMessage, SchoolEvent
from features.assessments.models import Assessment, AssessmentTechnique, Question, QuestionImage, QuestionBankItem
from features.notifications.models import Notification
from features.paper_exams.models import ExamRun, ImportBatch
from features.paper_exams.services import issue_run, save_result
from features.users_manager.models import Classroom, ClassroomNotice, InstitutionalAccount, InstitutionalContact


def illustration(label):
    image = Image.new('RGB', (960, 360), '#18334b')
    draw = ImageDraw.Draw(image)
    for i in range(6):
        draw.rounded_rectangle((70+i*140, 100-i*10, 160+i*140, 300), radius=12, fill='#28a99a')
    draw.text((40, 30), label, fill='white')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def demo_pdf(title):
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(50, 790, 'LUMINI - DOCUMENTO DEMONSTRATIVO')
    pdf.drawString(50, 760, title)
    pdf.drawString(50, 730, 'Dados ficticios, destinados exclusivamente a demonstracao.')
    pdf.save()
    return buffer.getvalue()


def populate(organization, administrator, teacher, assistant, student, guardian):
    now = timezone.now().replace(microsecond=0)
    year = now.year
    period, _ = Period.objects.get_or_create(organization=organization, name=f'[MOCK] Ano letivo {year}',
        defaults={'starts_on': now.date().replace(month=1, day=1), 'ends_on': now.date().replace(month=12, day=31)})
    teachers = []
    for user, subject in ((teacher, 'MATEMÁTICA'), (assistant, 'CIÊNCIAS')):
        row, _ = Teacher.objects.get_or_create(period=period, account=user.institutional_account,
            defaults={'subjects': subject, 'max_lessons': 40})
        teachers.append(row)
    rooms = list(Classroom.objects.filter(organization=organization).order_by('pk'))
    for index, room in enumerate(rooms):
        offer, _ = Offer.objects.get_or_create(classroom=room,
            defaults={'period': period, 'name': f'{room.name} {room.letter}'.strip(),
                      'grade': room.name.upper(), 'shift': room.shift, 'capacity': 30})
        if offer.period_id != period.pk:
            continue
        roster = []
        members = room.memberships.filter(role='STUDENT', status='ACTIVE').select_related('user__institutional_account')
        for membership in members:
            account = membership.user.institutional_account
            Student.objects.get_or_create(period=period, registration=account.registration,
                defaults={'name': membership.user.get_full_name(), 'grade': offer.grade,
                    'shift': offer.shift, 'previous_cohort': f'{year-1} · Lumini · Grupo {index+1}', 'offer': offer})
            roster.append(account.registration)
        schedule = []
        for subject_index, planner in enumerate(teachers):
            hour = (14 if room.shift == 'AFTERNOON' else 19 if room.shift == 'EVENING' else 8) + subject_index
            slot, _ = Slot.objects.get_or_create(period=period, weekday=index+1,
                starts_at=time(hour), ends_at=time(hour, 50), shift=room.shift)
            planner.availability.add(slot)
            requirement, _ = Requirement.objects.get_or_create(offer=offer, subject=planner.subjects,
                defaults={'weekly_lessons': 1, 'teacher': planner})
            Lesson.objects.get_or_create(requirement=requirement, slot=slot)
            schedule.append({'weekday': slot.get_weekday_display(), 'day': slot.weekday,
                'start': slot.starts_at.strftime('%H:%M'), 'end': slot.ends_at.strftime('%H:%M'),
                'teacher_id': planner.account_id, 'teacher': str(planner), 'subject': planner.subjects,
                'classroom': offer.name, 'period': period.name, 'code': str(offer.code),
                'period_start': period.starts_on.isoformat(), 'period_end': period.ends_on.isoformat()})
        if not period.published_at:
            period.published_at = now
            period.published_revision = period.revision
            period.save(update_fields=['published_at', 'published_revision'])
        if not offer.published_schedule:
            offer.published_schedule = schedule
            offer.published_roster = roster
            offer.published_members = list(room.memberships.filter(status='ACTIVE').values_list('user_id', flat=True))
            offer.save(update_fields=['published_schedule', 'published_roster', 'published_members'])
        if not room.cover_image:
            room.cover_image.save(f'mock-turma-{room.pk}.png', ContentFile(illustration('LUMINI - ESPACO DE APRENDIZAGEM')))
        for title, body in (
            ('[MOCK] Boas-vindas', 'Este é o espaço da turma. Consulte as disciplinas, atividades e a agenda.'),
            ('[MOCK] Avaliação da semana', 'A prova de Matemática está disponível no início da página. Revise os exercícios antes de começar.'),
            ('[MOCK] Projeto em grupo', 'Organizem as equipes e compartilhem dúvidas no grupo da turma.')):
            ClassroomNotice.objects.get_or_create(classroom=room, title=title,
                defaults={'author': teacher, 'body': body})
        for subject_index, planner in enumerate(teachers):
            assessment, _ = Assessment.objects.get_or_create(owner=planner.account.user,
                subject=planner.subjects, topic='[MOCK] Diagnóstico de aprendizagem',
                defaults={'assembly_method': 'manual', 'assembly_status': 'ready',
                          'technique': AssessmentTechnique.objects.get(code='problem-solving')})
            for order in range(1, 6):
                if subject_index == 0:
                    statement = f'Uma equipe organizou {order*4} livros em 4 caixas iguais. Quantos livros ficaram em cada caixa?'
                    options = [str(order), str(order+1), str(order*4), str(order+4)]
                    answer = str(order)
                else:
                    statement = f'Questão {order}: qual ação contribui para preservar um ecossistema?'
                    options = ['Proteger os habitats naturais', 'Descartar resíduos nos rios', 'Eliminar toda a vegetação', 'Desperdiçar água potável']
                    answer = options[0]
                question, _ = Question.objects.get_or_create(assessment=assessment, order=order,
                    defaults={'question_type': 'multiple_choice', 'statement': statement, 'options': options,
                        'correct_answer': answer, 'points': 2,
                        'support_text': 'Observe o material de apoio e aplique o conceito estudado.',
                        'explanation': 'A alternativa correta aplica o conteúdo da disciplina à situação apresentada.'})
                if order == 1 and not question.images.exists():
                    image = QuestionImage(owner=planner.account.user, description='Material visual demonstrativo de apoio à questão')
                    image.file.save(f'mock-questao-{question.pk}.png', ContentFile(illustration('MATERIAL DE APOIO')))
                    question.images.add(image)
                if question.bank_item_id is None:
                    bank_item = QuestionBankItem.objects.create(owner=planner.account.user,
                        title=f'[MOCK] {planner.subjects} - questão {order}', subject=planner.subjects,
                        topic=assessment.topic, support_text=question.support_text, statement=question.statement,
                        question_type=question.question_type, options=question.options, correct_answer=question.correct_answer,
                        explanation=question.explanation, default_points=question.points)
                    bank_item.images.set(question.images.all())
                    question.bank_item = bank_item
                    question.save(update_fields=['bank_item'])
            PDFModule.objects.get_or_create(offer=offer, subject=planner.subjects, teacher=planner.account,
                title='[MOCK] Material de leitura', defaults={'document':demo_pdf('Material de leitura da disciplina')})
            for kind, suffix in (('EXAM', 'Prova diagnóstica'), ('ACTIVITY', 'Lista de revisão'), ('ACTIVITY', 'Projeto em preparação')):
                publication, created = Publication.objects.get_or_create(offer=offer, subject=planner.subjects,
                    title=f'[MOCK] {suffix}', defaults={'teacher': planner.account, 'assessment': assessment,
                        'kind': kind, 'instructions': 'Leia o material de apoio e resolva as questões. Tire dúvidas com o professor.',
                        'due_at': now+timedelta(days=7+index)})
                if suffix != 'Projeto em preparação' and (created or (not publication.grading_snapshot and not publication.submissions.exists())):
                    publish(planner.account, publication)
            if members.exists():
                run = ExamRun.objects.filter(assessment=assessment, classroom=room, created_by=planner.account.user).first()
                if run is None:
                    run = issue_run(assessment, room, planner.account.user)
                batch, _ = ImportBatch.objects.get_or_create(run=run, filename='[MOCK] respostas.csv',
                    defaults={'created_by': planner.account.user})
                for position, sheet in enumerate(run.sheets.all()):
                    if hasattr(sheet, 'result'):
                        continue
                    answers = ['A' if q < (position+index)%4+1 else 'B' for q in range(5)]
                    save_result(batch, {'sheet': str(sheet.pk), 'student': sheet.student_id}, answers,
                        ['[MOCK] Marca ambígua: revisar alternativa da questão 1.'] if position == 1 and index == 0 else [],
                        f'mock-{sheet.student_id}.csv')
        group, _ = Conversation.objects.get_or_create(classroom=room, defaults={'organization': organization})
        for n, (author, body) in enumerate(((teacher.institutional_account, 'Bom dia, turma! As atividades da semana já estão disponíveis.'),
                (assistant.institutional_account, 'Podem enviar dúvidas sobre Ciências aqui no grupo.'))):
            mock_message(group, author, f'grupo-{room.pk}-{n}', body)
        SchoolEvent.objects.get_or_create(organization=organization, classroom=room,
            title='[MOCK] Encontro de projetos', defaults={'description': 'Apresentação dos trabalhos da turma para as famílias.',
                'starts_at': now+timedelta(days=14), 'ends_at': now+timedelta(days=14, hours=2),
                'location': 'Auditório da instituição', 'is_published': True, 'created_by': administrator})
    for other in (teacher.institutional_account, assistant.institutional_account, administrator.institutional_account):
        first, second = sorted([student.institutional_account.pk, other.pk])
        conversation, _ = Conversation.objects.get_or_create(first_id=first, second_id=second,
            defaults={'organization': organization})
        mock_message(conversation, student.institutional_account, f'direta-{other.pk}-pergunta',
            'Olá! Gostaria de orientação sobre as atividades desta semana.')
        mock_message(conversation, other, f'direta-{other.pk}-resposta',
            'Olá! Consulte o material disponível e me envie a questão em que ficou com dúvida.')
    for account in organization.institutional_accounts.filter(role__in=['GUARDIAN', 'MANAGER', 'OPERATOR', 'TEACHER']):
        first, second = sorted([account.pk, administrator.institutional_account.pk])
        conversation, _ = Conversation.objects.get_or_create(first_id=first, second_id=second,
            defaults={'organization': organization})
        mock_message(conversation, account, f'institucional-{account.pk}-pergunta',
            'Bom dia! Gostaria de confirmar a programação da próxima reunião.')
        mock_message(conversation, administrator.institutional_account, f'institucional-{account.pk}-resposta',
            'Bom dia! A programação está disponível na agenda institucional.')
    # The demo parent has two explicit children, with independent performance histories.
    child = InstitutionalAccount.objects.get(user__username='demo_ana')
    GuardianLink.objects.get_or_create(guardian=guardian.institutional_account, student=child,
        defaults={'relationship': 'Responsável demonstrativo', 'created_by': administrator})
    for kind, title, status in (('CONTACT', '[MOCK] Orientação sobre acompanhamento', 'OPEN'),
            ('DOCUMENT', '[MOCK] Declaração de matrícula', 'PROGRESS'),
            ('DOCUMENT', '[MOCK] Histórico escolar', 'RESOLVED'),
            ('DOCUMENT', '[MOCK] Segunda via indisponível', 'REJECTED')):
        request, _ = FamilyRequest.objects.get_or_create(organization=organization,
            guardian=guardian.institutional_account, title=title,
            defaults={'student': student.institutional_account, 'kind': kind, 'status': status,
                'description': 'Solicitação demonstrativa para acompanhar o atendimento institucional.'})
        RequestMessage.objects.get_or_create(request=request, author=guardian,
            text='Gostaria de informações sobre esta solicitação.')
        if status != 'OPEN':
            reply, _ = RequestMessage.objects.get_or_create(request=request, author=administrator,
                text='Solicitação recebida. A secretaria está acompanhando o atendimento.' if status == 'PROGRESS' else
                     'Solicitação indeferida: confira os dados e envie novamente.' if status == 'REJECTED' else
                     'Solicitação concluída pela secretaria.')
            if status == 'RESOLVED' and not reply.attachment:
                reply.attachment.save('historico-mock.pdf', ContentFile(demo_pdf('Historico escolar demonstrativo')))
    for status in InstitutionalContact.Status.values:
        InstitutionalContact.objects.get_or_create(email=f'mock-{status.lower()}@example.invalid',
            defaults={'institution_name': f'[MOCK] Escola {status}', 'contact_name': 'Contato demonstrativo',
                'phone': '00000000000', 'city': 'João Pessoa', 'state': 'PB', 'status': status,
                'message': 'Gostaria de conhecer a plataforma para minha instituição.'})
    for account in organization.institutional_accounts.select_related('user').all():
        Notification.objects.get_or_create(recipient=account.user, title='[MOCK] Agenda e atividades atualizadas',
            defaults={'message': 'Consulte a agenda, os avisos da turma e as mensagens disponíveis.'})


def mock_message(conversation, author, key, body):
    Message.objects.get_or_create(author=author, nonce=uuid.uuid5(uuid.NAMESPACE_URL, 'lumini-demo/'+key),
        defaults={'conversation': conversation, 'body': body})
