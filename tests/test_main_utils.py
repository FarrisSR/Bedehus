import logging
from pathlib import Path

from main import merge_dict, resolve_path, process_events


class TestMergeDict:
    def test_shallow_override(self):
        result = merge_dict({"a": 1, "b": 2}, {"b": 3, "c": 4})
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge_preserves_unoverridden_keys(self):
        result = merge_dict(
            {"a": {"x": 1, "y": 2}, "b": 10},
            {"a": {"y": 99, "z": 3}},
        )
        assert result == {"a": {"x": 1, "y": 99, "z": 3}, "b": 10}

    def test_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        merge_dict(base, {"a": {"x": 2}})
        assert base == {"a": {"x": 1}}

    def test_override_dict_with_scalar(self):
        result = merge_dict({"a": {"x": 1}}, {"a": "replaced"})
        assert result == {"a": "replaced"}

    def test_empty_override(self):
        base = {"a": 1}
        assert merge_dict(base, {}) == base

    def test_empty_base(self):
        assert merge_dict({}, {"a": 1}) == {"a": 1}


class TestResolvePath:
    def test_absolute_path_is_unchanged(self):
        assert resolve_path(Path("/base"), "/absolute") == Path("/absolute")

    def test_relative_path_is_joined(self):
        assert resolve_path(Path("/base"), "relative") == Path("/base/relative")

    def test_nested_relative(self):
        assert resolve_path(Path("/x/y"), "a/b/c") == Path("/x/y/a/b/c")


class TestProcessEvents:
    def test_empty_list_returns_false(self):
        assert process_events(logging.getLogger("test"), []) is False

    def test_non_empty_list_returns_true(self):
        events = [{"start": {"dateTime": "2024-06-15T10:00:00Z"}, "summary": "Møte"}]
        assert process_events(logging.getLogger("test"), events) is True

    def test_multiple_events_returns_true(self):
        events = [
            {"start": {"dateTime": "2024-06-15T10:00:00Z"}, "summary": "Møte"},
            {"start": {"date": "2024-06-16"}, "summary": "Gudstjeneste"},
        ]
        assert process_events(logging.getLogger("test"), events) is True
