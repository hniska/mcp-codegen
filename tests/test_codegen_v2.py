"""Test Pydantic v2 code generation."""
import pytest
from mcp_codegen.codegen import _pydantic_model_for_params, _generate_tools_hash, render_module


class MockTool:
    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.input_schema = input_schema


class MockSchema:
    def __init__(self, properties, required):
        self.properties = properties
        self.required = required


def test_pydantic_model_with_description():
    """Test model generation includes field descriptions."""
    schema = MockSchema(
        properties={
            "city": {"type": "string", "description": "City name"},
            "days": {"type": "integer", "description": "Number of days"}
        },
        required=["city"]
    )

    tool = MockTool("get_forecast", "Get weather forecast", schema)
    model_code = _pydantic_model_for_params(tool)

    assert "from typing import Annotated, Any, Literal" in model_code
    assert "from pydantic import BaseModel, Field" in model_code
    assert "class Params(BaseModel):" in model_code
    assert "description='City name'" in model_code
    assert "description='Number of days'" in model_code


def test_pydantic_model_with_enum():
    """Test enum handling with Literal."""
    schema = MockSchema(
        properties={
            "units": {"type": "string", "enum": ["metric", "imperial"]}
        },
        required=[]
    )

    tool = MockTool("convert", "Convert units", schema)
    model_code = _pydantic_model_for_params(tool)

    assert "Literal['metric', 'imperial']" in model_code


def test_pydantic_model_with_optional():
    """Test optional field generation."""
    schema = MockSchema(
        properties={
            "required_param": {"type": "string"},
            "optional_param": {"type": "string"}
        },
        required=["required_param"]
    )

    tool = MockTool("test", "Test tool", schema)
    model_code = _pydantic_model_for_params(tool)

    # Required param should not have default
    assert "required_param: Annotated[str, Field(" in model_code
    # Optional param should have default=None
    assert "optional_param: Annotated[str | None, Field(default=None" in model_code


def test_generate_tools_hash():
    """Test deterministic hash generation."""
    tools = [
        MockTool("tool1", "Description 1", MockSchema({}, [])),
        MockTool("tool2", "Description 2", MockSchema({}, []))
    ]

    hash1 = _generate_tools_hash(tools)
    hash2 = _generate_tools_hash(tools)

    # Same input should produce same hash
    assert hash1 == hash2
    assert len(hash1) == 16  # 16-character hash

    # Different input should produce different hash
    tools_modified = tools + [MockTool("tool3", "Description 3", MockSchema({}, []))]
    hash3 = _generate_tools_hash(tools_modified)

    assert hash1 != hash3


def test_empty_tools_raises_error():
    """Test rendering fails gracefully with no tools."""
    with pytest.raises(ValueError) as exc_info:
        render_module("empty", [])

    assert "no tools found" in str(exc_info.value).lower()


def test_model_with_validation_constraints():
    """Test validation constraints are included."""
    schema = MockSchema(
        properties={
            "name": {"type": "string", "minLength": 1, "maxLength": 100},
            "age": {"type": "integer", "minimum": 0, "maximum": 150}
        },
        required=["name"]
    )

    tool = MockTool("person", "Person data", schema)
    model_code = _pydantic_model_for_params(tool)

    # Check min/max length constraints
    assert "min_length=1" in model_code
    assert "max_length=100" in model_code
    # Check numeric constraints
    assert "ge=0" in model_code
    assert "le=150" in model_code
