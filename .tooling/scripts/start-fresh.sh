#!/usr/bin/env bash
#
# Make this clone yours.
#
# A starter vault arrives carrying someone else's history: the demo notes that prove the
# views work, whatever the last machine built, and a git repository whose first commit is
# not yours. This removes all three and starts a fresh repository over the same files.
#
#     .tooling/scripts/start-fresh.sh              # say what would happen, change nothing
#     .tooling/scripts/start-fresh.sh --yes        # do it
#     .tooling/scripts/start-fresh.sh --yes --keep-git    # everything except the history
#
# A dry run by default rather than a y/n prompt: this deletes .git with no undo, and a
# prompt is answered without being read. Run it once to see the list, once to act.
#
# Nothing here needs the venv -- it may be one of the things being deleted -- so this is
# shell and stdlib python only.

set -euo pipefail

DRY=1
KEEP_GIT=0

for arg in "$@"; do
  case "$arg" in
    --yes|-y)   DRY=0 ;;
    --keep-git) KEEP_GIT=1 ;;
    --help|-h)  awk 'NR>2 && /^#/ {print substr($0, 3); next} NR>2 {exit}' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# The vault is the repository root; this script lives two levels down in
# .tooling/scripts/, the same arrangement demo/demo.py documents. Resolved from the
# script's own path so it can be run from anywhere.
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)

# Refuse to run anywhere that is not this vault. Every path below is under $ROOT and
# several are `rm -rf`, so a wrong root is the one failure worth being paranoid about.
if [[ ! -f $ROOT/System.md || ! -f $ROOT/.tooling/pyproject.toml ]]; then
  echo "not a planner vault: $ROOT" >&2
  exit 1
fi

if (( DRY )); then
  echo "DRY RUN — nothing will be changed. Re-run with --yes to apply."
else
  echo "Starting fresh in $ROOT"
fi
echo

drop() {  # remove one path if it is there, and say so either way
  local path=$1 label=${1#"$ROOT"/}
  [[ -e $path || -L $path ]] || return 0
  if (( DRY )); then
    printf '  would remove   %s\n' "$label"
  else
    rm -rf -- "$path"
    printf '  removed        %s\n' "$label"
  fi
}

# --- the demo notes ------------------------------------------------------------------
#
# Delegated to demo.py rather than reimplemented: it matches on the `demo: true`
# frontmatter marker, not on filenames, which is the only thing that finds the weekly
# review (named for the ISO week it was generated in, so its path moves) and any copy
# Obsidian Sync made during a load/clear cycle.

echo "Demo notes"
# `|| true` because grep exits 1 on no matches, which under `pipefail` is the normal
# case here -- a vault with no demo notes left -- not a failure.
demo_count=$( { grep -rl --include='*.md' '^demo: true$' \
                  "$ROOT"/Items "$ROOT"/Docs "$ROOT"/Meetings "$ROOT"/Reviews "$ROOT"/Journal \
                  2>/dev/null || true; } | wc -l | tr -d ' ')
if [[ $demo_count == 0 ]]; then
  echo "  none found"
elif (( DRY )); then
  printf '  would remove   %s note(s) carrying the demo: true marker\n' "$demo_count"
else
  python3 "$ROOT/.tooling/demo/demo.py" clear | sed 's/^/  /'
fi
echo

# --- build output --------------------------------------------------------------------
#
# All of it regenerates from `make install`, and none of it is portable between machines:
# a venv records absolute interpreter paths, so one that arrived in a zip or a Sync folder
# is broken on arrival rather than merely stale.

echo "Build output"
drop "$ROOT/.tooling/.venv"
drop "$ROOT/.venv"
drop "$ROOT/.tooling/htmlcov"
drop "$ROOT/.tooling/docs/api"
drop "$ROOT/.tooling/.pytest_cache"
drop "$ROOT/.tooling/.ruff_cache"
for stale in "$ROOT"/.tooling/.coverage*; do drop "$stale"; done
caches=$( { find "$ROOT/.tooling" \( -name __pycache__ -o -name '*.egg-info' \) -prune -print \
              2>/dev/null || true; } | wc -l | tr -d ' ')
if [[ $caches != 0 ]]; then
  if (( DRY )); then
    printf '  would remove   %s __pycache__/*.egg-info director(ies) under .tooling/\n' "$caches"
  else
    find "$ROOT/.tooling" \( -name __pycache__ -o -name '*.egg-info' \) -prune -exec rm -rf {} +
    printf '  removed        %s __pycache__/*.egg-info director(ies) under .tooling/\n' "$caches"
  fi
fi
echo

# --- state belonging to the previous machine -----------------------------------------

echo "Local state"
drop "$ROOT/.idea"                        # JetBrains project files
drop "$ROOT/.claude"                      # Claude Code's local settings
drop "$ROOT/.obsidian/workspace.json"     # which panes were open, on someone else's screen
drop "$ROOT/.obsidian/graph.json"
drop "$ROOT/.planner-journal.json"        # a transaction the API never finished
drop "$ROOT/.DS_Store"
echo

# --- git -----------------------------------------------------------------------------
#
# Deleting .git rather than rewriting it. Amending or squashing leaves the objects in
# place and the remote configured, which is how a starter vault ends up pushed back over
# the repository it came from.

echo "Git"
if (( KEEP_GIT )); then
  echo "  kept           --keep-git was passed"
elif (( DRY )); then
  echo "  would remove   .git, then re-init on 'main' with one commit"
else
  rm -rf -- "$ROOT/.git"
  git init -q -- "$ROOT"
  git -C "$ROOT" symbolic-ref HEAD refs/heads/main    # works on git older than `init -b`
  git -C "$ROOT" add -A
  if git -C "$ROOT" commit -qm "Start from the planner starter vault" 2>/dev/null; then
    echo "  re-initialised a new repository on 'main', one commit, no remote"
  else
    echo "  re-initialised a new repository on 'main' — everything is staged, but the"
    echo "                 commit failed: set user.name and user.email, then commit."
  fi
fi
echo

# --- what is left to do by hand ------------------------------------------------------

if (( DRY )); then
  echo "Re-run with --yes to apply."
  exit 0
fi

cat <<'NOTES'
Done. Next:

  cd .tooling && make install     # rebuild the venv
  make demo                       # optional: the throwaway dataset, to see the views full

Two things this deliberately left alone:

  * The demo titles are still listed in .gitignore, because `make demo` needs them
    ignored. That means a real note named e.g. "Items/Pay bills.md" would be ignored
    too -- delete its line there if you want one of those titles for real work.
  * Folder icons do not rebuild from frontmatter (folders have none). Set them once
    from the table in System.md -> Icons.

If you had the audit database running, `make clean` drops its volume too.
NOTES
