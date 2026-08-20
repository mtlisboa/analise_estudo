from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


@login_required
def chat_bot(request: HttpRequest) -> HttpResponse:
    diagnostic_prompt = ""
    if request.GET.get("mode") == "diagnostic" and request.user.has_completed_onboarding:
        diagnostic_prompt = (
            "Crie um teste diagnóstico personalizado para mim. Faça uma pergunta por vez, "
            "aguarde minha resposta antes de continuar e adapte as próximas perguntas ao meu nível. "
            f"Meu perfil é {request.user.get_onboarding_role_display()}, meu grau de escolaridade é "
            f"{request.user.get_education_level_display()} e meu objetivo principal é "
            f"{request.user.get_app_goal_display()}. "
            f"Contexto adicional: {request.user.app_goal_details or 'não informado'}. "
            "Ao final, apresente uma avaliação breve, meus pontos fortes e um plano inicial de estudos."
        )
    return render(
        request,
        "ia_integrations/chat_bot.html",
        {"diagnostic_prompt": diagnostic_prompt},
    )
