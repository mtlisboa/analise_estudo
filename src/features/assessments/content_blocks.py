"""An ordered support-content list shared by forms, previews and snapshots."""
from django import forms


class ContentBlocksWidget(forms.Textarea):
    template_name = 'assessments/widgets/content_blocks.html'

    def __init__(self):
        super().__init__(attrs={'data-content-blocks-input': '', 'rows': 5})


def ordered_content(item):
    if item.content_blocks:
        return item.content_blocks
    blocks = [{'type': 'text', 'text': text.strip()} for text in item.support_text.split('\n\n') if text.strip()]
    blocks.extend({'type': 'image', 'id': image.pk, 'description': image.description} for image in item.images.all())
    return blocks
