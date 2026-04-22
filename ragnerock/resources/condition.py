"""Condition grammar for workflow node execution gates.

Users express conditions as a MongoDB-style dict, keyed by a field path from
the upstream execution context. The SDK compiles that dict into the server's
structured condition grammar (``field_comparison`` / ``list_operation`` /
``logical``) before sending it to the server.

A condition tree is built from three primitive shapes:

* **Field comparison** — compare a scalar field to a value::

      {"sentiment.score": {"$gt": 0.5}}

* **List operation** — evaluate a list-valued field::

      {"entities.types": {"$contains": "person"}}        # membership
      {"entities": {"$count": {"$gt": 5}}}               # count + comparison
      {"scores": {"$min": {"$gte": 0.3}}}                # min + comparison
      {"scores": {"$max": {"$lt": 0.9}}}                 # max + comparison

* **Logical combinator** — combine sub-conditions::

      {"$and": [c1, c2, ...]}
      {"$or":  [c1, c2, ...]}
      {"$not": c}

Object literals with multiple keys implicitly ``$and`` their entries.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from ragnerock.errors import ValidationError


class ComparisonOp(str, Enum):
    """MongoDB-style operator tokens that compare a field to a value.

    The enum value is the token a user writes in a condition dict; the
    ``server`` attribute is the symbol the server expects on a
    ``field_comparison`` condition.
    """

    EQ = "$eq"
    NE = "$ne"
    GT = "$gt"
    LT = "$lt"
    GTE = "$gte"
    LTE = "$lte"
    MATCHES = "$matches"

    @property
    def server(self) -> str:
        """Server-side operator symbol this enum member maps to."""
        return _COMPARISON_TO_SERVER[self]


class ListOp(str, Enum):
    """MongoDB-style operator tokens that evaluate a list-valued field.

    ``$count``, ``$min``, and ``$max`` each wrap a nested comparison operator
    (e.g. ``{"$count": {"$gt": 5}}``); ``$contains`` takes a bare value.
    """

    COUNT = "$count"
    CONTAINS = "$contains"
    MIN = "$min"
    MAX = "$max"

    @property
    def server(self) -> str:
        """Server-side operator symbol this enum member maps to."""
        return self.value.lstrip("$")


class LogicalOp(str, Enum):
    """MongoDB-style operator tokens for combining sub-conditions."""

    AND = "$and"
    OR = "$or"
    NOT = "$not"

    @property
    def server(self) -> str:
        """Server-side operator symbol this enum member maps to."""
        return self.name  # "AND" / "OR" / "NOT"


_COMPARISON_TO_SERVER: dict[ComparisonOp, str] = {
    ComparisonOp.EQ: "==",
    ComparisonOp.NE: "!=",
    ComparisonOp.GT: ">",
    ComparisonOp.LT: "<",
    ComparisonOp.GTE: ">=",
    ComparisonOp.LTE: "<=",
    ComparisonOp.MATCHES: "matches",
}

_COMPARISON_TOKENS: frozenset[str] = frozenset(op.value for op in ComparisonOp)
_LIST_TOKENS: frozenset[str] = frozenset(op.value for op in ListOp)
_LOGICAL_TOKENS: frozenset[str] = frozenset(op.value for op in LogicalOp)
_LIST_WITH_COMPARISON: frozenset[str] = frozenset(
    {ListOp.COUNT.value, ListOp.MIN.value, ListOp.MAX.value}
)

_ALLOWED_VALUE_TYPES: tuple[type, ...] = (str, int, float, bool, type(None))


def compile_condition(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Compile a MongoDB-style condition dict to the server's condition grammar.

    The server expects a discriminated-union payload where every node has a
    ``type`` of ``field_comparison``, ``list_operation``, or ``logical``. This
    function walks the user's dict, validates each subtree, and produces the
    server-shaped payload.

    Args:
        spec (Mapping[str, Any]): A MongoDB-style condition. See the module
            docstring for the supported shapes.

    Returns:
        dict[str, Any]: A server-shaped condition payload, ready to send as
        the ``condition`` body of a workflow node.

    Raises:
        ValidationError: ``spec`` is malformed — empty, wrong type, uses an
            unknown operator, or combines operators in an unsupported way.
    """
    return _compile(spec, path="condition")


def _compile(spec: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise ValidationError(f"{path}: expected a mapping, got {type(spec).__name__}.")
    if not spec:
        raise ValidationError(f"{path}: condition mapping must not be empty.")

    keys = list(spec.keys())

    # Implicit AND: multiple keys at the same level combine with AND.
    if len(keys) > 1:
        return {
            "type": "logical",
            "operator": LogicalOp.AND.server,
            "conditions": [_compile({k: spec[k]}, path=f"{path}.{k}") for k in keys],
        }

    key = keys[0]
    value = spec[key]

    if not isinstance(key, str) or not key:
        raise ValidationError(f"{path}: condition keys must be non-empty strings.")

    if key in _LOGICAL_TOKENS:
        return _compile_logical(LogicalOp(key), value, path=path)

    if key.startswith("$"):
        raise ValidationError(
            f"{path}: unknown top-level operator {key!r}; "
            f"expected a field path or one of {sorted(_LOGICAL_TOKENS)}."
        )

    return _compile_field(field_path=key, ops=value, path=path)


def _compile_logical(op: LogicalOp, value: Any, *, path: str) -> dict[str, Any]:
    if op is LogicalOp.NOT:
        if isinstance(value, list):
            raise ValidationError(
                f"{path}.{op.value}: expected a single condition mapping, not a list."
            )
        return {
            "type": "logical",
            "operator": op.server,
            "condition": _compile(value, path=f"{path}.{op.value}"),
        }

    # AND / OR
    if not isinstance(value, list) or not value:
        raise ValidationError(
            f"{path}.{op.value}: expected a non-empty list of sub-conditions."
        )
    return {
        "type": "logical",
        "operator": op.server,
        "conditions": [
            _compile(item, path=f"{path}.{op.value}[{i}]")
            for i, item in enumerate(value)
        ],
    }


def _compile_field(*, field_path: str, ops: Any, path: str) -> dict[str, Any]:
    if not isinstance(ops, Mapping):
        raise ValidationError(
            f"{path}.{field_path}: expected an operator mapping "
            f"(e.g. {{'$gt': 5}}), got {type(ops).__name__}."
        )
    if not ops:
        raise ValidationError(
            f"{path}.{field_path}: operator mapping must not be empty."
        )

    # Multiple ops on the same field implicitly AND.
    if len(ops) > 1:
        return {
            "type": "logical",
            "operator": LogicalOp.AND.server,
            "conditions": [
                _compile_field(field_path=field_path, ops={k: v}, path=path)
                for k, v in ops.items()
            ],
        }

    op_token, op_arg = next(iter(ops.items()))
    if not isinstance(op_token, str):
        raise ValidationError(
            f"{path}.{field_path}: operator keys must be strings, "
            f"got {type(op_token).__name__}."
        )

    if op_token in _COMPARISON_TOKENS:
        return _build_field_comparison(
            field_path=field_path,
            op=ComparisonOp(op_token),
            value=op_arg,
            path=path,
        )
    if op_token in _LIST_TOKENS:
        return _build_list_operation(
            field_path=field_path,
            op=ListOp(op_token),
            op_arg=op_arg,
            path=path,
        )

    raise ValidationError(
        f"{path}.{field_path}: unknown operator {op_token!r}; "
        f"expected one of {sorted(_COMPARISON_TOKENS | _LIST_TOKENS)}."
    )


def _build_field_comparison(
    *, field_path: str, op: ComparisonOp, value: Any, path: str
) -> dict[str, Any]:
    if op is ComparisonOp.MATCHES and not isinstance(value, str):
        raise ValidationError(
            f"{path}.{field_path}.{op.value}: regex value must be a string, "
            f"got {type(value).__name__}."
        )
    _require_scalar(value, path=f"{path}.{field_path}.{op.value}")
    return {
        "type": "field_comparison",
        "field_path": field_path,
        "operator": op.server,
        "value": value,
    }


def _build_list_operation(
    *, field_path: str, op: ListOp, op_arg: Any, path: str
) -> dict[str, Any]:
    if op is ListOp.CONTAINS:
        _require_scalar(op_arg, path=f"{path}.{field_path}.{op.value}")
        return {
            "type": "list_operation",
            "field_path": field_path,
            "operator": op.server,
            "value": op_arg,
            "comparison": None,
        }

    # $count / $min / $max wrap a single nested comparison.
    if not isinstance(op_arg, Mapping) or len(op_arg) != 1:
        raise ValidationError(
            f"{path}.{field_path}.{op.value}: expected a single-key comparison "
            f"mapping (e.g. {{'$gt': 5}})."
        )
    inner_token, inner_value = next(iter(op_arg.items()))
    if inner_token not in _COMPARISON_TOKENS:
        raise ValidationError(
            f"{path}.{field_path}.{op.value}: inner operator {inner_token!r} "
            f"is not a comparison; expected one of {sorted(_COMPARISON_TOKENS)}."
        )
    inner_op = ComparisonOp(inner_token)
    if inner_op is ComparisonOp.MATCHES:
        raise ValidationError(
            f"{path}.{field_path}.{op.value}: $matches is not supported inside "
            f"{op.value}."
        )
    _require_scalar(inner_value, path=f"{path}.{field_path}.{op.value}.{inner_token}")
    return {
        "type": "list_operation",
        "field_path": field_path,
        "operator": op.server,
        "value": inner_value,
        "comparison": inner_op.server,
    }


def _require_scalar(value: Any, *, path: str) -> None:
    if not isinstance(value, _ALLOWED_VALUE_TYPES):
        raise ValidationError(
            f"{path}: value must be one of str/int/float/bool/None, "
            f"got {type(value).__name__}."
        )
