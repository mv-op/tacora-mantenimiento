from django.shortcuts import render
from django.utils import timezone


def inicio(request):
    contexto = {
        "ahora": timezone.localtime(),
        "es_htmx": request.headers.get("HX-Request") == "true",
    }
    return render(request, "inicio.html", contexto)
