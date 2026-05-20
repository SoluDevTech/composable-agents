import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model


def schema_to_pydantic_model(schema: dict[str, Any], model_name: str = "DynamicModel") -> type[BaseModel]:
    """Convert a JSON Schema dict to a Pydantic BaseModel with extra='ignore'.

    Recursively builds nested models for object properties, stripping any
    fields not present in the schema when model_validate is called.
    """
    return _build_model(schema, model_name)


def _build_model(schema: dict[str, Any], name: str) -> type[BaseModel]:
    schema_type = schema.get("type", "object")

    if schema_type == "object":
        return _build_object_model(schema, name)
    if schema_type == "array":
        return _build_array_model(schema, name)

    primitives = {"string": str, "number": float, "integer": int, "boolean": bool}
    return primitives.get(schema_type, str)


def _build_object_model(schema: dict[str, Any], name: str) -> type[BaseModel]:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    if not properties:
        return create_model(
            name,
            __config__=ConfigDict(extra="ignore"),
            **{_sanitize(k): (dict | None, Field(default=None)) for k in properties},
        )

    field_defs: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        python_name = _sanitize(prop_name)
        prop_type = prop_schema.get("type", "string")

        if prop_type == "object":
            nested_name = f"{name}_{_sanitize(prop_name).capitalize()}"
            nested_model = _build_object_model(prop_schema, nested_name)
            if prop_name in required:
                field_defs[python_name] = (nested_model, Field(description=prop_schema.get("description", "")))
            else:
                field_defs[python_name] = (nested_model | None, Field(default=None, description=prop_schema.get("description", "")))
        elif prop_type == "array":
            items_schema = prop_schema.get("items", {})
            items_type = items_schema.get("type", "string")
            if items_type == "object":
                nested_name = f"{name}_{_sanitize(prop_name).capitalize()}Item"
                nested_model = _build_object_model(items_schema, nested_name)
                list_type = list[nested_model]
            else:
                primitives = {"string": str, "number": float, "integer": int, "boolean": bool}
                list_type = list[primitives.get(items_type, str)]
            if prop_name in required:
                field_defs[python_name] = (list_type, Field(default_factory=list, description=prop_schema.get("description", "")))
            else:
                field_defs[python_name] = (list_type | None, Field(default=None, description=prop_schema.get("description", "")))
        else:
            primitives = {"string": str, "number": float, "integer": int, "boolean": bool}
            python_type = primitives.get(prop_type, str)
            if prop_name in required:
                field_defs[python_name] = (python_type, Field(description=prop_schema.get("description", "")))
            else:
                field_defs[python_name] = (python_type | None, Field(default=None, description=prop_schema.get("description", "")))

    return create_model(name, __config__=ConfigDict(extra="ignore"), **field_defs)


def _build_array_model(schema: dict[str, Any], name: str) -> type:
    items_schema = schema.get("items", {})
    items_type = items_schema.get("type", "string")
    if items_type == "object":
        nested_model = _build_object_model(items_schema, f"{name}Item")
        return list[nested_model]
    primitives = {"string": str, "number": float, "integer": int, "boolean": bool}
    return list[primitives.get(items_type, str)]


def _sanitize(name: str) -> str:
    sanitized = name.replace("-", "_").replace(" ", "_")
    if sanitized[0].isdigit():
        sanitized = f"field_{sanitized}"
    return sanitized


def make_validation_model(response_format: dict[str, Any]) -> type[BaseModel]:
    """Create a Pydantic validation model from an agent's response_format schema.

    The resulting model uses extra='ignore' so any fields not in the schema
    are silently stripped on model_validate.
    """
    schema_hash = hashlib.sha256(json.dumps(response_format, sort_keys=True).encode()).hexdigest()[:8]
    return schema_to_pydantic_model(response_format, f"ResponseFormat_{schema_hash}")
