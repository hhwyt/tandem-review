"""Check a review.json: the JSON Schema and the references between its parts.

The schema validator supports only the draft 2020-12 keywords used by
``schema/review.schema.json``: type, required, properties, items, enum, $ref,
minItems, maxItems, prefixItems, const, additionalProperties.
"""

import json
import os

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "schema", "review.schema.json")


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


def _new_lines(unit):
    """Return the set of new-file line numbers shown by a unit."""
    hunk = unit.get("hunk") or {}
    line = hunk.get("newStart", 0)
    numbers = set()
    for mark, _ in unit.get("lines", []):
        if mark != "-":
            numbers.add(line)
            line += 1
    return numbers


def check_references(data):
    """Return problems a schema cannot express: ids and line numbers that point nowhere."""
    problems = []
    units = {u["id"]: u for u in data["units"]}
    lines = {uid: _new_lines(u) for uid, u in units.items()}

    def target(where, uid, line):
        if uid not in units:
            problems.append("%s points at unit %r, which does not exist" % (where, uid))
        elif line not in lines[uid]:
            problems.append("%s points at %s line %d, which unit %r does not show"
                            % (where, units[uid]["file"], line, uid))

    placed = [uid for chapter in data["chapters"] for uid in chapter["items"]]
    for uid in placed:
        if uid not in units:
            problems.append("chapters list unit %r, which does not exist" % uid)
    for uid in units:
        if placed.count(uid) != 1:
            problems.append("unit %r appears %d times in chapters, expected once"
                            % (uid, placed.count(uid)))
    for i, decision in enumerate(data["overview"]["decide"]):
        target("overview.decide[%d]" % i, decision[3][0], decision[3][1])
    for li, lane in enumerate(data["overview"]["map"]):
        for si, step in enumerate(lane["steps"]):
            if "go" in step:
                target("overview.map[%d].steps[%d].go" % (li, si), step["go"][0], step["go"][1])
    for uid, unit in units.items():
        for i, note in enumerate(unit["notes"]):
            for line in (note[0], note[1]):
                if line not in lines[uid]:
                    problems.append("unit %r note %d uses line %d, which the unit does not show"
                                    % (uid, i, line))
        nodes = unit["callers"] + unit["callees"] + [
            n for chain in unit["chains"] for n in chain if isinstance(n, dict)]
        for node in nodes:
            if "pr" in node and node["pr"] not in units:
                problems.append("unit %r has a frame with pr %r, which is not a unit"
                                % (uid, node["pr"]))
        if unit["file"] not in data["filesrc"]:
            problems.append("unit %r file %s is missing from filesrc" % (uid, unit["file"]))
    paths = {f["path"] for f in data["files"]}
    for path in data["newfiles"]:
        if path not in paths:
            problems.append("newfiles lists %s, which is not in files" % path)
    for lang in ("en", "zh"):
        summary = data["overview"]["summary"][lang]
        lines = [line for line in summary.split("\n") if line.strip()]
        if len(lines) != 3:
            problems.append(
                "overview.summary.%s has %d lines; write exactly three: problem, change, risk"
                % (lang, len(lines)))
    return problems


def check_review(data, schema=None):
    """Return a list of problems with a parsed review.json; empty means it is valid."""
    if schema is None:
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
    try:
        validate(data, schema)
    except ValidationError as exc:
        return [str(exc)]
    return check_references(data)
