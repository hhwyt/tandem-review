"""Tests of the review.json validator in tandem/validate.py."""

import json
import os
import unittest

from tandem.validate import ValidationError, check_review, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "schema", "review.schema.json")
EXAMPLE_PATH = os.path.join(ROOT, "examples", "pr-73235", "review.json")


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

    def test_overview_figures_ok(self):
        data = self._copy()
        data["overview"]["figures"] = [
            {"en": "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
             "zh": "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>"}
        ]
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


class TestReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = _load(EXAMPLE_PATH)

    def _copy(self):
        return json.loads(json.dumps(self.example))

    def assertProblem(self, data, text):
        problems = check_review(data)
        self.assertTrue(any(text in p for p in problems), problems)

    def test_example_has_no_problems(self):
        self.assertEqual(check_review(self._copy()), [])

    def test_decide_line_outside_unit(self):
        data = self._copy()
        data["overview"]["decide"][0][3][1] = 999999
        self.assertProblem(data, "overview.decide[0] points at")

    def test_map_unknown_unit(self):
        data = self._copy()
        data["overview"]["map"][0]["steps"][1]["go"] = ["nope", 1]
        self.assertProblem(data, "unit 'nope', which does not exist")

    def test_unit_missing_from_chapters(self):
        data = self._copy()
        data["chapters"][0]["items"].pop()
        self.assertProblem(data, "appears 0 times in chapters")

    def test_note_line_outside_unit(self):
        data = self._copy()
        data["units"][0]["notes"][0][0] = 999999
        self.assertProblem(data, "uses line 999999")

    def test_frame_pr_not_a_unit(self):
        data = self._copy()
        data["units"][0]["chains"][0][0]["pr"] = "nope"
        self.assertProblem(data, "pr 'nope'")

    def test_file_missing_from_filesrc(self):
        data = self._copy()
        del data["filesrc"][data["units"][0]["file"]]
        self.assertProblem(data, "missing from filesrc")

    def test_schema_error_is_reported(self):
        data = self._copy()
        del data["overview"]["map"]
        self.assertProblem(data, "missing required property 'map'")

    def test_summary_one_line_reported(self):
        data = self._copy()
        data["overview"]["summary"]["en"] = "only one line"
        self.assertProblem(data, "overview.summary.en has 1 lines")

    def test_summary_three_lines_ok(self):
        data = self._copy()
        data["overview"]["summary"]["en"] = "**Problem**: p\n**Change**: c\n**Risk**: r"
        data["overview"]["summary"]["zh"] = "**问题**：p\n**改动**：c\n**风险**：r"
        self.assertEqual(check_review(data), [])

    def test_doc_minimal_example_is_valid(self):
        with open(os.path.join(ROOT, "docs", "review-json.md"), encoding="utf-8") as fh:
            doc = fh.read()
        block = doc[doc.index("## Minimal example"):]
        block = block[block.index("```json") + len("```json"):]
        self.assertEqual(check_review(json.loads(block[:block.index("```")])), [])
