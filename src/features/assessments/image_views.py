from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import QuestionImage


@login_required
@never_cache
@require_GET
def question_image(request, pk):
    image = get_object_or_404(QuestionImage, pk=pk)
    from .bank_access import available_questions
    allowed = (image.owner_id == request.user.pk
               or available_questions(request.user).filter(images=image).exists()
               or image.questions.filter(assessment__owner=request.user).exists())
    if not allowed:
        from contexts.institutions.coursework.models import Publication
        from contexts.institutions.coursework.services import student_publications
        from features.users_manager.models import InstitutionalAccount
        account = InstitutionalAccount.objects.filter(user=request.user, role='STUDENT',
            organization__is_active=True).first()
        if account:
            publications = Publication.objects.filter(is_published=True,
                offer__period__organization=account.organization
                ).select_related('offer__period', 'offer__classroom')
            for publication in publications:
                ids = {item['id'] for question in publication.public_snapshot.get('questions', [])
                       for item in question.get('images', [])}
                if image.pk in ids and student_publications(account, publication.offer,
                        publication.subject).filter(pk=publication.pk).exists():
                    allowed = True
                    break
    if not allowed:
        raise Http404
    if request.GET.get('thumbnail') == '1':
        from io import BytesIO
        from PIL import Image
        from django.http import HttpResponse
        try:
            with image.file.open('rb') as file, Image.open(file) as original:
                original.thumbnail((360, 360))
                rgba = original.convert('RGBA')
                preview = Image.new('RGB', rgba.size, 'white')
                preview.paste(rgba, mask=rgba.getchannel('A'))
                output = BytesIO()
                preview.save(output, format='JPEG', quality=82)
        except (OSError, ValueError):
            raise Http404
        response = HttpResponse(output.getvalue(), content_type='image/jpeg')
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response
    try:
        response = FileResponse(image.file.open('rb'), content_type='image/png')
    except (FileNotFoundError, OSError):
        raise Http404
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@never_cache
@require_GET
def image_library(request):
    from django.core.exceptions import PermissionDenied
    from django.http import JsonResponse
    from django.urls import reverse
    from .bank_access import reusable_images
    account = getattr(request.user, 'institutional_account', None)
    if account and account.role not in ('TEACHER', 'ADMIN', 'MANAGER'):
        raise PermissionDenied
    rows = reusable_images(request.user).order_by('-pk')
    query = request.GET.get('q', '').strip()[:100]
    if query:
        rows = rows.filter(description__icontains=query)
    before = request.GET.get('before', '')
    if before:
        if not before.isdigit() or len(before) > 18:
            return JsonResponse({'error': 'Página inválida.'}, status=400)
        rows = rows.filter(pk__lt=int(before))
    page = list(rows[:25])
    return JsonResponse({'images': [{'id': image.pk, 'description': image.description,
        'url': reverse('assessments:question-image', args=[image.pk]),
        'thumbnail': reverse('assessments:question-image', args=[image.pk]) + '?thumbnail=1'} for image in page[:24]],
        'next': page[23].pk if len(page) > 24 else None})
