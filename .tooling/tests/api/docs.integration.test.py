"""The themed Swagger UI.

Deliberately shallow. These rules are written against Swagger UI's own class names, so
an upgrade can rename them and the theme quietly stops applying -- and a suite that
failed over that would be failing over a cosmetic problem while the API works fine.
What is worth asserting is that the page still renders, still loads Swagger, and that
the palette stays the real Dracula one rather than drifting into approximations.
"""

import re

import pytest

from planner.api.docs import DRACULA_CSS, METHOD_COLOURS, swagger_ui

#: https://draculatheme.com -- if a value here changes, it is no longer Dracula.
PALETTE = {
    "background": "#282a36",
    "current_line": "#44475a",
    "foreground": "#f8f8f2",
    "comment": "#6272a4",
    "cyan": "#8be9fd",
    "green": "#50fa7b",
    "orange": "#ffb86c",
    "pink": "#ff79c6",
    "purple": "#bd93f9",
    "red": "#ff5555",
    "yellow": "#f1fa8c",
}


class TestThePageStillWorks:
    def test_docs_is_served(self, client):
        assert client.get("/docs").status_code == 200

    def test_it_is_still_swagger(self, client):
        """The theme must not have replaced the thing it is theming."""
        body = client.get("/docs").text
        assert "swagger" in body.lower()
        assert "swagger-ui" in body

    def test_it_points_at_this_api(self, client):
        assert "/openapi.json" in client.get("/docs").text

    def test_the_root_still_redirects_there(self, client):
        assert client.get("/", follow_redirects=False).headers["location"] == "/docs"

    def test_the_openapi_document_is_untouched(self, client):
        """Theming is presentation; the contract must not move."""
        doc = client.get("/openapi.json").json()
        assert doc["openapi"] and doc["paths"]

    def test_redoc_is_still_available(self, client):
        """Overriding /docs must not take the alternative down with it."""
        assert client.get("/redoc").status_code == 200


class TestTheTheme:
    def test_the_stylesheet_is_injected(self, client):
        body = client.get("/docs").text
        assert "<style>" in body
        assert PALETTE["background"] in body

    def test_it_lands_inside_head(self, client):
        """After Swagger's own sheet, or it would be outranked and do nothing."""
        body = client.get("/docs").text
        assert body.index("<style>") < body.index("</head>")

    @pytest.mark.parametrize("name,value", PALETTE.items())
    def test_the_palette_is_genuinely_dracula(self, name, value):
        assert value in DRACULA_CSS

    def test_no_colours_outside_the_palette(self):
        """One near-miss shade is how a theme stops looking like itself."""
        allowed = set(PALETTE.values()) | {"#21222c"}  # the darker code-block shade
        used = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", DRACULA_CSS)}
        assert used <= allowed, f"off-palette: {sorted(used - allowed)}"

    def test_every_method_this_api_uses_is_coloured(self):
        """A verb with no rule falls back to Swagger's own green, which reads as a
        POST and would make a DELETE look safe.
        """
        from planner.api.routes import ROUTES

        for route in ROUTES:
            assert route.method.lower() in METHOD_COLOURS

    def test_destructive_methods_are_not_reassuring(self):
        assert METHOD_COLOURS["delete"] == PALETTE["red"]
        assert METHOD_COLOURS["get"] == PALETTE["cyan"]
        assert METHOD_COLOURS["post"] == PALETTE["green"]

    def test_method_rules_are_generated_not_listed(self):
        """Otherwise adding a verb means remembering four selectors."""
        import inspect

        from planner.api import docs

        assert "_method_rules" in inspect.getsource(docs)
        for method in METHOD_COLOURS:
            assert f"opblock-{method}" in DRACULA_CSS


class TestTheHelper:
    def test_it_returns_html(self):
        response = swagger_ui(openapi_url="/openapi.json", title="T")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_the_title_is_used(self):
        body = swagger_ui(
            openapi_url="/openapi.json", title="Distinctive"
        ).body.decode()
        assert "Distinctive" in body


class TestSwaggerGreysAreOverridden:
    """Swagger paints several panels with translucent black -- rgba(0,0,0,.1) and the
    like. Over a light page that is a faint tint; over Dracula each one composites into
    a grey slab. They cannot be fixed by darkening the page, only by naming each
    offender, so this pins the ones that were actually wrong on screen.
    """

    @pytest.mark.parametrize(
        "selector",
        [
            ".model-box",  # the slab behind every schema name
            ".json-schema-2020-12",  # Swagger 5's second schema renderer
            ".model-hint",
            "section.models .model-container",
        ],
    )
    def test_the_offender_is_overridden(self, selector):
        assert selector in DRACULA_CSS

    def test_no_translucent_black_survives_in_our_sheet(self):
        """Using rgba(0,0,0,...) in a rule would recreate the same problem.

        Comments are stripped first: this file documents the offending values in prose,
        and a check that could not tell an explanation from a declaration would forbid
        writing down what went wrong.
        """
        rules = re.sub(r"/\*.*?\*/", "", DRACULA_CSS, flags=re.S)
        assert "rgba(0, 0, 0" not in rules
        assert "rgba(0,0,0" not in rules

    def test_overlays_use_the_palette_not_transparency_over_black(self):
        """Translucent Dracula grey over the Dracula background stays Dracula;
        translucent black over it does not.
        """
        assert "rgba(68, 71, 90" in DRACULA_CSS


class TestFavicon:
    def test_it_is_served_inline(self, client):
        """Swagger's default points at fastapi.tiangolo.com, so every tab load fetched
        a picture from someone else's server -- and showed nothing at all offline,
        which for a planner on a laptop is often.
        """
        body = client.get("/docs").text
        assert "fastapi.tiangolo.com" not in body
        assert "data:image/svg+xml" in body

    def test_it_uses_the_palette(self):
        from planner.api.docs import FAVICON

        for colour in ("bd93f9", "8be9fd", "282a36"):  # purple, cyan, background
            assert colour in FAVICON

    def test_it_is_a_complete_svg(self):
        from planner.api.docs import FAVICON

        assert FAVICON.startswith("data:image/svg+xml,")
        assert FAVICON.endswith("%3C/svg%3E")

    def test_it_is_small_enough_to_inline(self):
        """Inlining is only worth it while it stays cheap; a big one belongs in a
        file served as a route.
        """
        from planner.api.docs import FAVICON

        assert len(FAVICON) < 2000
