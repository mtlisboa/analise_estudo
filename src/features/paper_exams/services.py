import csv
import io
import zipfile
from itertools import islice
from decimal import Decimal
from pathlib import PurePosixPath

import numpy as np
import pypdfium2 as pdfium
from django.core.exceptions import ValidationError
from django.db import transaction

from features.users_manager.models import ClassroomMembership, MembershipStatus
from features.users_manager.permissions import can_manage_classroom
from .documents import LETTERS
from .models import ExamRun, AnswerSheet, ImportBatch, SheetResult
from .omr import decode_image, read_page, ReadError

MAX_UPLOAD = 30 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
MAX_PAGES = 100


@transaction.atomic
def issue_run(assessment, classroom, user):
    if assessment.owner_id != user.pk or not can_manage_classroom(user, classroom):
        raise ValidationError('Você não pode emitir provas para esta avaliação ou turma.')
    questions = list(assessment.questions.all())
    if not 1 <= len(questions) <= 50:
        raise ValidationError('A emissão aceita de 1 a 50 questões objetivas por prova.')
    snapshot = []
    for question in questions:
        options = question.options
        if (question.question_type != 'multiple_choice' or not isinstance(options, list)
                or not 2 <= len(options) <= 5 or any(not isinstance(o, str) or not o.strip() for o in options)
                or len(set(options)) != len(options) or question.correct_answer not in options):
            raise ValidationError(f'Questão {question.order}: use 2 a 5 alternativas distintas e um gabarito válido. Questões discursivas não são corrigidas por este módulo.')
        if question.points <= 0:
            raise ValidationError('A pontuação de cada questão deve ser positiva.')
        snapshot.append({'id': question.pk, 'statement': question.statement, 'options': options,
                         'correct': LETTERS[options.index(question.correct_answer)], 'points': str(question.points)})
    members = list(classroom.memberships.filter(role=ClassroomMembership.Role.STUDENT,
                   status=MembershipStatus.ACTIVE, user__is_active=True).select_related('user'))
    if not members:
        raise ValidationError('A turma não possui alunos ativos.')
    if len(members) > 100:
        raise ValidationError('A emissão está limitada a 100 alunos por turma.')
    run = ExamRun.objects.create(assessment=assessment, classroom=classroom, created_by=user,
            title=str(assessment), classroom_name=str(classroom), questions=snapshot)
    AnswerSheet.objects.bulk_create([AnswerSheet(run=run, student=m.user,
            student_name=m.user.get_full_name() or m.user.username, student_registration=m.user.username) for m in members])
    return run


def grade(questions, answers):
    maximum = sum((Decimal(q['points']) for q in questions), Decimal('0'))
    score = sum((Decimal(q['points']) for q, answer in zip(questions, answers) if q['correct'] == answer), Decimal('0'))
    return score, maximum


def save_result(batch, identity, answers, issues, source, evidence=None):
    if 'run' in identity and str(identity['run']) != str(batch.run_id):
        raise ReadError('A folha pertence a outra emissão de prova.')
    try:
        sheet = batch.run.sheets.get(pk=identity.get('sheet'), student_id=identity.get('student'))
    except (AnswerSheet.DoesNotExist, ValidationError, ValueError, TypeError):
        raise ReadError('Aluno ou folha não corresponde à emissão selecionada.')
    if len(answers) != len(batch.run.questions):
        raise ReadError('Quantidade de respostas diferente da prova.')
    score, maximum = grade(batch.run.questions, answers)
    result, created = SheetResult.objects.get_or_create(sheet=sheet, defaults={
        'batch': batch, 'source_name': source[:255], 'detected': answers, 'answers': answers,
        'issues': issues, 'status': 'review' if issues else 'graded',
        'score': None if issues else score, 'maximum_score': maximum, 'evidence': evidence,
    })
    if not created:
        raise ReadError('Folha já importada. O resultado existente foi preservado; use a revisão para corrigir.')
    return result


def csv_template(run):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['sheet_id', 'student_id'] + [f'q{i+1}' for i in range(len(run.questions))])
    for sheet in run.sheets.all():
        writer.writerow([sheet.pk, sheet.student_id] + ['']*len(run.questions))
    return '\ufeff' + output.getvalue()


def import_csv(batch, data):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ReadError('O CSV deve usar codificação UTF-8.') from exc
    delimiter = ';' if ';' in text.partition('\n')[0] else ','
    reader = csv.DictReader(io.StringIO(text, newline=''), delimiter=delimiter)
    expected = ['sheet_id', 'student_id'] + [f'q{i+1}' for i in range(len(batch.run.questions))]
    if reader.fieldnames != expected:
        raise ReadError('Cabeçalho inválido. Baixe o modelo CSV desta emissão e preserve as colunas.')
    rows = list(islice(reader, MAX_PAGES + 1))
    if not rows or len(rows) > MAX_PAGES:
        raise ReadError('O CSV deve conter de 1 a 100 alunos.')
    for line, row in enumerate(rows, 2):
        try:
            if None in row or any(v is None for v in row.values()):
                raise ReadError('Quantidade de colunas inválida.')
            answers = [row[f'q{i+1}'].strip().upper() for i in range(len(batch.run.questions))]
            for index, answer in enumerate(answers):
                if answer and answer not in list(LETTERS[:len(batch.run.questions[index]['options'])]):
                    raise ReadError(f'Questão {index+1}: alternativa inválida. Use uma letra ou deixe vazio.')
            save_result(batch, {'sheet': row['sheet_id'].strip(), 'student': row['student_id'].strip(),
                        'run': str(batch.run_id)}, answers, [], f'{batch.filename}: linha {line}')
        except ReadError as exc:
            batch.errors.append(f'Linha {line}: {exc}')


def pages(data, suffix):
    if suffix == '.pdf':
        try:
            document = pdfium.PdfDocument(data)
        except Exception as exc:
            raise ReadError('PDF inválido ou protegido por senha.') from exc
        try:
            if not 1 <= len(document) <= MAX_PAGES:
                raise ReadError('PDF deve conter de 1 a 100 páginas.')
            for index in range(len(document)):
                try:
                    page = document[index]
                except Exception as exc:
                    raise ReadError('Página PDF inválida.') from exc
                bitmap = None
                try:
                    width, height = page.get_size()
                    if width <= 0 or height <= 0 or width*height > 4_000_000:
                        raise ReadError('Dimensões de página inválidas ou excessivas.')
                    try:
                        bitmap = page.render(scale=min(3, 2400/max(width, height)))
                        image = np.array(bitmap.to_pil().convert('L'))
                    except Exception as exc:
                        raise ReadError('Não foi possível renderizar a página PDF.') from exc
                    yield index+1, image
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
        finally:
            document.close()
    elif suffix in {'.png', '.jpg', '.jpeg'}:
        yield 1, decode_image(data)
    else:
        raise ReadError('Formato não aceito. Use PDF, PNG ou JPG dentro do ZIP.')


def import_scans(batch, files):
    count = 0
    for name, data in files:
        try:
            for number, image in pages(data, PurePosixPath(name).suffix.lower()):
                count += 1
                if count > MAX_PAGES:
                    batch.errors.append('Limite de 100 páginas atingido; divida o lote.')
                    return
                source = f'{name} / página {number}'
                try:
                    identity, answers, issues, evidence = read_page(image, batch.run.questions)
                    save_result(batch, identity, answers, issues, source, evidence)
                except ReadError as exc:
                    batch.errors.append(f'{source}: {exc}')
        except ReadError as exc:
            batch.errors.append(f'{name}: {exc}')


def zip_members(data):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ReadError('ZIP inválido.') from exc
    with archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if not members or len(members) > MAX_PAGES or sum(m.file_size for m in members) > MAX_EXPANDED:
            raise ReadError('ZIP deve conter até 100 arquivos e até 100 MB descompactados.')
        for member in members:
            if member.flag_bits & 1 or member.file_size > MAX_UPLOAD or member.file_size/max(1, member.compress_size) > 200:
                raise ReadError('ZIP protegido ou com expansão excessiva.')
            path = PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts or path.suffix.lower() not in {'.pdf', '.png', '.jpg', '.jpeg'}:
                raise ReadError('ZIP deve conter somente imagens PNG/JPG ou PDFs, sem caminhos relativos especiais.')
        for member in members:
            # Never extract paths to the filesystem.
            try:
                yield member.filename, archive.read(member)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                raise ReadError('Não foi possível ler um arquivo do ZIP.') from exc


def process_upload(run, user, upload):
    if upload.size > MAX_UPLOAD:
        raise ReadError('O arquivo deve ter até 30 MB.')
    suffix = PurePosixPath(upload.name).suffix.lower()
    if suffix not in {'.csv', '.zip', '.pdf', '.png', '.jpg', '.jpeg'}:
        raise ReadError('Envie CSV, ZIP, PDF, PNG ou JPG.')
    data = upload.read(MAX_UPLOAD+1)
    if len(data) > MAX_UPLOAD:
        raise ReadError('O arquivo deve ter até 30 MB.')
    batch = ImportBatch.objects.create(run=run, created_by=user, filename=upload.name[:255])
    try:
        if suffix == '.csv':
            import_csv(batch, data)
        elif suffix == '.zip':
            import_scans(batch, zip_members(data))
        else:
            import_scans(batch, [(upload.name, data)])
    except (ReadError, csv.Error) as exc:
        batch.errors.append(str(exc))
    batch.save(update_fields=['errors'])
    return batch
