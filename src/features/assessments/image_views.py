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
    allowed = image.owner_id == request.user.pk
    if not allowed:
        from contexts.institutions.coursework.models import Publication
        from contexts.institutions.coursework.services import student_publications
        from features.users_manager.models import InstitutionalAccount
        account = InstitutionalAccount.objects.filter(user=request.user, role='STUDENT',
            organization__is_active=True).first()
        if account:
            publications = Publication.objects.filter(is_published=True,
                offer__period__organization=account.organization, assessment__owner_id=image.owner_id
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
    try:
        response = FileResponse(image.file.open('rb'), content_type='image/png')
    except (FileNotFoundError, OSError):
        raise Http404
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
