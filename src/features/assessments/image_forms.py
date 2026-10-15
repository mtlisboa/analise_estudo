"""Validated, normalized uploads; stored images are never edited in place."""
from io import BytesIO

from django import forms
from django.core.files.base import ContentFile
from PIL import Image

from .models import QuestionImage

MAX_IMAGES = 5
MAX_IMAGE_SIZE = 2 * 1024 * 1024


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        if len(files) > MAX_IMAGES:
            raise forms.ValidationError('Adicione no máximo cinco imagens por questão.')
        cleaned = []
        for upload in files:
            if upload.size > MAX_IMAGE_SIZE:
                raise forms.ValidationError('Cada imagem deve ter até 2 MB.')
            upload = super().clean(upload, initial)
            image = upload.image
            if image.format not in ('PNG', 'JPEG', 'WEBP'):
                raise forms.ValidationError('Use imagens PNG, JPEG ou WebP.')
            if image.width * image.height > 10_000_000:
                raise forms.ValidationError('A imagem deve ter até 10 milhões de pixels.')
            upload.seek(0)
            with Image.open(upload) as original:
                output = BytesIO()
                original.convert('RGBA' if 'A' in original.getbands() else 'RGB').save(output, format='PNG')
            if output.tell() > MAX_IMAGE_SIZE:
                raise forms.ValidationError('A imagem processada excede 2 MB. Reduza suas dimensões.')
            cleaned.append(ContentFile(output.getvalue(), name='imagem.png'))
        return cleaned


class QuestionImagesMixin:
    def configure_images(self, source=None):
        self.fields['new_images'] = MultipleImageField(label='Imagens entre o texto e o comando',
            required=False, widget=MultipleImageInput(attrs={'accept': 'image/png,image/jpeg,image/webp'}),
            help_text='Até cinco imagens, em ordem de seleção. PNG, JPEG ou WebP; até 2 MB por imagem.')
        self.fields['image_description'] = forms.CharField(label='Descrição das novas imagens',
            max_length=300, required=False, help_text='Descreva o conteúdo para quem utiliza leitor de tela.')
        current = self.instance if self.instance.pk else source
        queryset = current.images.all() if current else QuestionImage.objects.none()
        self.fields['remove_images'] = forms.ModelMultipleChoiceField(label='Remover imagens desta versão',
            queryset=queryset, required=False, widget=forms.CheckboxSelectMultiple)
        if not queryset.exists():
            self.fields['remove_images'].widget = forms.MultipleHiddenInput()
        order = list(self.fields)
        for field in ('new_images', 'image_description', 'remove_images'):
            order.remove(field)
        index = order.index('statement')
        self.order_fields(order[:index] + ['new_images', 'image_description', 'remove_images'] + order[index:])
        self.existing_images = queryset
        from .content_blocks import ContentBlocksWidget, ordered_content
        self.fields['content_blocks'] = forms.JSONField(label='Parágrafos e imagens', required=False,
            widget=ContentBlocksWidget(), initial=ordered_content(current) if current else [])
        leading = [name for name in ('title', 'content_blocks', 'statement', 'question_type', 'options', 'correct_answer') if name in self.fields]
        self.order_fields(leading + [name for name in self.fields if name not in leading])

    def validate_images(self, cleaned):
        if 'content_blocks' in self.data:
            blocks = cleaned.get('content_blocks')
            if blocks is None:
                blocks = []
            try:
                self.validate_blocks(blocks)
            except forms.ValidationError as exc:
                self.add_error('content_blocks', exc)
            return cleaned
        uploads = cleaned.get('new_images', [])
        removed = cleaned.get('remove_images', [])
        remaining = self.fields['remove_images'].queryset.count() - len(removed)
        if remaining + len(uploads) > MAX_IMAGES:
            self.add_error('new_images', 'A questão pode conter no máximo cinco imagens.')
        if uploads and not cleaned.get('image_description', '').strip():
            self.add_error('image_description', 'Descreva as imagens adicionadas.')
        return cleaned

    def block_image_choices(self):
        from django.db.models import Q
        from .bank_access import reusable_images
        current = self.fields['remove_images'].queryset
        owner = getattr(self, 'sharing_owner', None)
        if owner is None:
            return current
        return QuestionImage.objects.filter(Q(pk__in=current.values('pk')) |
            Q(pk__in=reusable_images(owner).values('pk'))).distinct()

    def validate_blocks(self, blocks):
        import re
        if not isinstance(blocks, list) or len(blocks) > 50:
            raise forms.ValidationError('Use uma lista com até 50 blocos.')
        ids = [block['id'] for block in blocks if isinstance(block, dict) and type(block.get('id')) is int]
        allowed = {image.pk: image for image in self.block_image_choices().filter(pk__in=ids)}
        self.block_uploads = {}
        images = 0
        for block in blocks:
            if not isinstance(block, dict):
                raise forms.ValidationError('Bloco inválido.')
            if block.get('type') == 'text':
                if not isinstance(block.get('text'), str) or not block['text'].strip() or len(block['text']) > 15000:
                    raise forms.ValidationError('Preencha cada parágrafo com até 15.000 caracteres.')
            elif block.get('type') == 'image':
                images += 1
                if images > MAX_IMAGES:
                    raise forms.ValidationError('A questão pode conter no máximo cinco imagens.')
                if 'upload' in block:
                    key = block['upload']
                    if not isinstance(key, str) or not re.fullmatch(r'block_image_[a-zA-Z0-9_-]{1,80}', key) or key in self.block_uploads:
                        raise forms.ValidationError('Identificador de imagem inválido.')
                    description = block.get('description', '')
                    if not isinstance(description, str) or not description.strip() or len(description) > 300:
                        raise forms.ValidationError('Descreva cada imagem em até 300 caracteres.')
                    upload = self.files.get(key)
                    if upload is None:
                        raise forms.ValidationError('Selecione novamente o arquivo de cada imagem nova.')
                    self.block_uploads[key] = MultipleImageField().clean(upload)[0]
                elif not isinstance(block.get('id'), int) or block['id'] not in allowed:
                    raise forms.ValidationError('Escolha uma imagem disponível no seu banco ou nas questões públicas acessíveis.')
            else:
                raise forms.ValidationError('Escolha parágrafo ou imagem.')
        if images > MAX_IMAGES:
            raise forms.ValidationError('A questão pode conter no máximo cinco imagens.')

    def save_images(self, item, owner):
        if 'content_blocks' in self.data:
            blocks, image_ids = [], []
            ids = [block['id'] for block in self.cleaned_data.get('content_blocks') or [] if type(block.get('id')) is int]
            allowed = {image.pk: image for image in self.block_image_choices().filter(pk__in=ids)}
            for block in self.cleaned_data.get('content_blocks') or []:
                if block['type'] == 'text':
                    blocks.append({'type': 'text', 'text': block['text'].strip()})
                else:
                    if 'upload' not in block and block['id'] not in allowed:
                        from django.core.exceptions import PermissionDenied
                        raise PermissionDenied('A imagem não está mais disponível para esta questão.')
                    image = (QuestionImage.objects.create(owner=owner, file=self.block_uploads[block['upload']],
                        description=block['description'].strip()) if 'upload' in block else allowed[block['id']])
                    image_ids.append(image.pk)
                    blocks.append({'type': 'image', 'id': image.pk, 'description': image.description})
            item.images.set(image_ids)
            item.content_blocks = blocks
            item.support_text = '\n\n'.join(block['text'] for block in blocks if block['type'] == 'text')
            item.save(update_fields=['content_blocks', 'support_text'])
            return
        item.images.remove(*self.cleaned_data.get('remove_images', []))
        for upload in self.cleaned_data.get('new_images', []):
            item.images.add(QuestionImage.objects.create(owner=owner, file=upload,
                description=self.cleaned_data['image_description'].strip()))
