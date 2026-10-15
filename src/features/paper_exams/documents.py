"""Layout v1: fixed A4 coordinates shared by printing and optical recognition."""
import base64
from io import BytesIO
from xml.sax.saxutils import escape

import qrcode
from django.core import signing
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepInFrame, KeepTogether, Image

WIDTH, HEIGHT = A4
LETTERS = 'ABCDE'
MARKERS = [(30, 30), (WIDTH - 30, 30), (WIDTH - 30, HEIGHT - 30), (30, HEIGHT - 30)]
SALT = 'paper-exams.layout-v1'


def bubble_position(index, option):
    column, row = divmod(index, 25)
    return 100 + column * 265 + option * 30, 245 + row * 21


def qr_payload(sheet):
    return signing.Signer(salt=SALT).sign(f'1:{sheet.student_id}:{sheet.pk.hex}')


def answer_sheets_pdf(run, sheets=None):
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    pdf.setTitle('Folhas de respostas - ' + run.title)
    for sheet in (sheets if sheets is not None else run.sheets.all()):
        for x, y in MARKERS:
            pdf.rect(x - 5, HEIGHT - y - 5, 10, 10, fill=1, stroke=0)
        pdf.setFont('Helvetica-Bold', 16)
        pdf.drawString(50, HEIGHT - 66, 'Folha de respostas')
        styles = getSampleStyleSheet()
        title = Paragraph(escape(run.title), styles['Normal'])
        frame = KeepInFrame(355, 38, [title], mode='shrink')
        _, h = frame.wrapOn(pdf, 355, 38)
        frame.drawOn(pdf, 50, HEIGHT - 86 - h)
        for y, label, value in [(140, 'Aluno', sheet.student_name),
                                 (159, 'Registro', sheet.student_registration),
                                 (178, 'Turma', run.classroom_name)]:
            text = f'{label}: {value}'
            size = 10
            while pdf.stringWidth(text, 'Helvetica', size) > 370 and size > 6:
                size -= .5
            pdf.setFont('Helvetica', size)
            pdf.drawString(50, HEIGHT - y, text)
        pdf.setFont('Helvetica', 9)
        pdf.drawString(50, HEIGHT - 195, f'ID: {sheet.student_id} | Turno: {run.context.get("shift", "")} | Sala: {run.context.get("room", "")}'[:100])
        qr = qrcode.make(qr_payload(sheet)).get_image()
        pdf.drawImage(ImageReader(qr), 438, HEIGHT - 187, 110, 110)
        pdf.setFont('Helvetica', 9)
        pdf.drawString(50, HEIGHT - 220, 'Preencha toda a bolinha com caneta preta ou azul. Marque uma alternativa por questão.')
        for i, question in enumerate(run.questions):
            if question.get('type') == 'open_ended':
                continue
            x, y = bubble_position(i, 0)
            pdf.setFont('Helvetica-Bold', 9)
            pdf.drawRightString(x - 19, HEIGHT - y - 3, f'{i + 1:02}')
            for option in range(len(question['options'])):
                x, y = bubble_position(i, option)
                pdf.setLineWidth(.7)
                pdf.circle(x, HEIGHT - y, 6, stroke=1, fill=0)
                pdf.setFont('Helvetica', 6)
                pdf.drawCentredString(x, HEIGHT - y + 9, LETTERS[option])
        pdf.setFont('Helvetica', 8)
        pdf.drawString(50, HEIGHT - 787, 'Não recorte os quatro marcadores. Digitalize a folha inteira, de preferência em 300 dpi.')
        pdf.setFont('Helvetica', 6)
        pdf.drawString(50, HEIGHT - 803, f'Folha {sheet.pk} | Layout 1')
        pdf.showPage()
    pdf.save()
    return stream.getvalue()


def exam_pdf(run, sheets=None):
    from pypdf import PdfReader, PdfWriter
    output = BytesIO()
    writer = PdfWriter()
    styles = getSampleStyleSheet()
    def paragraph(text, style='Normal'):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style])
    for sheet in (sheets if sheets is not None else run.sheets.all()):
        cover = BytesIO(answer_sheets_pdf(run, [sheet]))
        writer.append(PdfReader(cover))
        body = BytesIO()
        story = []
        for index, question in enumerate(run.questions):
            story.append(paragraph(f'Questão {index + 1} - {question["points"]} pontos', 'Heading3'))
            blocks = question.get('content_blocks')
            if blocks is None:
                blocks = ([{'type': 'text', 'text': question['support_text']}] if question.get('support_text') else [])
                blocks += [{'type': 'image', **asset} for asset in question.get('images', [])]
            for block in blocks:
                if block['type'] == 'text':
                    story.extend([paragraph(block['text']), Spacer(1, 8)])
                else:
                    picture = Image(BytesIO(base64.b64decode(block['data'])))
                    scale = min((WIDTH - 84) / picture.imageWidth, 210 / picture.imageHeight, 1)
                    picture.drawWidth = picture.imageWidth * scale
                    picture.drawHeight = picture.imageHeight * scale
                    story.extend([picture, paragraph(block['description']), Spacer(1, 8)])
            story.append(paragraph(question['statement']))
            if question.get('type') == 'open_ended':
                from reportlab.graphics.shapes import Drawing, Line
                from reportlab.lib.units import mm
                for _ in range(question.get('answer_lines', 6)):
                    line = Drawing(WIDTH - 84, 7 * mm)
                    line.add(Line(0, 0, WIDTH - 84, 0, strokeWidth=.4))
                    story.append(line)
            else:
                for letter, option in zip(LETTERS, question['options']):
                    story.append(paragraph(f'{letter}) {option}'))
            story.append(Spacer(1, 16))
        def header(pdf, doc):
            payload = signing.Signer(salt=SALT).sign(f'2:{sheet.student_id}:{sheet.pk.hex}:{doc.page}')
            qr = qrcode.make(payload).get_image()
            pdf.drawImage(ImageReader(qr), 438, HEIGHT - 165, 110, 110)
            fields = [run.title, f'Aluno: {sheet.student_name}', f'Registro: {sheet.student_registration} | ID: {sheet.student_id}',
                      f'Turma: {run.classroom_name}', f'Turno: {run.context.get("shift", "")} | Sala: {run.context.get("room", "")}',
                      f'Oferta: {run.context.get("offer", "")}']
            block = KeepInFrame(375, 130, [paragraph(v) for v in fields], mode='shrink')
            _, height = block.wrapOn(pdf, 375, 130)
            block.drawOn(pdf, 42, HEIGHT - 50 - height)
            pdf.setFont('Helvetica', 8)
            pdf.drawString(42, 25, f'Questões - página {doc.page} | Aluno ID {sheet.student_id}')
        SimpleDocTemplate(body, pagesize=A4, rightMargin=42, leftMargin=42,
            topMargin=190, bottomMargin=42).build(story, onFirstPage=header, onLaterPages=header)
        writer.append(PdfReader(body))
    writer.write(output)
    return output.getvalue()
