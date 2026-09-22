from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("", views.index, name="index"),
    path("questoes/", views.question_bank, name="question-bank"),
    path("questoes/nova/", views.create_bank_question, name="bank-question-create"),
    path(
        "questoes/<int:source_pk>/derivar/",
        views.create_bank_question,
        name="bank-question-derive",
    ),
    path(
        "questoes/<int:pk>/editar/",
        views.update_bank_question,
        name="bank-question-update",
    ),
    path(
        "questoes/ia/nova/",
        views.generate_bank_question_with_ai,
        name="bank-question-ai-create",
    ),
    path(
        "questoes/<int:pk>/ia/editar/",
        views.edit_bank_question_with_ai,
        name="bank-question-ai-edit",
    ),
    path("nova/", views.create, name="create"),
    path("<int:pk>/editar/", views.update, name="update"),
    path(
        "<int:assessment_pk>/questoes/nova/",
        views.create_question,
        name="question-create",
    ),
    path(
        "<int:assessment_pk>/questoes/do-banco/",
        views.add_bank_questions,
        name="bank-questions-add",
    ),
    path(
        "questoes/adicionar-em-avaliacao/",
        views.add_bank_questions,
        name="bank-questions-add-generic",
    ),
]
