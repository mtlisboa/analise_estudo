"""Private PDF learning modules for a published subject room."""
from io import BytesIO
from urllib.parse import urlencode

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..planning.models import Offer
from ..views import institutional_identity
from .models import PDFModule
from .services import authorize_teacher


class PDFModuleForm(forms.Form):
    title = forms.CharField(label='Título do módulo', max_length=160)
    document = forms.FileField(label='Arquivo PDF', widget=forms.FileInput(attrs={'accept': 'application/pdf,.pdf'}),
        help_text='PDF de até 10 MB. Ao salvar, o módulo ficará disponível aos estudantes desta disciplina.')

    def clean_document(self):
        upload = self.cleaned_data['document']
        if upload.size > 10 * 1024 * 1024:
            raise forms.ValidationError('O PDF deve ter no máximo 10 MB.')
        data = upload.read()
        try:
            import pypdfium2
            if not data.startswith(b'%PDF-'):
                raise ValueError
            with pypdfium2.PdfDocument(data) as pdf:
                if not len(pdf):
                    raise ValueError
        except Exception:
            raise forms.ValidationError('Envie um PDF válido, com páginas e sem senha.')
        return data


def room_link(offer, subject):
    return reverse('institutions:classroom', args=[offer.classroom_id]) + '?' + urlencode({'subject': subject})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def create(request, code, subject):
    account = institutional_identity(request.user)
    offer = get_object_or_404(Offer.objects.select_related('period'), code=code, period__organization=account.organization)
    authorize_teacher(account, offer, subject)
    form = PDFModuleForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        PDFModule.objects.create(offer=offer, subject=subject, teacher=account,
            title=form.cleaned_data['title'], document=form.cleaned_data['document'])
        return redirect(room_link(offer, subject))
    return render(request, 'coursework/pdf_module_form.html', {'form': form, 'subject': subject, 'back_url': room_link(offer, subject)})


def accessible_pdf(request, pk):
    account = institutional_identity(request.user)
    module = get_object_or_404(PDFModule.objects.select_related('offer__period'), pk=pk,
        offer__period__organization=account.organization, offer__period__published_at__isnull=False,
        offer__classroom__is_active=True)
    from features.users_manager.room import authorized_classroom
    authorized_classroom(request, module.offer.classroom_id)
    if not any(l['subject'] == module.subject for l in module.offer.published_schedule):
        raise PermissionDenied
    if account.role == 'TEACHER':
        authorize_teacher(account, module.offer, module.subject)
    return module


@login_required
@never_cache
@require_GET
def reader(request, pk):
    module = accessible_pdf(request, pk)
    from .views import base_data
    return render(request, 'coursework/pdf_reader.html', {**base_data(institutional_identity(request.user)), 'module': module,
        'back_url': room_link(module.offer, module.subject) + '#room-activities'})


@login_required
@never_cache
@require_GET
@xframe_options_sameorigin
def open_pdf(request, pk):
    module = accessible_pdf(request, pk)
    response = FileResponse(BytesIO(bytes(module.document)), content_type='application/pdf', filename=f'modulo-{module.pk}.pdf')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'self'; base-uri 'none'"
    return response


@login_required
@require_POST
def remove(request, pk):
    account = institutional_identity(request.user)
    module = get_object_or_404(PDFModule.objects.select_related('offer__period'), pk=pk, teacher=account)
    authorize_teacher(account, module.offer, module.subject)
    target = room_link(module.offer, module.subject)
    module.delete()
    return redirect(target)
