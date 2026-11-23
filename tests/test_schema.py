"""Minimal JSON Schema (draft 2020-12) validator and its tests.

This deliberately does NOT depend on the ``jsonschema`` package. It supports the
keywords used by ``schema/review.schema.json``:

    type, required, properties, items, enum, $ref, minItems, maxItems,
    prefixItems, const, additionalProperties
"""

import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "schema", "review.schema.json")
EXAMPLE_PATH = os.path.join(ROOT, "examples", "pr-73235", "review.json")


class SchemaError(Exception):
    pass


class ValidationError(Exception):
    def __init__(self, path, message):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def _type_matches(instance, typ):
    if isinstance(typ, str):
        types = [typ]
    else:
        types = list(typ)

    for t in types:
        if t == "object" and type(instance) is dict:
            return True
        if t == "array" and type(instance) is list:
            return True
        if t == "string" and type(instance) is str:
            return True
        if t == "boolean" and type(instance) is bool:
            return True
        if t == "null" and type(instance) is type(None):
            return True
        if t == "integer" and type(instance) is int:
            return True
        if t == "number" and type(instance) in (int, float):
            return True
    return False


def _resolve_ref(ref, root):
    if ref == "#":
        return root
    if ref.startswith("#/"):
        node = root
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                raise SchemaError(f"cannot resolve $ref {ref!r}")
            node = node[part]
        return node
    raise SchemaError(f"unsupported $ref {ref!r}")


def validate(instance, schema, root=None, path="$"):
    """Validate ``instance`` against ``schema``; raise ValidationError on failure."""
    if root is None:
        root = schema
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: schema node is not an object")

    if "$ref" in schema:
        validate(instance, _resolve_ref(schema["$ref"], root), root, path)
        return

    if "type" in schema and not _type_matches(instance, schema["type"]):
        got = type(instance).__name__
        raise ValidationError(path, f"expected type {schema['type']!r}, got {got}")

    if "enum" in schema and instance not in schema["enum"]:
        raise ValidationError(path, f"value {instance!r} not in enum {schema['enum']!r}")

    if "const" in schema and instance != schema["const"]:
        raise ValidationError(path, f"value {instance!r} does not equal const {schema['const']!r}")

    if type(instance) is dict:
        if "required" in schema:
            for key in schema["required"]:
                if key not in instance:
                    raise ValidationError(path, f"missing required property {key!r}")
        if "properties" in schema:
            for key, sub in schema["properties"].items():
                if key in instance:
                    validate(instance[key], sub, root, f"{path}.{key}")
        ap = schema.get("additionalProperties")
        if ap is not None:
            known = set(schema.get("properties", {}))
            for key, value in instance.items():
                if key in known:
                    continue
                if ap is False:
                    raise ValidationError(path, f"unexpected property {key!r}")
                if isinstance(ap, dict):
                    validate(value, ap, root, f"{path}.{key}")

    if type(instance) is list:
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise ValidationError(
                path, f"array has {len(instance)} items, fewer than minItems {schema['minItems']}"
            )
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ValidationError(
                path, f"array has {len(instance)} items, more than maxItems {schema['maxItems']}"
            )
        prefix = schema.get("prefixItems")
        if prefix:
            for index, sub in enumerate(prefix):
                if index < len(instance):
                    validate(instance[index], sub, root, f"{path}[{index}]")
        items = schema.get("items")
        if items is not None:
            start = len(prefix) if prefix else 0
            if items is False and len(instance) > start:
                raise ValidationError(path, "unexpected items beyond prefixItems")
            if isinstance(items, dict):
                for index in range(start, len(instance)):
                    validate(instance[index], items, root, f"{path}[{index}]")

    return instance


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class TestSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = _load(SCHEMA_PATH)
        cls.example = _load(EXAMPLE_PATH)

    def _copy(self):
        return json.loads(json.dumps(self.example))

    def test_example_is_valid(self):
        validate(self.example, self.schema)

    def test_missing_zh_fails(self):
        data = self._copy()
        del data["meta"]["title"]["zh"]
        with self.assertRaises(ValidationError):
            validate(data, self.schema)

    def test_unit_missing_lines_fails(self):
        data = self._copy()
        del data["units"][0]["lines"]
        with self.assertRaises(ValidationError):
            validate(data, self.schema)

    def test_decide_target_not_str_int_fails(self):
        data = self._copy()
        data["overview"]["decide"][0][3] = ["exec", "not-an-int"]
        with self.assertRaises(ValidationError):
            validate(data, self.schema)

    def test_unexpected_top_level_key_fails(self):
        data = self._copy()
        data["extra"] = 1
        with self.assertRaises(ValidationError):
            validate(data, self.schema)


class TestValidatorKeywords(unittest.TestCase):
    def test_const(self):
        validate("x", {"const": "x"})
        with self.assertRaises(ValidationError):
            validate("y", {"const": "x"})

    def test_enum(self):
        validate("new", {"enum": ["new", "mod"]})
        with self.assertRaises(ValidationError):
            validate("other", {"enum": ["new", "mod"]})

    def test_type_array(self):
        # chainItem allows either a node object or a plain string.
        schema = {
            "type": ["object", "string"],
            "required": ["name", "file", "line"],
            "properties": {
                "name": {"type": "string"},
                "file": {"type": "string"},
                "line": {"type": "integer"},
            },
            "additionalProperties": False,
        }
        validate({"name": "main", "file": "f.go", "line": 1}, schema)
        validate("⋯ folded ⋯", schema)
        with self.assertRaises(ValidationError):
            validate({"name": "main"}, schema)  # missing required keys

    def test_prefix_items_and_bounds(self):
        schema = {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "prefixItems": [{"type": "string"}, {"type": "integer"}],
        }
        validate(["exec", 139], schema)
        with self.assertRaises(ValidationError):
            validate(["exec"], schema)  # too few
        with self.assertRaises(ValidationError):
            validate(["exec", 139, 1], schema)  # too many
        with self.assertRaises(ValidationError):
            validate(["exec", "x"], schema)  # wrong second type

    def test_ref_resolution(self):
        schema = {
            "$defs": {"T": {"type": "object", "required": ["en", "zh"], "properties": {
                "en": {"type": "string"}, "zh": {"type": "string"}}, "additionalProperties": False}},
            "type": "object",
            "required": ["title"],
            "properties": {"title": {"$ref": "#/$defs/T"}},
            "additionalProperties": False,
        }
        validate({"title": {"en": "a", "zh": "b"}}, schema)
        with self.assertRaises(ValidationError):
            validate({"title": {"en": "a"}}, schema)  # missing zh


if __name__ == "__main__":
    unittest.main()
