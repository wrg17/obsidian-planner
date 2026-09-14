"""Invariants of the note endpoints.

Each class covers one endpoint and each test names the invariant it proves, using the
identifiers documented on the routes in src/planner/api/routers/notes.py. A failure
here should point at a stated rule, not just a broken assertion.
"""


# =====================================================================================
# GET /notes  --  L1..L7
# =====================================================================================


class TestListNotes:
    def test_L1_listing_is_pure(self, client, populated):
        """Reads must not touch mtime: Triage's "stale" view reads it, so a listing
        that bumped it would quietly reset everyone's staleness clock.
        """
        path = populated.repo.root / "Items" / "Pick a type scale.md"
        before = path.stat().st_mtime_ns
        client.get("/notes")
        client.get("/notes", params={"kind": "task"})
        assert path.stat().st_mtime_ns == before

    def test_L2_one_unreadable_note_does_not_break_the_listing(self, client, populated):
        (populated.repo.root / "Items" / "Broken.md").write_text("no frontmatter")
        r = client.get("/notes")
        assert r.status_code == 200
        assert "Broken" not in [n["title"] for n in r.json()]

    def test_L3_no_matches_is_an_empty_list_not_404(self, client):
        r = client.get("/notes", params={"project": "Nonexistent project"})
        assert r.status_code == 200 and r.json() == []

    def test_L4_filters_conjoin(self, client):
        """Adding a filter may only shrink the result."""
        tasks = client.get("/notes", params={"kind": "task"}).json()
        narrowed = client.get(
            "/notes", params={"kind": "task", "status": "doing"}
        ).json()
        assert len(narrowed) <= len(tasks)
        assert {n["title"] for n in narrowed} <= {n["title"] for n in tasks}

    def test_L4_filters_never_widen(self, client):
        everything = client.get("/notes").json()
        filtered = client.get("/notes", params={"kind": "epic"}).json()
        assert {n["title"] for n in filtered} <= {n["title"] for n in everything}

    def test_L5_order_is_deterministic(self, client):
        first = [n["title"] for n in client.get("/notes").json()]
        second = [n["title"] for n in client.get("/notes").json()]
        assert first == second == sorted(first)

    def test_L6_open_excludes_closed_by_either_signal(self, client):
        """`done` and a closing status are additive -- either one closes a ticket."""
        client.post("/notes/Pick a type scale/close")
        client.post(
            "/notes/Audit existing components/close", params={"status": "cancelled"}
        )
        open_titles = {
            n["title"]
            for n in client.get("/notes", params={"kind": "task", "open": True}).json()
        }
        assert "Pick a type scale" not in open_titles
        assert "Audit existing components" not in open_titles

    def test_L7_nothing_on_disk_is_invisible_to_the_api(self, client, populated):
        """The union covers the vault. Disjointness is NOT claimed -- see below."""
        (populated.repo.root / "Items" / "Typo.md").write_text(
            "---\nkind: task\nstatus: in-progress\n---\n"
        )
        (populated.repo.root / "Items" / "Unparseable.md").write_text("no frontmatter")
        listed = {n["title"] for n in client.get("/notes").json()}
        problems = {p["title"] for p in client.get("/problems").json()}
        assert listed | problems == set(populated.repo.titles())

    def test_L7_an_invalid_note_stays_listable_so_it_can_be_repaired(
        self, client, populated
    ):
        """The overlap is the point. Hiding a misspelled status from /notes would
        leave it fixable only by hand in Obsidian.
        """
        (populated.repo.root / "Items" / "Typo.md").write_text(
            "---\nkind: task\nstatus: in-progress\n---\n"
        )
        assert "Typo" in {n["title"] for n in client.get("/notes").json()}
        assert "Typo" in {p["title"] for p in client.get("/problems").json()}
        assert client.patch("/notes/Typo", json={"status": "doing"}).status_code == 200
        assert client.get("/problems").json() == []

    def test_L7_an_unparseable_note_appears_only_in_problems(self, client, populated):
        (populated.repo.root / "Items" / "Unparseable.md").write_text("no frontmatter")
        assert "Unparseable" not in {n["title"] for n in client.get("/notes").json()}
        assert "Unparseable" in {p["title"] for p in client.get("/problems").json()}

    def test_unknown_kind_is_rejected(self, client):
        assert client.get("/notes", params={"kind": "epicc"}).status_code == 422


# =====================================================================================
# POST /notes  --  C1..C8
# =====================================================================================


class TestCreateNote:
    def test_C1_repeat_is_a_conflict_never_an_overwrite(self, client):
        """A retried request must not destroy a note."""
        client.post(
            "/notes",
            json={"kind": "task", "title": "Once", "body": "\n# Once\n\noriginal\n"},
        )
        again = client.post(
            "/notes",
            json={"kind": "task", "title": "Once", "body": "\n# Once\n\nreplacement\n"},
        )
        assert again.status_code == 409
        assert "original" in client.get("/notes/Once").json()["body"]

    def test_C2_rejected_create_writes_nothing(self, client, populated):
        before = set(populated.repo.titles())
        client.post("/notes", json={"kind": "task", "title": "Bad", "priority": 99})
        assert set(populated.repo.titles()) == before

    def test_C3_folder_is_derived_from_kind(self, client, populated):
        client.post("/notes", json={"kind": "decision", "title": "ADR"})
        assert (populated.repo.root / "Docs" / "ADR.md").is_file()

    def test_C3_caller_cannot_choose_the_folder(self, client):
        assert (
            client.post(
                "/notes", json={"kind": "task", "title": "T", "folder": "Docs"}
            ).status_code
            == 422
        )

    def test_C4_titles_are_unique_case_insensitively(self, client):
        assert (
            client.post(
                "/notes", json={"kind": "task", "title": "pick a TYPE scale"}
            ).status_code
            == 409
        )

    def test_C5_dangling_parent_is_refused(self, client):
        r = client.post("/notes", json={"kind": "task", "title": "T", "parent": "Nope"})
        assert r.status_code == 422 and r.json()["field"] == "parent"

    def test_C5_wrong_parent_kind_is_refused(self, client):
        r = client.post(
            "/notes",
            json={"kind": "subtask", "title": "S", "parent": "Website relaunch"},
        )
        assert r.status_code == 422 and r.json()["field"] == "parent"

    def test_C6_defaults_are_applied_at_creation(self, client):
        body = client.post("/notes", json={"kind": "task", "title": "Fresh"}).json()
        assert body["status"] == "todo" and body["done"] is False and body["created"]

    def test_C7_response_equals_the_subsequent_get(self, client):
        created = client.post(
            "/notes", json={"kind": "task", "title": "Echo", "priority": 2}
        ).json()
        assert client.get("/notes/Echo").json() == created

    def test_C8_created_notes_never_appear_in_problems(self, client):
        for kind in ("area", "project", "epic", "task", "routine", "doc", "meeting"):
            client.post("/notes", json={"kind": kind, "title": f"Clean {kind}"})
        assert client.get("/problems").json() == []


# =====================================================================================
# GET /notes/{title}  --  G1..G5
# =====================================================================================


class TestGetNote:
    def test_G1_fetch_is_pure(self, client, populated):
        path = populated.repo.root / "Items" / "Pick a type scale.md"
        before = path.stat().st_mtime_ns
        client.get("/notes/Pick a type scale")
        assert path.stat().st_mtime_ns == before

    def test_G2_lookup_is_case_insensitive_like_creation(self, client):
        """Otherwise the same request 200s on macOS and 404s on Linux, with the
        filesystem rather than the application deciding.
        """
        assert client.get("/notes/pick a TYPE scale").status_code == 200

    def test_G3_missing_is_404_in_the_standard_shape(self, client):
        r = client.get("/notes/Nope")
        assert r.status_code == 404 and set(r.json()) == {"detail", "field"}

    def test_G4_links_are_plain_titles(self, client):
        assert (
            client.get("/notes/Pick a type scale").json()["parent"] == "Design system"
        )

    def test_G4_derived_presentation_fields_are_not_echoed(self, client):
        body = client.get("/notes/Pick a type scale").json()
        assert "icon" not in body and "iconColor" not in body

    def test_G5_response_can_be_fed_back_in_to_reproduce_the_note(
        self, client, other_vault
    ):
        """Lossless: what comes out is enough to recreate what went in."""
        from planner.domain.note import Note

        original = client.get("/notes/Design system").json()
        detached = {k: v for k, v in original.items() if k not in ("parent", "project")}
        other_vault.create(Note.from_dict(detached))
        copied = other_vault.get("Design system")
        assert copied.kind == original["kind"]
        assert copied.fields["status"] == original["status"]
        assert copied.fields["type"] == original["type"]
        assert copied.body == original["body"]


# =====================================================================================
# PATCH /notes/{title}  --  U1..U6
# =====================================================================================


class TestUpdateNote:
    def test_U1_patch_is_idempotent(self, client):
        first = client.patch(
            "/notes/Pick a type scale", json={"status": "review"}
        ).json()
        second = client.patch(
            "/notes/Pick a type scale", json={"status": "review"}
        ).json()
        assert first == second

    def test_U2_untouched_fields_survive(self, client):
        before = client.get("/notes/Pick a type scale").json()
        client.patch("/notes/Pick a type scale", json={"status": "review"})
        after = client.get("/notes/Pick a type scale").json()
        for key in set(before) - {"status"}:
            assert after[key] == before[key], key

    def test_U2_body_is_preserved_byte_for_byte(self, client):
        before = client.get("/notes/Design system").json()["body"]
        client.patch("/notes/Design system", json={"priority": 4})
        assert client.get("/notes/Design system").json()["body"] == before

    def test_U2_absent_and_null_differ(self, client):
        """Absent leaves the field alone; null removes it."""
        client.patch("/notes/Pick a type scale", json={"status": "review"})
        assert "due" in client.get("/notes/Pick a type scale").json()
        client.patch("/notes/Pick a type scale", json={"due": None})
        assert "due" not in client.get("/notes/Pick a type scale").json()

    def test_U3_rejected_patch_changes_nothing(self, client):
        before = client.get("/notes/Pick a type scale").json()
        client.patch("/notes/Pick a type scale", json={"priority": 99})
        assert client.get("/notes/Pick a type scale").json() == before

    def test_U4_kind_is_immutable(self, client):
        r = client.patch("/notes/Pick a type scale", json={"kind": "epic"})
        assert r.status_code == 422 and r.json()["field"] == "kind"

    def test_U5_title_is_ignored_not_applied(self, client):
        client.patch("/notes/Pick a type scale", json={"title": "Renamed"})
        assert client.get("/notes/Pick a type scale").status_code == 200
        assert client.get("/notes/Renamed").status_code == 404

    def test_U6_patch_cannot_introduce_a_dangling_parent(self, client):
        r = client.patch("/notes/Pick a type scale", json={"parent": "Nope"})
        assert r.status_code == 422 and r.json()["field"] == "parent"

    def test_U6_patch_cannot_introduce_a_foreign_field(self, client):
        assert client.patch("/notes/Studio", json={"recur": "daily"}).status_code == 422

    def test_U6_result_satisfies_what_post_would_require(self, client):
        client.patch("/notes/Pick a type scale", json={"priority": 3})
        assert client.get("/problems").json() == []


# =====================================================================================
# DELETE /notes/{title}  --  D1..D6
# =====================================================================================


class TestDeleteNote:
    def test_D1_second_delete_is_404_like_every_other_verb(self, client):
        assert client.delete("/notes/Test at 320px").status_code == 204
        assert client.delete("/notes/Test at 320px").status_code == 404
        assert client.get("/notes/Test at 320px").status_code == 404

    def test_D2_deleting_a_parent_is_refused(self, client):
        r = client.delete("/notes/Design system")
        assert r.status_code == 409
        assert "child" in r.json()["detail"]
        assert client.get("/notes/Design system").status_code == 200

    def test_D2_closure_holds_the_api_cannot_create_a_dangling_parent(self, client):
        """The invariant this exists for: no route may produce a state POST refuses."""
        client.delete("/notes/Design system")  # refused
        assert client.get("/problems").json() == []

    def test_D2_a_leaf_deletes_freely(self, client):
        assert client.delete("/notes/Test at 320px").status_code == 204

    def test_D3_cascade_removes_the_whole_subtree(self, client):
        assert (
            client.delete("/notes/Design system", params={"cascade": True}).status_code
            == 204
        )
        for title in ("Design system", "Pick a type scale", "Test at 320px"):
            assert client.get(f"/notes/{title}").status_code == 404

    def test_D3_cascade_leaves_no_dangling_links_behind(self, client):
        client.delete("/notes/Design system", params={"cascade": True})
        remaining = {p["title"] for p in client.get("/problems").json()}
        assert not any(
            "parent" in p["message"] for p in client.get("/problems").json()
        ), remaining

    def test_D3_cascade_does_not_touch_siblings(self, client):
        client.delete("/notes/Design system", params={"cascade": True})
        assert client.get("/notes/Content migration").status_code == 200

    def test_D4_cascade_terminates_on_a_hand_edited_cycle(self, client, populated):
        a = populated.repo.root / "Items" / "Loop A.md"
        b = populated.repo.root / "Items" / "Loop B.md"
        a.write_text('---\nkind: task\nparent: "[[Loop B]]"\n---\n')
        b.write_text('---\nkind: task\nparent: "[[Loop A]]"\n---\n')
        assert (
            client.delete("/notes/Loop A", params={"cascade": True}).status_code == 204
        )

    def test_D5_no_body_on_success(self, client):
        assert client.delete("/notes/Test at 320px").content == b""

    def test_D6_non_structural_references_are_left_alone(self, client, populated):
        """`blocked_by` pointing at a deleted note is reported, not silently rewritten
        -- editing notes the caller did not name is worse than a stale reference.
        """
        blocker = client.get("/notes/Export old posts").json()["blocked_by"]
        assert blocker == ["Pick a type scale"]
        client.delete("/notes/Pick a type scale", params={"cascade": True})
        assert client.get("/notes/Export old posts").json()["blocked_by"] == [
            "Pick a type scale"
        ]
        assert any("blocked_by" in p["message"] for p in client.get("/problems").json())


# =====================================================================================
# GET /notes/{title}/children  --  H1..H7
# =====================================================================================


class TestChildren:
    def test_H1_is_pure(self, client, populated):
        path = populated.repo.root / "Items" / "Design system.md"
        before = path.stat().st_mtime_ns
        client.get("/notes/Design system/children", params={"recursive": True})
        assert path.stat().st_mtime_ns == before

    def test_H2_missing_parent_is_404_not_empty(self, client):
        assert client.get("/notes/Nope/children").status_code == 404

    def test_H2_childless_note_is_an_empty_list(self, client):
        r = client.get("/notes/Test at 320px/children")
        assert r.status_code == 200 and r.json() == []

    def test_H3_recursive_is_a_superset_of_direct(self, client):
        direct = {
            n["title"] for n in client.get("/notes/Design system/children").json()
        }
        deep = {
            n["title"]
            for n in client.get(
                "/notes/Design system/children", params={"recursive": True}
            ).json()
        }
        assert direct <= deep

    def test_H4_never_includes_itself(self, client, populated):
        (populated.repo.root / "Items" / "Selfref.md").write_text(
            '---\nkind: task\nparent: "[[Selfref]]"\n---\n'
        )
        titles = [
            n["title"]
            for n in client.get(
                "/notes/Selfref/children", params={"recursive": True}
            ).json()
        ]
        assert "Selfref" not in titles

    def test_H5_terminates_on_a_cycle(self, client, populated):
        a = populated.repo.root / "Items" / "Loop A.md"
        b = populated.repo.root / "Items" / "Loop B.md"
        a.write_text('---\nkind: task\nparent: "[[Loop B]]"\n---\n')
        b.write_text('---\nkind: task\nparent: "[[Loop A]]"\n---\n')
        r = client.get("/notes/Loop A/children", params={"recursive": True})
        assert r.status_code == 200

    def test_H6_each_note_appears_once(self, client):
        titles = [
            n["title"]
            for n in client.get(
                "/notes/Website relaunch/children", params={"recursive": True}
            ).json()
        ]
        assert len(titles) == len(set(titles))

    def test_H7_the_recursive_walk_bases_cannot_do(self, client):
        deep = {
            n["title"]
            for n in client.get(
                "/notes/Website relaunch/children", params={"recursive": True}
            ).json()
        }
        assert {"Design system", "Pick a type scale", "Test at 320px"} <= deep


# =====================================================================================
# POST /notes/{title}/close and /reopen  --  X1..X7, R1..R6
# =====================================================================================


class TestClose:
    def test_X1_all_three_fields_move_together(self, client):
        body = client.post("/notes/Pick a type scale/close").json()
        assert body["status"] == "done"
        assert body["done"] is True
        assert "closed" in body

    def test_X2_cancelling_closes_without_claiming_it_was_done(self, client):
        body = client.post(
            "/notes/Pick a type scale/close", params={"status": "cancelled"}
        ).json()
        assert body["status"] == "cancelled"
        assert body["done"] is False
        assert "closed" in body

    def test_X3_post_condition_is_not_open(self, client):
        client.post("/notes/Pick a type scale/close")
        assert "Pick a type scale" not in [
            n["title"] for n in client.get("/notes", params={"open": True}).json()
        ]

    def test_X4_closing_twice_is_stable(self, client):
        first = client.post(
            "/notes/Pick a type scale/close", params={"on": "2026-08-20"}
        ).json()
        second = client.post(
            "/notes/Pick a type scale/close", params={"on": "2026-08-20"}
        ).json()
        assert first == second

    def test_X5_a_doc_cannot_be_closed_and_the_reason_says_so(self, client):
        r = client.post("/notes/Worktop options/close")
        assert r.status_code == 422
        assert r.json()["field"] == "kind"
        assert "doc" in r.json()["detail"] and "cannot be closed" in r.json()["detail"]

    def test_X6_only_closing_statuses_are_accepted(self, client):
        assert (
            client.post(
                "/notes/Pick a type scale/close", params={"status": "doing"}
            ).status_code
            == 422
        )

    def test_X7_close_is_reversible(self, client):
        before = client.get("/notes/Pick a type scale").json()
        client.post("/notes/Pick a type scale/close")
        after = client.post(
            "/notes/Pick a type scale/reopen", params={"status": before["status"]}
        ).json()
        assert after["status"] == before["status"] and after["done"] is False


class TestReopen:
    def test_R1_clears_what_close_set(self, client):
        client.post("/notes/Pick a type scale/close")
        body = client.post("/notes/Pick a type scale/reopen").json()
        assert "closed" not in body and body["done"] is False

    def test_R2_post_condition_is_open(self, client):
        client.post("/notes/Pick a type scale/close")
        client.post("/notes/Pick a type scale/reopen")
        assert "Pick a type scale" in [
            n["title"] for n in client.get("/notes", params={"open": True}).json()
        ]

    def test_R3_target_status_must_be_in_the_kind_vocabulary(self, client):
        client.post("/notes/Pick a type scale/close")
        assert (
            client.post(
                "/notes/Pick a type scale/reopen", params={"status": "active"}
            ).status_code
            == 422
        )

    def test_R4_tickets_only(self, client):
        r = client.post("/notes/Worktop options/reopen")
        assert r.status_code == 422 and r.json()["field"] == "kind"

    def test_R5_idempotent(self, client):
        client.post("/notes/Pick a type scale/close")
        first = client.post("/notes/Pick a type scale/reopen").json()
        second = client.post("/notes/Pick a type scale/reopen").json()
        assert first == second

    def test_R6_safe_on_an_already_open_ticket(self, client):
        body = client.post(
            "/notes/Audit existing components/reopen", params={"status": "doing"}
        ).json()
        assert body["status"] == "doing"


class TestTitleIdentity:
    """A note's identity is what is stored, not how a caller spelled it. Both
    invariants (G2 lookup, C4 uniqueness) are case-insensitive, so a response that
    echoed the request would report a title no note has -- and one that would 409 as
    a case clash if fed back (S9).
    """

    def test_get_returns_the_stored_spelling(self, client):
        assert (
            client.get("/notes/PICK A TYPE SCALE").json()["title"]
            == "Pick a type scale"
        )

    def test_patch_returns_the_stored_spelling(self, client):
        body = client.patch("/notes/pick a type scale", json={"priority": 3}).json()
        assert body["title"] == "Pick a type scale"

    def test_close_returns_the_stored_spelling(self, client):
        assert (
            client.post("/notes/PICK A TYPE SCALE/close").json()["title"]
            == "Pick a type scale"
        )

    def test_the_echoed_title_can_be_fed_straight_back(self, client, other_vault):
        from planner.domain.note import Note

        body = client.get("/notes/PICK A TYPE SCALE").json()
        detached = {
            k: v
            for k, v in body.items()
            if k not in ("parent", "project", "blocked_by")
        }
        other_vault.create(Note.from_dict(detached))
        assert other_vault.exists("Pick a type scale")

    def test_children_lookup_is_case_insensitive_too(self, client):
        r = client.get("/notes/DESIGN SYSTEM/children")
        assert r.status_code == 200 and r.json()


class TestBulkCreate:
    """B1..B5 -- the endpoint the unit of work exists for."""

    def test_B1_a_clean_batch_is_written(self, client):
        r = client.post(
            "/notes/bulk",
            json=[
                {"kind": "task", "title": "Bulk one"},
                {"kind": "task", "title": "Bulk two"},
            ],
        )
        assert r.status_code == 201
        assert [n["title"] for n in r.json()] == ["Bulk one", "Bulk two"]

    def test_B1_one_bad_note_undoes_the_whole_batch(self, client, populated):
        before = set(populated.repo.titles())
        r = client.post(
            "/notes/bulk",
            json=[
                {"kind": "task", "title": "Bulk one"},
                {"kind": "task", "title": "Bulk two"},
                {"kind": "task", "title": "Bulk three", "parent": "Ghost"},
            ],
        )
        assert r.status_code == 422
        assert set(populated.repo.titles()) == before

    def test_B1_a_duplicate_inside_the_batch_undoes_it(self, client, populated):
        before = set(populated.repo.titles())
        r = client.post(
            "/notes/bulk",
            json=[
                {"kind": "task", "title": "Twice"},
                {"kind": "task", "title": "Twice"},
            ],
        )
        assert r.status_code == 409
        assert set(populated.repo.titles()) == before

    def test_B2_per_note_rules_still_apply(self, client):
        assert (
            client.post(
                "/notes/bulk",
                json=[{"kind": "task", "title": "X", "status": "in-progress"}],
            ).status_code
            == 422
        )

    def test_B2_defaults_are_applied_to_each(self, client):
        body = client.post(
            "/notes/bulk", json=[{"kind": "task", "title": "Defaulted"}]
        ).json()
        assert body[0]["status"] == "todo" and body[0]["done"] is False

    def test_B3_a_parent_earlier_in_the_batch_is_visible_to_its_child(self, client):
        r = client.post(
            "/notes/bulk",
            json=[
                {
                    "kind": "epic",
                    "title": "New epic",
                    "parent": "Website relaunch",
                    "project": "Website relaunch",
                },
                {"kind": "task", "title": "New task", "parent": "New epic"},
            ],
        )
        assert r.status_code == 201

    def test_B3_the_reverse_order_fails(self, client):
        r = client.post(
            "/notes/bulk",
            json=[
                {"kind": "task", "title": "New task", "parent": "New epic"},
                {"kind": "epic", "title": "New epic", "parent": "Website relaunch"},
            ],
        )
        assert r.status_code == 422 and r.json()["field"] == "parent"

    def test_B4_the_error_names_the_offending_note(self, client):
        r = client.post(
            "/notes/bulk",
            json=[
                {"kind": "task", "title": "Fine"},
                {"kind": "task", "title": "Broken", "parent": "Ghost"},
            ],
        )
        detail = r.json()["detail"]
        assert "Broken" in detail and "note 1" in detail

    def test_an_empty_batch_is_accepted(self, client):
        assert client.post("/notes/bulk", json=[]).json() == []

    def test_the_batch_leaves_problems_empty(self, client):
        client.post(
            "/notes/bulk",
            json=[
                {"kind": "doc", "title": "Bulk doc"},
                {"kind": "meeting", "title": "Bulk meeting"},
            ],
        )
        assert client.get("/problems").json() == []
