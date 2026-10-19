import re
import unicodedata


def normalizar(texto):
    """Minúsculas, sin tildes ni signos, con espacios simples. Ej.: 'Bomba Nº 2-A' → 'bomba no 2 a'."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    solo_letras = re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower())
    return solo_letras.strip()
