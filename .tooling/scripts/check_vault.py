"""Fail if any committed note would be rejected by the API.

The notes are the product. A schema change that invalidates notes already in the vault
passes every unit test -- the tests build their own fixtures -- and breaks the real
thing. This checks the real thing.

    python scripts/check_vault.py [vault]

Writes GitHub Actions error annotations when running there, so a bad note is flagged on
the pull request rather than buried in a log.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from planner import open_vault  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Report invalid notes. Returns 1 if the vault has any."""
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path(os.environ.get("PLANNER_VAULT", ".."))
    problems = open_vault(root).problems()

    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for title, why in problems:
        prefix = "::error::" if in_actions else "  "
        print(f"{prefix}{title}: {why}")

    if problems:
        print(f"\n{len(problems)} note(s) the API would refuse. Fix them or the schema.")
        return 1
    print(f"vault at {root} is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
