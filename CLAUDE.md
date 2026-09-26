# Working in this repo

This file is read automatically at the start of every session. It is the house style,
and it exists because agents that re-derive conventions produce code that does not match
the code already here.

## What this is

An Obsidian vault (the markdown at the repo root) with a Python service beside it in
`.tooling/`. The vault is the product; the service models the same rules as code so the
vault can be validated, queried and edited without Obsidian open.

**The vault is the source of truth.** The service is one more writer alongside a human
in Obsidian, never the owner of the data.

## Before you start

```sh
cd .tooling
make install
make check     # lint + 1042 tests + docs freshness. Must pass before and after.
```

If `make check` fails before you have touched anything, say so and stop. You have
inherited a broken tree and fixing it is a different task from the one you were given.

## Branch and PR discipline

**Never commit to `main`.** Not for a one-line fix, not for a typo, not because the
change is obviously safe. Every change arrives as a pull request that CI has passed.

```sh
git checkout -b <topic>          # or: worktree, see below
# work
make check
gh pr create --fill
```

**One concern per PR.** A pull request that renames a method *and* adds a feature *and*
fixes a lint error is one that nobody reads properly, and the review that matters gets
spent on the parts that do not. If you notice something unrelated while working, write
it down and raise it separately.

**The PR description must describe the diff, not the intention.** State what changed and
why, and if something you set out to do did not land, say that instead of describing it
as though it did. A commit in this repo once described a README section that the diff did
not contain, because the edit had silently failed to match and nothing checked.

## Running in parallel

Several agents work here at once. Use a worktree so you cannot collide:

```sh
git worktree add .claude/worktrees/<topic> -b <topic>
cd .claude/worktrees/<topic>
```

Two things do **not** parallelise, and both will bite:

- **Obsidian opens one vault.** A worktree is a second copy of the notes. Fine for
  changes under `.tooling/`; not fine for changes to notes, bases or templates, which
  need the real vault.
- **The compose stack has a fixed project name and fixed ports** (`planner`, `8000`,
  `55433`). Two worktrees running `make up` fight over the same containers rather than
  getting one each. Export `COMPOSE_PROJECT_NAME` and override the ports, or only run
  the stack from one worktree at a time.

## House style

**Ruff decides formatting.** Do not argue with it, do not hand-format around it. Run
`make fmt`. The configuration in `pyproject.toml` carries a reason for every suppression;
if you add one, add the reason too.

**Comments explain decisions, not mechanics.** The code says what it does. A comment
earns its place by saying why it does that rather than the obvious alternative — why
`parent` is a single link and never a list, why deleting a blocker is allowed but
orphaning a child is not.

**A comment defending a workaround is a smell.** It usually means the thing being worked
around should go instead. One such comment in this repo explained six spellings of
`builtins.list[...]`; the real fix was renaming the method that shadowed the builtin.

**Tests are named for the invariant they prove** — `test_D2_deleting_a_parent_is_refused`
— so a failure names a documented rule rather than a bare assertion. The `D2` is a real
identifier; find it in `.tooling/src/planner/contracts/operations.py`.

**Documentation is generated where it restates code.** The endpoint table, the layer
diagram and the vocabularies come from `planner.docsgen`. Edit
`.tooling/docs/README.template.md`, never `README.md`. `make docs-check` fails the build
if they have drifted.

**One source of truth per fact.** Before adding a paragraph, check whether it already
exists somewhere. An extraction that leaves the original in place is worse than not
extracting: two copies drift, and a test asserting on the copy will keep it alive.

## What not to do

- Do not commit to `main`, or push to another agent's branch.
- Do not delete or rewrite notes in `Items/`, `Docs/`, `Meetings/`, `Reviews/` or
  `Journal/`. Those are the user's real work. The demo generator owns only files marked
  `demo: true`.
- Do not edit anything under `.obsidian/` in a text editor. Both plugins load their
  `data.json` once and rewrite it from memory, so an external edit is silently discarded.
- Do not lower the coverage gate, skip a failing test, or add `# noqa` without a reason
  beside it. If a check is wrong, change the check deliberately and say why in the PR.
- Do not claim something is verified that you have not run. "Tests pass" means you ran
  them and read the output.
