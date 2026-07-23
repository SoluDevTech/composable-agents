import hashlib
import json
from functools import reduce
from operator import or_
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

_PRIMITIVES: dict[str, type] = {"string": str, "number": float, "integer": int, "boolean": bool}


def schema_to_pydantic_model(schema: dict[str, Any], model_name: str = "DynamicModel") -> type[BaseModel]:
    """Convert a JSON Schema dict to a Pydantic BaseModel with extra='ignore'.

    Recursively builds nested models for object properties, stripping any
    fields not present in the schema when model_validate is called.
    """
    return _build_model(schema, model_name)


def _build_model(schema: dict[str, Any], name: str) -> type[BaseModel] | type:
    schema_type = schema.get("type", "object")

    if schema_type == "object":
        return _build_object_model(schema, name)
    if schema_type == "array":
        return _build_array_model(schema, name)

    return _PRIMITIVES.get(schema_type, str)


def _build_object_model(schema: dict[str, Any], name: str) -> type[BaseModel]:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    field_defs: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        python_name = _sanitize(prop_name)
        prop_type = _resolve_prop_type(prop_schema, name, prop_name)
        if prop_name in required:
            field_defs[python_name] = (prop_type, Field(description=prop_schema.get("description", "")))
        else:
            field_defs[python_name] = (prop_type, Field(default=None, description=prop_schema.get("description", "")))

    return create_model(name, __config__=ConfigDict(extra="ignore"), **field_defs)


def _resolve_prop_type(prop_schema: dict[str, Any], parent_name: str, prop_name: str) -> type:
    """Resolve the Python type for a single property schema."""
    if "enum" in prop_schema:
        return _build_enum_type(prop_schema["enum"])

    if "anyOf" in prop_schema:
        return _build_union_type(prop_schema["anyOf"], parent_name, prop_name)

    prop_type = prop_schema.get("type", "string")

    if isinstance(prop_type, list):
        return _build_type_array_union(prop_type, prop_schema, parent_name, prop_name)

    if prop_type == "object":
        nested_name = f"{parent_name}_{_sanitize(prop_name).capitalize()}"
        return _build_object_model(prop_schema, nested_name)
    if prop_type == "array":
        return _build_array_model(prop_schema, f"{parent_name}_{_sanitize(prop_name).capitalize()}Item")

    return _PRIMITIVES.get(prop_type, str)


def _build_enum_type(values: list[Any]) -> type:
    """Build a Literal type from an enum's value list."""
    return Literal[tuple(values)]  # type: ignore[valid-type]


def _build_union_type(variants: list[dict[str, Any]], parent_name: str, prop_name: str) -> type:
    """Build a Union type from an anyOf variant list.

    A variant of ``{"type": "null"}`` maps to ``types.NoneType`` so the
    resulting union is nullable.
    """
    variant_name = f"{parent_name}_{_sanitize(prop_name).capitalize()}Variant"
    non_null_types: list[type] = []
    has_null = False
    for variant in variants:
        if variant.get("type") == "null":
            has_null = True
            continue
        non_null_types.append(_build_model(variant, variant_name))

    return _join_union(non_null_types, has_null)


def _build_type_array_union(types: list[str], prop_schema: dict[str, Any], parent_name: str, prop_name: str) -> type:
    """Build a Union type from a ``type: ["a", "b", ...]`` list form.

    Object/array variants are built as nested models (preserving properties/items
    constraints) by delegating to ``_build_object_model``/``_build_array_model``.
    """
    nested_name = f"{parent_name}_{_sanitize(prop_name).capitalize()}"
    has_null = "null" in types
    non_null_types: list[type] = []
    for t in types:
        if t == "null":
            continue
        if t == "object":
            non_null_types.append(_build_object_model(prop_schema, nested_name))
        elif t == "array":
            non_null_types.append(_build_array_model(prop_schema, nested_name))
        else:
            non_null_types.append(_PRIMITIVES.get(t, str))
    return _join_union(non_null_types, has_null)


def _join_union(non_null_types: list[type], has_null: bool) -> type:
    """Combine a list of non-null types with optional ``None`` into a union."""
    base = non_null_types[0] if len(non_null_types) == 1 else reduce(or_, non_null_types)
    return base | None if has_null else base


def _build_array_model(schema: dict[str, Any], name: str) -> type:
    items_schema = schema.get("items", {})
    items_type = items_schema.get("type", "string")
    if items_type == "object":
        nested_model = _build_object_model(items_schema, f"{name}Item")
        return list[nested_model]
    return list[_PRIMITIVES.get(items_type, str)]


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
