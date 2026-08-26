"""The facade.

schema.py exists so that everything outside the domain has one import rather than
three. What is worth testing is not the rules -- those are covered next to the modules
that define them -- but that the facade stays complete: a name added to vocabularies,
fields or kinds and forgotten here would work in the domain and fail everywhere else.
"""

import pytest

from planner.domain import fields, kinds, schema, vocabularies


PUBLIC = [m for m in (vocabularies, fields, kinds)]


@pytest.mark.parametrize("module", PUBLIC, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_every_public_name_is_re_exported(module):
    """Anything a module exposes should be reachable through the facade, or callers
    end up importing past it and the split leaks outward."""
    # `StrEnum` is imported by these modules, not defined by them. Everything else
    # upper-cased or ending in Enum is a rule the facade is supposed to carry.
    imported = {"StrEnum"}
    missing = [
        name for name, value in vars(module).items()
        if not name.startswith("_")
        and name not in imported
        and (name.isupper() or name.endswith("Enum"))
        and not hasattr(schema, name)
    ]
    assert not missing, f"{module.__name__} exposes {missing} but the facade does not"


def test_the_helpers_are_reachable():
    assert schema.allowed_fields("task")
    assert schema.folder_for("task") == "Items"


def test_the_kind_dataclass_is_reachable():
    assert schema.Kind is kinds.Kind


def test_the_facade_adds_no_rules_of_its_own():
    """It re-exports and nothing else. A rule defined here would be invisible to the
    module it belongs with."""
    import inspect
    source = inspect.getsource(schema)
    assert "def " not in source
    assert "class " not in source


@pytest.mark.parametrize("name", [
    "KINDS", "KIND_NAMES", "TICKET_KINDS", "SHARED",
    "TICKET_STATUS", "ALL_STATUS", "ISSUE_TYPE", "RECUR", "PRIORITY_RANGE",
    "CLOSED_STATUS", "FIELD_TYPES", "LINK_FIELDS", "DATE_FIELDS", "LIST_FIELDS",
    "KindEnum", "StatusEnum", "IssueTypeEnum", "RecurEnum", "ClosingStatusEnum",
])
def test_the_names_callers_actually_use(name):
    assert hasattr(schema, name)
