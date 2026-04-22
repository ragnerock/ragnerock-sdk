"""Tests for the MongoDB-style condition grammar compiler."""

from __future__ import annotations

import pytest

from ragnerock.errors import ValidationError
from ragnerock.resources.condition import (
    ComparisonOp,
    ListOp,
    LogicalOp,
    compile_condition,
)


class TestFieldComparison:
    @pytest.mark.parametrize(
        "token,expected",
        [
            ("$eq", "=="),
            ("$ne", "!="),
            ("$gt", ">"),
            ("$lt", "<"),
            ("$gte", ">="),
            ("$lte", "<="),
        ],
    )
    def test_each_comparison_operator(self, token, expected):
        result = compile_condition({"field.path": {token: 5}})
        assert result == {
            "type": "field_comparison",
            "field_path": "field.path",
            "operator": expected,
            "value": 5,
        }

    def test_matches_takes_string_regex(self):
        result = compile_condition({"name": {"$matches": "^foo.*"}})
        assert result == {
            "type": "field_comparison",
            "field_path": "name",
            "operator": "matches",
            "value": "^foo.*",
        }

    def test_matches_rejects_non_string(self):
        with pytest.raises(ValidationError, match="regex value must be a string"):
            compile_condition({"name": {"$matches": 123}})

    @pytest.mark.parametrize("value", ["text", 1, 1.5, True, False, None])
    def test_accepts_all_scalar_value_types(self, value):
        result = compile_condition({"f": {"$eq": value}})
        assert result["value"] == value

    def test_rejects_list_value(self):
        with pytest.raises(ValidationError, match="value must be one of"):
            compile_condition({"f": {"$eq": [1, 2, 3]}})

    def test_rejects_dict_value(self):
        with pytest.raises(ValidationError, match="value must be one of"):
            compile_condition({"f": {"$gt": {"$eq": 1}}})


class TestListOperations:
    def test_contains(self):
        result = compile_condition({"tags": {"$contains": "urgent"}})
        assert result == {
            "type": "list_operation",
            "field_path": "tags",
            "operator": "contains",
            "value": "urgent",
            "comparison": None,
        }

    @pytest.mark.parametrize(
        "op,server_op",
        [("$count", "count"), ("$min", "min"), ("$max", "max")],
    )
    def test_count_min_max_with_comparison(self, op, server_op):
        result = compile_condition({"scores": {op: {"$gte": 0.5}}})
        assert result == {
            "type": "list_operation",
            "field_path": "scores",
            "operator": server_op,
            "value": 0.5,
            "comparison": ">=",
        }

    def test_count_requires_nested_comparison(self):
        with pytest.raises(ValidationError, match="expected a single-key"):
            compile_condition({"xs": {"$count": 5}})

    def test_count_rejects_matches_inside(self):
        with pytest.raises(ValidationError, match="matches is not supported"):
            compile_condition({"xs": {"$count": {"$matches": "x"}}})

    def test_count_rejects_list_op_inside(self):
        with pytest.raises(ValidationError, match="not a comparison"):
            compile_condition({"xs": {"$count": {"$contains": "x"}}})


class TestLogicalOperators:
    def test_and_combines_conditions(self):
        result = compile_condition(
            {
                "$and": [
                    {"a": {"$gt": 0}},
                    {"b": {"$eq": "x"}},
                ]
            }
        )
        assert result == {
            "type": "logical",
            "operator": "AND",
            "conditions": [
                {
                    "type": "field_comparison",
                    "field_path": "a",
                    "operator": ">",
                    "value": 0,
                },
                {
                    "type": "field_comparison",
                    "field_path": "b",
                    "operator": "==",
                    "value": "x",
                },
            ],
        }

    def test_or_combines_conditions(self):
        result = compile_condition({"$or": [{"a": {"$eq": 1}}, {"b": {"$eq": 2}}]})
        assert result["operator"] == "OR"
        assert len(result["conditions"]) == 2

    def test_not_wraps_single_condition(self):
        result = compile_condition({"$not": {"a": {"$gt": 0}}})
        assert result == {
            "type": "logical",
            "operator": "NOT",
            "condition": {
                "type": "field_comparison",
                "field_path": "a",
                "operator": ">",
                "value": 0,
            },
        }

    def test_not_rejects_list(self):
        with pytest.raises(ValidationError, match=r"\$not.*not a list"):
            compile_condition({"$not": [{"a": {"$gt": 0}}]})

    def test_and_rejects_non_list(self):
        with pytest.raises(ValidationError, match="non-empty list"):
            compile_condition({"$and": {"a": {"$eq": 1}}})

    def test_and_rejects_empty_list(self):
        with pytest.raises(ValidationError, match="non-empty list"):
            compile_condition({"$and": []})

    def test_nested_logicals(self):
        result = compile_condition(
            {
                "$or": [
                    {"$and": [{"a": {"$eq": 1}}, {"b": {"$eq": 2}}]},
                    {"$not": {"c": {"$gt": 5}}},
                ]
            }
        )
        assert result["operator"] == "OR"
        assert result["conditions"][0]["operator"] == "AND"
        assert result["conditions"][1]["operator"] == "NOT"


class TestImplicitAnd:
    def test_multiple_top_level_fields_and_together(self):
        result = compile_condition(
            {
                "a": {"$eq": 1},
                "b": {"$eq": 2},
            }
        )
        assert result["type"] == "logical"
        assert result["operator"] == "AND"
        assert len(result["conditions"]) == 2

    def test_multiple_ops_on_same_field_and_together(self):
        result = compile_condition({"score": {"$gte": 0.1, "$lte": 0.9}})
        assert result["operator"] == "AND"
        assert len(result["conditions"]) == 2
        ops = {c["operator"] for c in result["conditions"]}
        assert ops == {">=", "<="}


class TestErrorPaths:
    def test_non_mapping_rejected(self):
        with pytest.raises(ValidationError, match="expected a mapping"):
            compile_condition("oops")  # type: ignore[arg-type]

    def test_empty_mapping_rejected(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            compile_condition({})

    def test_unknown_top_level_operator(self):
        with pytest.raises(ValidationError, match="unknown top-level operator"):
            compile_condition({"$bogus": [{"a": {"$eq": 1}}]})

    def test_unknown_field_operator(self):
        with pytest.raises(ValidationError, match="unknown operator"):
            compile_condition({"field": {"$bogus": 0}})

    def test_field_ops_mapping_required(self):
        with pytest.raises(ValidationError, match="expected an operator mapping"):
            compile_condition({"field": 5})

    def test_error_path_includes_breadcrumb(self):
        with pytest.raises(ValidationError, match=r"condition\.\$and\[1\]"):
            compile_condition(
                {
                    "$and": [
                        {"a": {"$eq": 1}},
                        {"b": {"$bogus": 2}},
                    ]
                }
            )


class TestEnums:
    def test_comparison_enum_server_symbols(self):
        assert ComparisonOp.EQ.server == "=="
        assert ComparisonOp.NE.server == "!="
        assert ComparisonOp.GT.server == ">"
        assert ComparisonOp.LT.server == "<"
        assert ComparisonOp.GTE.server == ">="
        assert ComparisonOp.LTE.server == "<="
        assert ComparisonOp.MATCHES.server == "matches"

    def test_list_enum_server_symbols(self):
        assert ListOp.COUNT.server == "count"
        assert ListOp.CONTAINS.server == "contains"
        assert ListOp.MIN.server == "min"
        assert ListOp.MAX.server == "max"

    def test_logical_enum_server_symbols(self):
        assert LogicalOp.AND.server == "AND"
        assert LogicalOp.OR.server == "OR"
        assert LogicalOp.NOT.server == "NOT"

    def test_tokens_are_dollar_prefixed(self):
        for op in (*ComparisonOp, *ListOp, *LogicalOp):
            assert op.value.startswith("$"), op

    def test_enum_values_accepted_as_dict_keys(self):
        # Users can write `{ComparisonOp.GT.value: 5}` if they want programmatic
        # construction without stringly-typed tokens.
        result = compile_condition({"f": {ComparisonOp.GT.value: 5}})
        assert result["operator"] == ">"
