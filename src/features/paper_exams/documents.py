"""Layout v1: fixed A4 coordinates shared by printing and optical recognition."""
from io import BytesIO
from xml.sax.saxutils import escape

import qrcode
from django.core import signing
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepInFrame, KeepTogether

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
        pdf.drawString(50, HEIGHT - 195, f'ID do aluno: {sheet.student_id}')
        qr = qrcode.make(qr_payload(sheet)).get_image()
        pdf.drawImage(ImageReader(qr), 438, HEIGHT - 187, 110, 110)
        pdf.setFont('Helvetica', 9)
        pdf.drawString(50, HEIGHT - 220, 'Preencha toda a bolinha com caneta preta ou azul. Marque uma alternativa por questão.')
        for i, question in enumerate(run.questions):
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


def exam_pdf(run):
    stream = BytesIO()
    styles = getSampleStyleSheet()
    story = []
    def paragraph(text, style='Normal'):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style])
    for sheet in run.sheets.all():
        if story:
            story.append(PageBreak())
        story.extend([paragraph(run.title, 'Title'), paragraph(run.classroom_name),
                      paragraph(f'Aluno: {sheet.student_name} | ID: {sheet.student_id}'),
                      Spacer(1, 16)])
        for index, question in enumerate(run.questions):
            block = [paragraph(f'{index + 1}. {question["statement"]}', 'Heading3')]
            for letter, option in zip(LETTERS, question['options']):
                block.append(paragraph(f'{letter}) {option}'))
            block.append(Spacer(1, 12))
            story.append(KeepTogether(block))
    def footer(pdf, doc):
        pdf.setFont('Helvetica', 8)
        pdf.drawRightString(WIDTH - 42, 25, f'Página {doc.page}')
    SimpleDocTemplate(stream, pagesize=A4, rightMargin=42, leftMargin=42,
                      topMargin=42, bottomMargin=42).build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
