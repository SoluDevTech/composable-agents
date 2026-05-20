"""Tests for schema_utils: schema_to_pydantic_model, make_validation_model."""

from pydantic import BaseModel

from src.infrastructure.deepagent.schema_utils import (
    _build_array_model,
    _sanitize,
    make_validation_model,
    schema_to_pydantic_model,
)


class TestSanitize:
    def test_hyphens(self):
        assert _sanitize("my-field") == "my_field"

    def test_spaces(self):
        assert _sanitize("my field") == "my_field"

    def test_leading_digit(self):
        assert _sanitize("1field") == "field_1field"

    def test_no_change(self):
        assert _sanitize("normalName") == "normalName"


class TestSchemaToPydanticModel:
    def test_flat_object(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "FlatModel")
        assert issubclass(model, BaseModel)
        instance = model.model_validate({"name": "Alice", "age": 30})
        assert instance.name == "Alice"
        assert instance.age == 30

    def test_flat_object_strips_extra_fields(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "StripModel")
        instance = model.model_validate({"name": "Bob", "invented": "extra"})
        assert instance.name == "Bob"
        dumped = instance.model_dump()
        assert "invented" not in dumped

    def test_optional_fields_default_none(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "number"},
            },
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "OptModel")
        instance = model.model_validate({"name": "test"})
        assert instance.name == "test"
        assert instance.score is None

    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "zip": {"type": "integer"},
                    },
                    "required": ["city"],
                }
            },
            "required": ["address"],
        }
        model = schema_to_pydantic_model(schema, "NestedModel")
        instance = model.model_validate({"address": {"city": "Paris", "zip": 75001}})
        assert instance.address.city == "Paris"
        assert instance.address.zip == 75001

    def test_nested_object_strips_extra_fields(self):
        schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                }
            },
            "required": ["address"],
        }
        model = schema_to_pydantic_model(schema, "NestedStripModel")
        instance = model.model_validate({"address": {"city": "Lyon", "bogus": 99}})
        dumped = instance.model_dump()
        assert "bogus" not in dumped["address"]

    def test_array_of_primitives(self):
        schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
            "required": ["tags"],
        }
        model = schema_to_pydantic_model(schema, "ArrayModel")
        instance = model.model_validate({"tags": ["a", "b"]})
        assert instance.tags == ["a", "b"]

    def test_array_of_objects(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                }
            },
            "required": ["items"],
        }
        model = schema_to_pydantic_model(schema, "ObjArrayModel")
        instance = model.model_validate({"items": [{"name": "x"}, {"name": "y"}]})
        assert len(instance.items) == 2

    def test_primitives(self):
        assert schema_to_pydantic_model({"type": "string"}, "M") is str
        assert schema_to_pydantic_model({"type": "integer"}, "M") is int
        assert schema_to_pydantic_model({"type": "number"}, "M") is float
        assert schema_to_pydantic_model({"type": "boolean"}, "M") is bool

    def test_empty_properties(self):
        schema = {"type": "object", "properties": {}, "required": []}
        model = schema_to_pydantic_model(schema, "EmptyModel")
        instance = model.model_validate({"anything": "here"})
        dumped = instance.model_dump()
        assert "anything" not in dumped

    def test_sanitize_field_names(self):
        schema = {
            "type": "object",
            "properties": {
                "my-field": {"type": "string"},
                "2ndField": {"type": "integer"},
            },
            "required": ["my-field"],
        }
        model = schema_to_pydantic_model(schema, "SanitizeModel")
        instance = model.model_validate({"my_field": "val", "field_2ndField": 5})
        assert instance.my_field == "val"
        assert instance.field_2ndField == 5


class TestBuildArrayModel:
    def test_array_of_objects(self):
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
        }
        result = _build_array_model(schema, "TestArr")
        assert hasattr(result, "__origin__")

    def test_array_of_strings(self):
        schema = {"type": "array", "items": {"type": "string"}}
        result = _build_array_model(schema, "TestArr")
        assert hasattr(result, "__origin__")


class TestMakeValidationModel:
    def test_creates_model_with_hash_name(self):
        schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }
        model = make_validation_model(schema)
        assert issubclass(model, BaseModel)
        assert model.__name__.startswith("ResponseFormat_")

    def test_same_schema_produces_same_hash(self):
        schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }
        model1 = make_validation_model(schema)
        model2 = make_validation_model(schema)
        assert model1.__name__ == model2.__name__

    def test_different_schema_produces_different_hash(self):
        schema1 = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
        schema2 = {"type": "object", "properties": {"b": {"type": "integer"}}, "required": ["b"]}
        model1 = make_validation_model(schema1)
        model2 = make_validation_model(schema2)
        assert model1.__name__ != model2.__name__
