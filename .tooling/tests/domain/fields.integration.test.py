"""Property types and the groupings derived from them."""

import pytest

from planner.domain import schema as S


class TestFieldTypeGroups:
    def test_groups_are_derived_from_field_types(self):
        assert S.LINK_FIELDS == {k for k, v in S.FIELD_TYPES.items() if v == S.LINK}
        assert S.DATE_FIELDS == {k for k, v in S.FIELD_TYPES.items() if v == S.DATE}

    def test_link_lists_are_a_subset_of_lists(self):
        assert S.LINK_LIST_FIELDS <= S.LIST_FIELDS

    def test_parent_is_a_single_link_not_a_list(self):
        """`parent == this` breaks on a list value, and so does the new-note
        prefill that makes the base factories work."""
        assert "parent" in S.LINK_FIELDS
        assert "parent" not in S.LIST_FIELDS
