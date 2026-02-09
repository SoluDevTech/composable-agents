from pathlib import Path
import yaml

from src.domain.entities.agent_config import AgentConfig
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.exceptions import ConfigNotFoundError, ConfigValidationError, ConfigError


class YamlAgentConfigLoader(AgentConfigLoader):
    """Charge et valide une configuration d'agent depuis un fichier YAML."""

    def load(self, config_path: str | Path) -> AgentConfig:
        path = Path(config_path)

        if not path.exists():
            raise ConfigNotFoundError(f"Fichier introuvable: {path}")

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ConfigError(f"YAML invalide dans {path}: {e}") from e

        if not isinstance(raw, dict):
            raise ConfigError(
                f"Le fichier {path} doit contenir un mapping YAML, pas {type(raw).__name__}"
            )

        # Resoudre system_prompt_file relativement au fichier YAML
        if raw.get("system_prompt_file"):
            prompt_path = path.parent / raw["system_prompt_file"]
            if not prompt_path.exists():
                raise ConfigNotFoundError(f"Fichier prompt introuvable: {prompt_path}")
            raw["system_prompt"] = prompt_path.read_text(encoding="utf-8")
            raw.pop("system_prompt_file")

        try:
            return AgentConfig.model_validate(raw)
        except Exception as e:
            if hasattr(e, "errors"):
                raise ConfigValidationError(e.errors()) from e
            raise ConfigError(f"Erreur de validation: {e}") from e
