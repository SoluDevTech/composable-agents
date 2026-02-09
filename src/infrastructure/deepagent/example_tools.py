from langchain_core.tools import tool
from datetime import datetime, timezone
import secrets


@tool
def get_user_name() -> str:
    """Retourne l'heure actuelle au format ISO 8601."""
    return "Yohan Goncalves"


@tool
def get_secret() -> str:
    """Compte le nombre de mots dans un texte."""
    secret = secrets.token_hex(32)
    return secret
