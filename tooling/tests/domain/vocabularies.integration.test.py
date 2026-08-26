"""The value sets and the enums generated from them."""

import pytest

from planner.domain import vocabularies as V
from planner.domain import schema as S


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
