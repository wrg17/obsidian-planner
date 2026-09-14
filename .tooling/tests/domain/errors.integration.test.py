"""Domain errors. Small, but the API's status codes are keyed off these types, so
their hierarchy is load-bearing.
"""

import pytest

from planner.domain.errors import (
    NoteExistsError,
    NoteNotFoundError,
    PlannerError,
    ValidationError,
)


class TestHierarchy:
    @pytest.mark.parametrize(
        "cls", [ValidationError, NoteNotFoundError, NoteExistsError]
    )
    def test_all_are_planner_errors(self, cls):
        """middleware.install_error_handlers catches PlannerError once. Anything
        outside that tree escapes as a 500.
        """
        assert issubclass(cls, PlannerError)

    def test_planner_error_is_an_exception(self):
        assert issubclass(PlannerError, Exception)

    def test_types_are_distinct(self):
        """They map to different status codes, so isinstance must discriminate."""
        assert not issubclass(NoteNotFoundError, NoteExistsError)
        assert not issubclass(NoteExistsError, ValidationError)


class TestValidationError:
    def test_carries_the_offending_field(self):
        exc = ValidationError("bad status", "status")
        assert exc.field == "status"
        assert str(exc) == "bad status"

    def test_field_is_optional(self):
        assert ValidationError("something broke").field is None

    def test_can_be_raised_and_caught_as_planner_error(self):
        with pytest.raises(PlannerError) as caught:
            raise ValidationError("x", "y")
        assert caught.value.field == "y"


class TestOtherErrors:
    def test_not_found_carries_a_message(self):
        assert "Nope" in str(NoteNotFoundError("no note titled 'Nope'"))

    def test_exists_has_no_field_attribute(self):
        """Middleware reads `field` with getattr and a None default; this pins that
        the default is actually needed.
        """
        assert getattr(NoteExistsError("dup"), "field", None) is None
