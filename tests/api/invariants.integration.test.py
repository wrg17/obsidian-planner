"""The system invariants, as data.

They were written twice in app.py -- prose in the docstring, a table in the OpenAPI
description -- and two hand-maintained copies of nine rules in one file is how nine
rules become nine rules and nine slightly different ones. These tests pin that there is
now one source and that both renderings come from it.
"""

import re

import pytest

from planner.api.invariants import BY_ID, INVARIANTS, as_markdown_table, as_prose


class TestTheRecords:
    def test_there_are_nine(self):
        assert len(INVARIANTS) == 9

    def test_ids_are_sequential_and_unique(self):
        assert [i.id for i in INVARIANTS] == [f"S{n}" for n in range(1, 10)]

    @pytest.mark.parametrize("invariant", INVARIANTS, ids=lambda i: i.id)
    def test_each_is_complete(self, invariant):
        assert invariant.name.isupper()
        assert invariant.summary.strip()
        assert invariant.rationale.strip()

    @pytest.mark.parametrize("invariant", INVARIANTS, ids=lambda i: i.id)
    def test_each_says_whether_it_is_promised_or_merely_detected(self, invariant):
        """The distinction the whole design turns on: what this API will never do,
        versus what it will tell you about once someone else has."""
        assert invariant.kind in ("guarantee", "detection")

    def test_the_summary_is_shorter_than_the_rationale(self):
        """One is a table cell, the other is the reasoning. If they are the same
        length, one of them is wrong."""
        for invariant in INVARIANTS:
            assert len(invariant.summary) < len(invariant.rationale)

    def test_lookup_by_id(self):
        assert BY_ID["S1"].name == "CLOSURE"
        assert set(BY_ID) == {i.id for i in INVARIANTS}


class TestBothRenderingsComeFromTheRecords:
    def test_the_table_has_a_row_for_every_invariant(self):
        table = as_markdown_table()
        for invariant in INVARIANTS:
            assert f"**{invariant.id}**" in table
            assert invariant.summary in table

    def test_the_prose_has_an_entry_for_every_invariant(self):
        prose = as_prose()
        for invariant in INVARIANTS:
            assert f"{invariant.id}. {invariant.name}" in prose

    def test_the_table_is_valid_markdown(self):
        lines = as_markdown_table().splitlines()
        assert lines[1].startswith("|---")
        assert all(line.startswith("|") for line in lines)

    def test_both_renderings_stay_in_step(self):
        """The property that makes this worth doing: one record, two forms, no way for
        them to disagree about which invariants exist."""
        in_table = set(re.findall(r"\*\*(S\d)\*\*", as_markdown_table()))
        in_prose = set(re.findall(r"^(S\d)\.", as_prose(), re.M))
        assert in_table == in_prose == {i.id for i in INVARIANTS}


class TestTheyReachTheClient:
    def test_the_published_description_carries_the_table(self, client):
        """A client author should not have to read the source to learn what this API
        promises."""
        description = client.get("/openapi.json").json()["info"]["description"]
        for invariant in INVARIANTS:
            assert f"**{invariant.id}**" in description

    def test_the_summaries_are_published_verbatim(self, client):
        description = client.get("/openapi.json").json()["info"]["description"]
        for invariant in INVARIANTS:
            assert invariant.summary in description

    def test_the_guarantee_detection_split_is_published(self, client):
        description = client.get("/openapi.json").json()["info"]["description"]
        assert "guarantee" in description and "detection" in description

    def test_app_no_longer_restates_them(self):
        """The duplication this file exists to remove: app.py must not carry a second
        copy that can drift from this one."""
        import inspect
        import sys

        import planner.api.app  # noqa: F401
        source = inspect.getsource(sys.modules["planner.api.app"])
        # A stray `S4. ONE ERROR SHAPE` style heading would mean the prose came back.
        assert not re.findall(r"^S\d\. [A-Z]", source, re.M)


class TestEndpointsReferToThem:
    def test_handler_docstrings_cite_system_invariants(self):
        """Per-endpoint rules are meant to be instances of these, not a parallel set."""
        import inspect

        from planner.api.handlers import notes

        source = inspect.getsource(notes)
        cited = set(re.findall(r"\(S\d(?:, S\d)*\)", source))
        assert cited, "no handler traces a rule back to a system invariant"

    def test_every_cited_id_exists(self):
        import inspect

        from planner.api.handlers import meta, notes

        for module in (notes, meta):
            for match in re.findall(r"\bS(\d)\b", inspect.getsource(module)):
                assert f"S{match}" in BY_ID, f"cites S{match}, which is not defined"
