"""Conservative OMR: align registration marks, authenticate QR and measure ink."""
from io import BytesIO

import cv2
import zxingcpp
import numpy as np
from PIL import Image, ImageOps
from django.core import signing

from .documents import WIDTH, HEIGHT, MARKERS, SALT, LETTERS, bubble_position

MAX_PIXELS = 25_000_000
SCALE = 3


class ReadError(ValueError):
    pass


def decode_image(data):
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise ReadError('Imagem excede 25 megapixels.')
            image = ImageOps.exif_transpose(image).convert('RGB')
            return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    except (OSError, Image.DecompressionBombError) as exc:
        raise ReadError('Imagem inválida ou grande demais.') from exc


def align(image):
    # Bound computation for photographs, but preserve enough resolution for QR.
    h, w = image.shape
    if max(h, w) > 2400:
        image = cv2.resize(image, None, fx=2400/max(h, w), fy=2400/max(h, w))
    h, w = image.shape
    _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if (0.000035*w*h < area < .002*w*h and .65 < cw/ch < 1.5
                and area/(cw*ch) > .72):
            candidates.append((x+cw/2, y+ch/2))
    selected = []
    for cx, cy in [(0, 0), (w, 0), (w, h), (0, h)]:
        nearby = [p for p in candidates if abs(p[0]-cx) < w*.28 and abs(p[1]-cy) < h*.28]
        if not nearby:
            raise ReadError('Quatro marcadores não localizados. Digitalize a folha inteira.')
        selected.append(min(nearby, key=lambda p: ((p[0]-cx)/w)**2+((p[1]-cy)/h)**2))
    # Try each orientation. Only a signed QR in the expected header is accepted.
    for rotation in range(4):
        source = np.float32(selected[rotation:] + selected[:rotation])
        target = np.float32(MARKERS) * SCALE
        transform = cv2.getPerspectiveTransform(source, target)
        aligned = cv2.warpPerspective(image, transform, (round(WIDTH*SCALE), round(HEIGHT*SCALE)), borderValue=255)
        header = aligned[60*SCALE:205*SCALE, 420*SCALE:570*SCALE]
        barcode = zxingcpp.read_barcode(header, formats=zxingcpp.BarcodeFormat.QRCode)
        if barcode is None:
            continue
        payload = barcode.text
        try:
            version, student, sheet = signing.Signer(salt=SALT).unsign(payload).split(':')
            identity = {'v': int(version), 'student': int(student), 'sheet': sheet}
        except (signing.BadSignature, ValueError, TypeError):
            continue
        if isinstance(identity, dict) and identity.get('v') == 1:
            return aligned, identity
    raise ReadError('QR code ilegível ou inválido. Nenhuma nota foi atribuída.')


def read_marks(aligned, questions):
    answers, issues = [], []
    for index, question in enumerate(questions):
        densities = []
        for option in range(len(question['options'])):
            x, y = bubble_position(index, option)
            x, y = round(x*SCALE), round(y*SCALE)
            r = 4*SCALE  # inside the printed radius, excluding its outline
            region = aligned[y-r:y+r+1, x-r:x+r+1]
            yy, xx = np.ogrid[-r:r+1, -r:r+1]
            pixels = region[(xx*xx+yy*yy) <= r*r]
            densities.append(float(np.mean(pixels < 150)))
        marked = [i for i, value in enumerate(densities) if value >= .55]
        uncertain = any(.12 < value < .55 for value in densities)
        if len(marked) == 1 and not uncertain:
            answers.append(LETTERS[marked[0]])
        elif not marked and not uncertain:
            answers.append('')
        else:
            answers.append('?')
            issues.append(f'Questão {index+1}: marcação dupla ou preenchimento incerto.')
    return answers, issues


def read_page(image, questions):
    aligned, identity = align(image)
    answers, issues = read_marks(aligned, questions)
    ok, png = cv2.imencode('.png', aligned)
    if not ok:
        raise ReadError('Não foi possível guardar a imagem para revisão.')
    return identity, answers, issues, png.tobytes()
