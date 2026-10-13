from .analysis.views import index as analysis_index

def index(request):
    return analysis_index(request, teacher_only=True)
