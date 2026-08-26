"""The vocabularies and kind definitions everything else is generated from.

These are mostly consistency checks rather than behaviour. That is deliberate: this
module is the single source of truth, so the failure mode worth guarding is not "the
code is wrong" but "two derived things disagree with it".
"""

import pytest

from planner.domain import schema as S


class TestKinds:
    def test_ten_kinds(self):
        assert len(S.KINDS) == 10

    def test_every_kind_knows_its_own_name(self):
        for name, kind in S.KINDS.items():
            assert kind.name == name

    def test_kind_names_matches_the_registry(self):
        assert list(S.KIND_NAMES) == list(S.KINDS)

    @pytest.mark.parametrize("name,kind", S.KINDS.items())
    def test_folder_is_one_we_actually_have(self, name, kind):
        assert kind.folder in ("Items", "Docs", "Meetings", "Reviews", "Journal")

    @pytest.mark.parametrize("name,kind", S.KINDS.items())
    def test_default_status_is_in_its_own_vocabulary(self, name, kind):
        """A default outside the vocabulary would make every new note of that kind
        land in Triage the moment it was created."""
        if kind.default_status is not None:
            assert kind.default_status in kind.statuses

    @pytest.mark.parametrize("name,kind", S.KINDS.items())
    def test_statusless_kinds_have_no_default(self, name, kind):
        if not kind.statuses:
            assert kind.default_status is None

    @pytest.mark.parametrize("name,kind", S.KINDS.items())
    def test_parent_kinds_exist(self, name, kind):
        for parent in kind.parent_kinds:
            assert parent in S.KINDS

    def test_only_tickets_carry_the_done_checkbox(self):
        assert {k.name for k in S.KINDS.values() if k.has_done} == set(S.TICKET_KINDS)

    def test_icons_are_lucide_ids_in_iconize_form(self):
        """Iconize's `Li` prefix plus CamelCase. A name it cannot resolve renders as
        nothing at all -- silently, which is the whole problem."""
        for kind in S.KINDS.values():
            assert kind.icon.startswith("Li")
            assert kind.icon[2].isupper()

    def test_colours_are_hex(self):
        """Unquoted hex is a YAML comment; the emitter quotes it, but a malformed
        value would still be written out."""
        for kind in S.KINDS.values():
            assert kind.colour.startswith("#") and len(kind.colour) == 7
            int(kind.colour[1:], 16)


class TestAllowedFields:
    def test_shared_fields_are_on_everything(self):
        for name in S.KIND_NAMES:
            assert set(S.SHARED) <= set(S.allowed_fields(name))

    def test_status_only_where_there_is_a_vocabulary(self):
        assert "status" in S.allowed_fields("task")
        assert "status" not in S.allowed_fields("meeting")

    def test_done_only_on_tickets(self):
        assert "done" in S.allowed_fields("task")
        assert "done" not in S.allowed_fields("area")

    def test_kind_specific_fields_are_included(self):
        assert "blocked_by" in S.allowed_fields("task")
        assert "blocked_by" not in S.allowed_fields("subtask")
        assert "recur" in S.allowed_fields("routine")

    @pytest.mark.parametrize("name", S.KIND_NAMES)
    def test_every_field_has_a_declared_type(self, name):
        """A field with no entry in FIELD_TYPES gets no coercion, so a date would
        stay a string and compare wrongly."""
        for field in S.allowed_fields(name):
            assert field in S.FIELD_TYPES, f"{name}.{field} has no type"


class TestVocabularies:
    def test_no_duplicates(self):
        for vocab in (S.TICKET_STATUS, S.ISSUE_TYPE, S.RECUR, S.ALL_STATUS):
            assert len(vocab) == len(set(vocab))

    def test_closing_statuses_are_real_ticket_statuses(self):
        assert set(S.CLOSED_STATUS) <= set(S.TICKET_STATUS)

    def test_all_status_is_the_union(self):
        union = set(S.TICKET_STATUS) | set(S.CONTAINER_STATUS) | set(S.ROUTINE_STATUS) \
            | set(S.DOC_STATUS) | set(S.DECISION_STATUS)
        assert set(S.ALL_STATUS) == union

    def test_every_kind_status_appears_in_all_status(self):
        for kind in S.KINDS.values():
            assert set(kind.statuses) <= set(S.ALL_STATUS)

    def test_priority_range_is_ordered(self):
        low, high = S.PRIORITY_RANGE
        assert low < high

    def test_vocabularies_are_lowercase(self):
        """Casing is enforced against these, so a capitalised entry here would make
        the error messages nonsense."""
        for vocab in (S.KIND_NAMES, S.ALL_STATUS, S.ISSUE_TYPE, S.RECUR):
            assert all(v == v.lower() for v in vocab)


class TestEnums:
    """Generated from the tuples above. A hand-written second copy is how an OpenAPI
    document ends up promising something the validator rejects."""

    @pytest.mark.parametrize("enum,source", [
        (S.KindEnum, S.KIND_NAMES),
        (S.IssueTypeEnum, S.ISSUE_TYPE),
        (S.RecurEnum, S.RECUR),
        (S.StatusEnum, S.ALL_STATUS),
        (S.ClosingStatusEnum, S.CLOSED_STATUS),
    ])
    def test_enum_matches_its_tuple(self, enum, source):
        assert [e.value for e in enum] == list(source)

    def test_enums_are_strings(self):
        """StrEnum so `kind == "task"` works and JSON serialisation is plain text."""
        assert S.KindEnum.TASK == "task"
        assert isinstance(S.KindEnum.TASK, str)


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


class TestFolderFor:
    def test_maps_kind_to_folder(self):
        assert S.folder_for("task") == "Items"
        assert S.folder_for("decision") == "Docs"
        assert S.folder_for("review") == "Reviews"

    def test_unknown_kind_raises(self):
        with pytest.raises(KeyError):
            S.folder_for("nope")
