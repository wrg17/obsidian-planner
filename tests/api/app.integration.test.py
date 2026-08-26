"""OpenAPI assembly: the document the app publishes about itself."""

import pytest


class TestOpenApi:
    def test_document_is_served(self, client):
        assert client.get("/openapi.json").status_code == 200

    def test_swagger_ui_is_served(self, client):
        r = client.get("/docs")
        assert r.status_code == 200 and "swagger" in r.text.lower()

    def test_root_redirects_to_docs(self, client):
        assert client.get("/", follow_redirects=False).headers["location"] == "/docs"

    def test_every_route_is_documented(self, client):
        doc = client.get("/openapi.json").json()
        for path in ("/notes", "/notes/{title}", "/notes/{title}/close",
                     "/schema", "/problems"):
            assert path in doc["paths"], f"{path} missing from OpenAPI"

    def test_operations_carry_summaries_and_tags(self, client):
        doc = client.get("/openapi.json").json()
        for path, ops in doc["paths"].items():
            for verb, op in ops.items():
                assert op.get("tags"), f"{verb.upper()} {path} has no tag"
                assert op.get("summary") or op.get("description"), \
                    f"{verb.upper()} {path} is undocumented"

    def test_error_shapes_are_declared(self, client):
        doc = client.get("/openapi.json").json()
        assert "422" in doc["paths"]["/notes"]["post"]["responses"]
