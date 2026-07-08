"""Tests for schema_utils public API: schema_to_pydantic_model, make_validation_model.

Private helpers (_sanitize, _build_array_model) are tested indirectly via the
public functions below.
"""

from pydantic import BaseModel

from src.infrastructure.deepagent.schema_utils import (
    make_validation_model,
    schema_to_pydantic_model,
)


class TestSchemaToPydanticModel:
    """Tests for schema_to_pydantic_model."""

    def test_flat_object_returns_basemodel_subclass(self):
        """Should return a BaseModel subclass."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        # Act
        model = schema_to_pydantic_model(schema, "FlatModel")

        # Assert
        assert issubclass(model, BaseModel)

    def test_flat_object_parses_name_field(self):
        """Should validate the name field."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "FlatModel")

        # Act
        instance = model.model_validate({"name": "Alice", "age": 30})

        # Assert
        assert instance.name == "Alice"

    def test_flat_object_parses_age_field(self):
        """Should validate the optional age field."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "FlatModel")

        # Act
        instance = model.model_validate({"name": "Alice", "age": 30})

        # Assert
        assert instance.age == 30

    def test_flat_object_strips_extra_fields(self):
        """Should ignore fields not present in the schema."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "StripModel")

        # Act
        instance = model.model_validate({"name": "Bob", "invented": "extra"})

        # Assert
        assert instance.name == "Bob"

    def test_flat_object_drops_unknown_keys_from_dump(self):
        """Should not include extra fields in the model dump."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "StripModel")
        instance = model.model_validate({"name": "Bob", "invented": "extra"})

        # Act
        dumped = instance.model_dump()

        # Assert
        assert "invented" not in dumped

    def test_optional_fields_default_to_none(self):
        """Should default optional fields to None."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "number"},
            },
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "OptModel")

        # Act
        instance = model.model_validate({"name": "test"})

        # Assert
        assert instance.score is None

    def test_optional_fields_keep_required_value(self):
        """Should keep the required field's provided value."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "number"},
            },
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema, "OptModel")

        # Act
        instance = model.model_validate({"name": "test"})

        # Assert
        assert instance.name == "test"

    def test_nested_object_returns_basemodel(self):
        """Should build a nested model as a BaseModel subclass."""
        # Arrange
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

        # Act
        model = schema_to_pydantic_model(schema, "NestedModel")

        # Assert
        assert issubclass(model, BaseModel)

    def test_nested_object_parses_nested_city(self):
        """Should validate the nested city field."""
        # Arrange
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

        # Act
        instance = model.model_validate({"address": {"city": "Paris", "zip": 75001}})

        # Assert
        assert instance.address.city == "Paris"

    def test_nested_object_parses_nested_zip(self):
        """Should validate the nested zip field."""
        # Arrange
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

        # Act
        instance = model.model_validate({"address": {"city": "Paris", "zip": 75001}})

        # Assert
        assert instance.address.zip == 75001

    def test_nested_object_strips_extra_fields(self):
        """Should ignore extra fields in nested objects."""
        # Arrange
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

        # Act
        dumped = instance.model_dump()

        # Assert
        assert "bogus" not in dumped["address"]

    def test_array_of_primitives_returns_list(self):
        """Should build a list field for arrays of primitives."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["tags"],
        }
        model = schema_to_pydantic_model(schema, "ArrayModel")

        # Act
        instance = model.model_validate({"tags": ["a", "b"]})

        # Assert
        assert instance.tags == ["a", "b"]

    def test_array_of_objects_returns_list_of_models(self):
        """Should build a list of nested models for arrays of objects."""
        # Arrange
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

        # Act
        instance = model.model_validate({"items": [{"name": "x"}, {"name": "y"}]})

        # Assert
        assert len(instance.items) == 2

    def test_primitive_string_returns_str(self):
        """Should return str for type=string."""
        # Arrange
        # Act
        result = schema_to_pydantic_model({"type": "string"}, "M")

        # Assert
        assert result is str

    def test_primitive_integer_returns_int(self):
        """Should return int for type=integer."""
        # Arrange
        # Act
        result = schema_to_pydantic_model({"type": "integer"}, "M")

        # Assert
        assert result is int

    def test_primitive_number_returns_float(self):
        """Should return float for type=number."""
        # Arrange
        # Act
        result = schema_to_pydantic_model({"type": "number"}, "M")

        # Assert
        assert result is float

    def test_primitive_boolean_returns_bool(self):
        """Should return bool for type=boolean."""
        # Arrange
        # Act
        result = schema_to_pydantic_model({"type": "boolean"}, "M")

        # Assert
        assert result is bool

    def test_empty_properties_strips_extras(self):
        """Should ignore all fields when properties is empty."""
        # Arrange
        schema = {"type": "object", "properties": {}, "required": []}
        model = schema_to_pydantic_model(schema, "EmptyModel")

        # Act
        instance = model.model_validate({"anything": "here"})
        dumped = instance.model_dump()

        # Assert
        assert "anything" not in dumped

    def test_sanitize_hyphenated_field_name(self):
        """Should sanitize hyphens to underscores in field names."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"my-field": {"type": "string"}},
            "required": ["my-field"],
        }
        model = schema_to_pydantic_model(schema, "SanitizeModel")

        # Act
        instance = model.model_validate({"my_field": "val"})

        # Assert
        assert instance.my_field == "val"

    def test_sanitize_leading_digit_field_name(self):
        """Should prepend field_ prefix to names starting with a digit."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"2ndField": {"type": "integer"}},
            "required": ["2ndField"],
        }
        model = schema_to_pydantic_model(schema, "SanitizeModel")

        # Act
        instance = model.model_validate({"field_2ndField": 5})

        # Assert
        assert instance.field_2ndField == 5


class TestMakeValidationModel:
    """Tests for make_validation_model."""

    def test_creates_model_with_hash_name(self):
        """Should create a BaseModel subclass with a hash-based name."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

        # Act
        model = make_validation_model(schema)

        # Assert
        assert issubclass(model, BaseModel)
        assert model.__name__.startswith("ResponseFormat_")

    def test_same_schema_produces_same_hash(self):
        """Should produce the same hash name for the same schema."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

        # Act
        model1 = make_validation_model(schema)
        model2 = make_validation_model(schema)

        # Assert
        assert model1.__name__ == model2.__name__

    def test_different_schema_produces_different_hash(self):
        """Should produce a different hash name for different schemas."""
        # Arrange
        schema1 = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
        }
        schema2 = {
            "type": "object",
            "properties": {"b": {"type": "integer"}},
            "required": ["b"],
        }

        # Act
        model1 = make_validation_model(schema1)
        model2 = make_validation_model(schema2)

        # Assert
        assert model1.__name__ != model2.__name__
