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
    """Recursively compile one condition node.

    Dispatches to :func:`_compile_logical` for ``$and``/``$or``/``$not`` keys
    and to :func:`_compile_field` for anything else; multi-key mappings are
    rewritten as an implicit ``$and`` before recursion.

    Args:
        spec (Any): The condition subtree to compile. Must be a non-empty
            :class:`~collections.abc.Mapping` at every level.
        path (str): Dotted trace of the position in the original spec, used
            verbatim in :class:`ValidationError` messages so the user can
            locate the problem.

    Returns:
        dict[str, Any]: A server-shaped condition node.

    Raises:
        ValidationError: If ``spec`` is not a mapping, is empty, or uses a
            ``$``-prefixed top-level key that is not a known logical operator.
    """
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
    """Compile a logical combinator node (``$and`` / ``$or`` / ``$not``).

    ``$not`` takes a single sub-condition; ``$and`` / ``$or`` take a
    non-empty list. The list form is validated here rather than in
    :func:`_compile` so error messages can name the specific operator.

    Args:
        op (LogicalOp): Which combinator to emit.
        value (Any): The operator's argument — a mapping for ``$not``, a
            list of mappings for ``$and`` / ``$or``.
        path (str): Trace path for :class:`ValidationError` messages.

    Returns:
        dict[str, Any]: A ``type="logical"`` condition node.

    Raises:
        ValidationError: If ``value`` has the wrong shape for ``op``.
    """
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
    """Compile a per-field condition (``field: {op: value, ...}``).

    Multiple operators on the same field are rewritten as an implicit
    ``$and`` of single-operator subtrees. A single operator is dispatched to
    either :func:`_build_field_comparison` or :func:`_build_list_operation`
    depending on whether it's a scalar or list-valued operator.

    Args:
        field_path (str): Dotted path of the field in the upstream context.
        ops (Any): The operator mapping (e.g. ``{"$gt": 5}`` or
            ``{"$gt": 0, "$lt": 10}``).
        path (str): Trace path for :class:`ValidationError` messages.

    Returns:
        dict[str, Any]: A server-shaped node — ``field_comparison``,
        ``list_operation``, or ``logical`` (for the multi-op AND fan-out).

    Raises:
        ValidationError: If ``ops`` is not a non-empty mapping, if an
            operator key is not a string, or if it is not a recognized
            comparison or list operator.
    """
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
    """Build a ``field_comparison`` node for a single scalar operator.

    ``$matches`` is handled specially: its value must be a regex string, not
    a number or bool.

    Args:
        field_path (str): Dotted path of the field being compared.
        op (ComparisonOp): The comparison operator.
        value (Any): The right-hand side. Must be scalar (str/int/float/
            bool/None); ``$matches`` further requires a string.
        path (str): Trace path for :class:`ValidationError` messages.

    Returns:
        dict[str, Any]: A ``type="field_comparison"`` condition node.

    Raises:
        ValidationError: If ``value`` is not a scalar, or if ``$matches`` is
            given a non-string.
    """
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
    """Build a ``list_operation`` node for a list-valued operator.

    ``$contains`` takes a bare scalar (membership test). ``$count``,
    ``$min``, and ``$max`` each wrap a single nested comparison that is
    applied to the count/min/max of the list. ``$matches`` is rejected as
    the nested comparison because a regex against an aggregate number is
    meaningless.

    Args:
        field_path (str): Dotted path of the list-valued field.
        op (ListOp): The list operator.
        op_arg (Any): For ``$contains``, a scalar; for the others, a
            single-entry comparison mapping (e.g. ``{"$gt": 5}``).
        path (str): Trace path for :class:`ValidationError` messages.

    Returns:
        dict[str, Any]: A ``type="list_operation"`` condition node.

    Raises:
        ValidationError: If ``op_arg`` has the wrong shape for ``op``, the
            nested operator is not a comparison, or the values are not
            scalars.
    """
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
    """Enforce that a condition value is a JSON scalar.

    Lists and dicts are rejected because the server condition grammar can't
    represent them as comparison RHS values — callers should use
    ``$contains`` / ``$count`` / ``$min`` / ``$max`` for list semantics.

    Args:
        value (Any): The value to check.
        path (str): Trace path for the :class:`ValidationError` message.

    Raises:
        ValidationError: If ``value`` is not one of str, int, float, bool,
            or None.
    """
    if not isinstance(value, _ALLOWED_VALUE_TYPES):
        raise ValidationError(
            f"{path}: value must be one of str/int/float/bool/None, "
            f"got {type(value).__name__}."
        )
