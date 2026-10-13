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

    def validate_images(self, cleaned):
        uploads = cleaned.get('new_images', [])
        removed = cleaned.get('remove_images', [])
        remaining = self.fields['remove_images'].queryset.count() - len(removed)
        if remaining + len(uploads) > MAX_IMAGES:
            self.add_error('new_images', 'A questão pode conter no máximo cinco imagens.')
        if uploads and not cleaned.get('image_description', '').strip():
            self.add_error('image_description', 'Descreva as imagens adicionadas.')
        return cleaned

    def save_images(self, item, owner):
        item.images.remove(*self.cleaned_data.get('remove_images', []))
        for upload in self.cleaned_data.get('new_images', []):
            item.images.add(QuestionImage.objects.create(owner=owner, file=upload,
                description=self.cleaned_data['image_description'].strip()))
