from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def inicio(request):
    """Pantalla de inicio según el rol. Las pantallas reales llegan en las Fases 4 y 5."""
    return render(request, "inicio.html")
