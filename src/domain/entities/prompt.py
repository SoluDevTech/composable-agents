from datetime import datetime

from pydantic import BaseModel, Field


class PromptVersion(BaseModel):
    """A specific version of a prompt."""

    version_id: str
    content: list[dict[str, str]] = Field(..., description="Messages with role/content")
    model_name: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None  # optional, Phoenix doesn't always return this


class Prompt(BaseModel):
    """Domain entity representing a prompt in Phoenix registry."""

    identifier: str = Field(..., description="Unique prompt identifier/name")
    description: str | None = Field(None)
    current_version: PromptVersion
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def extract_template_variables(self) -> list[str]:
        """Extract template variable names from current version."""
        import re

        content_str = str(self.current_version.content)
        pattern = r"\{([^{}]+)\}"
        matches = re.findall(pattern, content_str)
        return list(set(matches))

    def validate_variables(self, required: list[str]) -> dict[str, any]:
        """Validate template has required variables."""
        found = self.extract_template_variables()
        missing = set(required) - set(found)
        return {
            "is_valid": len(missing) == 0,
            "found": found,
            "missing": list(missing),
        }
