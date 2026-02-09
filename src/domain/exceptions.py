class DomainError(Exception):
    """Exception de base du domaine."""
    pass


class ConfigError(DomainError):
    """Erreur de configuration."""
    pass


class ConfigNotFoundError(ConfigError):
    """Fichier de configuration introuvable."""
    pass


class ConfigValidationError(ConfigError):
    """Erreur de validation du schema."""
    def __init__(self, errors: list[dict]):
        self.errors = errors
        messages = [f"  - {e.get('loc', '?')}: {e.get('msg', '?')}" for e in errors]
        super().__init__("Erreurs de validation:\n" + "\n".join(messages))


class ThreadNotFoundError(DomainError):
    """Thread introuvable."""
    pass


class AgentError(DomainError):
    """Erreur d'execution de l'agent."""
    pass


class AgentNotFoundError(DomainError):
    """Agent introuvable."""
    pass


class McpError(DomainError):
    """Erreur de base pour les operations MCP."""
    pass


class McpConnectionError(McpError):
    """Erreur de connexion a un serveur MCP."""
    pass


class McpToolLoadError(McpError):
    """Erreur lors du chargement des outils MCP."""
    pass
