import secrets

from langchain_core.tools import tool


@tool
def get_user_name() -> str:
    """Retourne le nom de l'utilisateur."""
    return "Yohan Goncalves"


@tool
def get_secret() -> str:
    """Génère une chaîne secrète aléatoire."""
    secret = secrets.token_hex(32)
    return secret
