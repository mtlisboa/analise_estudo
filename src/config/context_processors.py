from django.conf import settings


def deploy_mode(request):
    """Expose only the safe demo configuration required by the interface."""
    return {
        "mock_mode": settings.MOCK_MODE,
        "mock_username": settings.MOCK_USERNAME if settings.MOCK_MODE else "",
        "mock_password": settings.MOCK_PASSWORD if settings.MOCK_MODE else "",
    }
