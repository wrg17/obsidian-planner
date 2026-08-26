---
kind: doc
icon: LiSlidersHorizontal
iconColor: "#64748B"
status: current
created: "2026-08-12"
---

# System

Jira and Confluence in Obsidian, built on `.base` files, the Templates core plugin, and
frontmatter properties, plus two community plugins: **Iconize** for icons and **Templater** for
templates that fill and file themselves.

Iconize is purely cosmetic — disable it and nothing breaks. **Templater is not**: the templates in
`Templates/` use `<% … %>` syntax, so with Templater disabled a new note would contain those tags
literally. That is the trade for automatic filing and titling. The tracked git history is your way
back if you ever want the vanilla versions.

## Setup checklist

Do these once, in order.

1. Open this folder as a vault (**Open folder as vault**) and trust it.
2. **Settings → Core plugins**: turn on **Bases** and **Templates**.
3. **Settings → Templates → Template folder location** = `Templates`.
4. **Settings → Files and links → Default location for new notes** = `Items`.
5. **Settings → Editor → Properties in document** = `Source`. Without this, Live Preview can
   overwrite template variables while you edit templates.
6. **Settings → Hotkeys** → set a shortcut for **Templater: Open insert template modal**. (Also
   worth one for **Templater: Create new note from template**.)
7. Property types — see [[#Property types]] below. Already written; nothing to do unless you edit.
8. **Settings → Core plugins → Daily notes**: set **New file location** = `Journal`, **Template
   file location** = `Templates/Daily`, and date format `YYYY-MM-DD`. This is what gives you a
   fresh checklist every morning. (Three clicks in the UI — I didn't write the config file for it
   because I couldn't verify its key names from the app bundle, and guessing at config is how you
   get silent breakage.)
9. **Reload the vault** (`Cmd+R`) once after any change to `.obsidian/plugins/*/data.json` made
   outside the app — Iconize holds its data in memory and will otherwise overwrite it.
10. Open [[Home]] and pin it. Optionally drag `Bases/Today.base` into the right sidebar; a base
    in the sidebar follows whichever note you have open, so `this`-based views track it.

## The types

Every note carries `kind`. That field is what makes types real to Bases — filters and views key
off it.

%%generated:kinds%%

| Kind | Folder | Own fields |
|---|---|---|
| `area` | `Items/` | `status` |
| `project` | `Items/` | `status`, `area`, `priority`, `due`, `closed` |
| `epic` | `Items/` | `status`, `done`, `type`, `parent`, `project`, `priority`, `due`, `closed` |
| `task` | `Items/` | `status`, `done`, `type`, `parent`, `project`, `priority`, `due`, `scheduled`, `closed`, `blocked_by` |
| `subtask` | `Items/` | `status`, `done`, `type`, `parent`, `project`, `priority`, `due`, `closed` |
| `routine` | `Items/` | `status`, `area`, `recur`, `last_done` |
| `doc` | `Docs/` | `status`, `project`, `area` |
| `decision` | `Docs/` | `status`, `project`, `date`, `supersedes` |
| `meeting` | `Meetings/` | `project`, `date`, `attendees` |
| `review` | `Reviews/` | `week` |

%%/generated:kinds%%

### Vocabularies

Typos are silent bugs — a misspelled status means work vanishes from the board. There is no enum
property type in vanilla Obsidian, so **Triage → Invalid values** catches them instead. Check it
weekly.

%%generated:vocabularies%%

| | |
|---|---|
| **Ticket status** | `backlog` · `todo` · `doing` · `blocked` · `review` · `done` · `cancelled` |
| **Container status** | `active` · `paused` · `done` |
| **Routine status** | `active` · `paused` |
| **Doc status** | `draft` · `current` · `stale` |
| **Decision status** | `proposed` · `accepted` · `rejected` · `superseded` |
| **Issue type** | `feature` · `bug` · `chore` · `spike` · `research` |
| **Recurrence** | `daily` · `weekdays` · `weekly` · `monthly` |
| **Priority** | `1` (highest) … `4` — a number, so it sorts correctly |

%%/generated:vocabularies%%

These are generated from `.tooling/src/planner/domain/vocabularies.py`, the module the
API validates against, so this table cannot promise a value the tooling would reject.

## Hierarchy

```
Studio (area)
└─ Website relaunch (project)     area: [[Studio]]
   └─ Design system (epic)        parent: [[Website relaunch]]  project: [[Website relaunch]]
      └─ Pick a type scale (task) parent: [[Design system]]      project: [[Website relaunch]]
         └─ Test at 320px         parent: [[Pick a type scale]]  project: [[Website relaunch]]
```

Two rules make everything else work:

1. **`parent` is a single link, never a list.** Views filter with `parent == this`, and a list
   value breaks both the filter and the auto-fill described below.
2. **`project` is copied onto every epic, task, and subtask.** This is redundant with `parent`
   and it is deliberate: Bases cannot walk a parent chain — no joins, no recursion — so without
   `project` on the note itself, "everything in Website relaunch" is not expressible. If it goes
   missing, **Triage → Missing project** lists the offenders; select the cells in a table view
   and paste the value into all of them at once.

## Creating things

**Every embedded view is a factory.** Its filters are the constructor: the **New** button creates a
note with every property that view filters on by equality already set. That is the trick that
replaces scripting, and it means you almost never create a note from scratch — you create it *from
the place it belongs*.

Where to click, for each thing you might make:

| To create | Open | Click New in |
|---|---|---|
| a task under an epic | that epic | `Tasks` → sets `kind: task`, `parent` |
| a subtask under a task | that task | `Subtasks` → sets `kind: subtask`, `parent` |
| an epic in a project | that project | `Epics` → sets `kind: epic`, `parent` |
| a project in an area | that area | `Projects` → sets `kind: project`, `area` |
| an action item from a meeting | that meeting | `Action items` → sets `kind: task`, `parent` |
| a doc for a project | that project | `Docs` → sets `kind: doc`, `project` |
| anything, unparented | `Board.base` | `New` → sets `kind` from the global filter |

Each base and each factory block sets `newItemFolder`, so new notes land in `Items/` (or `Docs/`,
`Meetings/`) regardless of your global default-location setting.

Then press your **Insert template** hotkey (bind it to **Templater: Open insert template modal**)
to add the body. Templater also **files the note for itself** — each template starts with a line
like `<%* if (tp.file.folder(true) !== "Docs") { await tp.file.move("Docs/" + tp.file.title) } %>`,
so applying the Doc template moves the note to `Docs/`, and the Weekly Review template names itself
`2026-W33` and moves to `Reviews/` with no input at all. The Meeting template asks once for a topic
and files itself as `Meetings/2026-08-12 topic`.

For anything with no parent — a review, a standalone doc — skip the two-step entirely and use
**Templater: Create new note from template**. That is a genuine one-click factory: pick the
template, and it creates, names, fills, and files the note.

**Why not have Bases apply the template for you?** There is a `newItemTemplate` key that looks
like it should do exactly that, and it is a trap here. In the creation code the filter-derived
frontmatter is only computed when no template was found (`u || (s = …frontmatter)`), so setting
`newItemTemplate` **suppresses the `kind`/`parent` pre-fill** — and it copies only the template's
frontmatter, never its body, so you would lose the relationship *and* still not get your
`## Subtasks` block. The two-step flow gives you both. `newItemFolder` is safe because it does not
touch that flag.

Two things to know about that second step:

- Inserting a template **merges** its frontmatter with what's already there, but it
  **overwrites** any key it also defines. That is why no ticket template declares `parent`,
  `project`, or `area` — if they did, inserting the template would wipe the links the New button
  just filled in. Set those three through the property editor (or let the view fill them).
- Don't create notes from *filtered viewing* views like **Board → Bugs** or **Backlog** unless
  you mean it: they'll pre-fill `type: bug` or `status: backlog`, and then the template will
  overwrite that with its own default. Create from the hierarchy blocks instead.

## The board

Bases has no board layout and no drag-and-drop, so:

- **Board** (cards, in `Board.base`) groups open tickets into collapsible lanes, ordered
  `1 · Backlog` → `5 · Review` by the `lane` formula. Frontmatter keeps clean values like
  `doing`; only the display label is numbered. Anything whose status isn't in the vocabulary
  lands in a visible **`8 · Unknown status`** lane rather than being quietly filed as cancelled
  — so a typo shows up on the board itself, not just in Triage.
- **Board (edit)** is the same grouping as a table. **This is how you move a ticket**: click its
  `status` cell, change the value, and the row jumps to the new lane. Cell multi-select,
  `Cmd+C` / `Cmd+V` and `Cmd+Z` all work, so bulk moves are one paste.
- The **`done` checkbox** is a shortcut, not a replacement. Clicking it in any table closes the
  ticket in one click and drops it into the Done lane. `status: done` does exactly the same
  thing — the `lane` and `open` formulas read `done || status == "done"`, so use whichever suits
  the moment. Set `closed` either way if you want the date in reports.

## Progress and rollups

Bases can't compute a child count on a parent's row. What it *can* do is summarise each group,
and that's where progress lives:

- **Portfolio → Progress by project** — tasks and subtasks grouped by project, with a `Sum` of
  closed items and a `Filled` count per group header.
- **Portfolio → Progress by parent** — same, grouped by the parent epic (or project, for tasks
  that hang directly off one). Needs no denormalised field at all.
- Each project note's **All work** block does this inline, grouped by parent, so subtasks nest
  under their task.

An epic's own `Tasks` block deliberately shows direct children only. Subtasks appear on their
parent task and in the project rollup.

## Two surfaces for two horizons

Recurring things come in two flavours, and forcing both through one mechanism is what makes a
system feel like a second job. So there are two, and you pick per item.

### Daily checks — the daily note

For trivia like *have lunch* or *move for 20 minutes*. These are plain markdown checkboxes in
today's daily note, created from `Templates/Daily.md`. No note per item, no frontmatter, no
fields — one click to tick, a fresh unchecked copy every morning, and yesterday's record stays in
yesterday's note.

The trade-off, stated plainly: checkbox state is invisible to Bases. You get no "missed three
days running" view and no streaks. For *have lunch*, that's the right trade.

### Pinned vs live sections

`today()` takes no arguments — it reads the system clock, so an embedded view filtered on it
renders the same rows in every note that embeds it. A journal note from three weeks ago would
show *today's* work.

So **Due this day** is not an embed. It is an inline block that derives the day from the note's
own filename:

```
formulas:
  day: date(this.file.basename)
filters:
  - due == formula.day
```

`this` inside an embedded base resolves to the embedding note, and `file.basename` is the
filename without its extension — so `Journal/2026-08-12.md` yields `2026-08-12` and the view
answers *what was due on the 12th*. It needs no frontmatter, so it works on journal notes that
already exist. `date()` returns empty on a name that isn't a date, and the `formula.day` guard
filter turns that into an empty table rather than an error — which is why this same block sits
harmlessly in `Templates/Daily.md` itself.

`==` is safe for dates here: Obsidian's equality operator uses `looseEquals`, which normalizes
both sides to date-only, so a stray time component can't cause a miss.

The block deliberately does **not** filter on `formula.open`. On a past day you want to see what
was due including what you finished; the `done` and `status` columns record how it turned out.

Every other section in the daily note is **live** and labelled as such — *Carried over*,
*Routines due*, *In progress*. They answer "right now", so they are only meaningful in today's
note.

The line this draws: anything stored as a date is reconstructible for any day. State is not.
`last_done` holds one value, not a history, so "was this routine due three Tuesdays ago" cannot
be answered and *Routines due* stays live. If you ever want that, the weekly review is the place
— it filters `closed >= today() - "7d"`, which is genuinely time-bounded.

### Routines — real notes, for cadence that matters

For anything where being late is information: `Pay bills` monthly, a weekly backup check. These
are `kind: routine` notes with `recur` and `last_done`. A routine is due when `last_done` plus its
cadence has passed, so **Today → Due today** can show you it's three weeks overdue — which a
checkbox can never do. Check one off by setting `last_done` to today in the cell.

`daily` and `weekdays` are still valid here — use a routine note over a checklist line whenever
you want the overdue detection.

**How `weekdays` works.** The `next_due` formula rolls forward over the weekend rather than
adding a flat day: done Friday → due Monday, done Saturday or Sunday → due Monday. Without that,
`last_done + "1d"` puts a Friday check-off due on Saturday, which then reads as *missed* the
moment Sunday arrives — the exact day you would sit down to do a weekly review. On top of that,
**Today → Due today** applies a `weekday_ok` guard so `weekdays` routines stay hidden on Saturday
and Sunday even when genuinely overdue; the weekend is not the time to be nagged.

The formula is duplicated in `Bases/Today.base`, `Templates/Area.md` and
`Templates/Weekly Review.md`. Bases has no shared-formula mechanism, so if you change the cadence
rules, change all three — a copy left behind produces a view that quietly disagrees with the
others.

## Closing work

Set `status: done`, or tick the `done` checkbox, and put the date in `closed`. Nothing moves to an
archive folder; views filter on status. **Triage → Done but no closed date** catches the ones you
forget, which matters because the weekly review's "closed this week" reads `closed` — the one
field neither the checkbox nor the status can infer for you.

## Property types

Types are what give you date pickers, numeric sorting on `priority`, and multi-link behaviour on
`blocked_by`. Set them in the **Properties** view in the sidebar, or in
`Settings → Files and links`, using this mapping:

- **Date** — `due` `scheduled` `closed` `last_done` `created` `date`
- **Number** — `priority`
- **Checkbox** — `done`
- **List** — `blocked_by` `attendees` `supersedes`
- **Text** — `kind` `status` `type` `recur` `parent` `project` `area` `week`

These are already written to `.obsidian/types.json`. The file is a flat map of property name to
widget under a single `types` key:

```json
{ "types": { "due": "date", "priority": "number", "blocked_by": "multitext" } }
```

Valid widgets are `text`, `multitext`, `number`, `checkbox`, `date`, `datetime`, `tags`,
`aliases`, `file`, `folder`. Two things to know if you edit it by hand:

- **A list property is `multitext`**, not `list`.
- Only *explicit* assignments are stored. Obsidian infers a type from your values, so a property
  can behave as a date without appearing in this file — which means an empty entry here is not
  the same as "no type".

## Icons (Iconize)

The one community plugin in play. Everything else still works with it disabled — icons are
cosmetic, and an `icon:` property is inert without the plugin.

Icons come from two independent places, because they solve different problems:

- **File explorer, tabs, note titles → Iconize.** Every note's icon comes from its `icon:`
  frontmatter property, which each template ships with, so a new task is automatically
  `LiSquareCheck`. `Settings → Iconize → Use icon in frontmatter` is on; the field name is `icon`.
  Folder icons live in the plugin's own `data.json` as top-level `"path": "IconName"` entries —
  folders can't have frontmatter, so that's the only place they can go. Files deliberately are
  *not* listed there, so frontmatter is the single source of truth per note.
- **Inside base views → the native `icon()` function.** Iconize doesn't reach into Bases tables,
  so the board gets its glyphs from Bases itself: `Board.base` has a `type_icon` formula (bug →
  `triangle-alert`, spike → `search-code`, research → `book-open`, chore → `circle-dot`) and a
  `flag` formula marking P1 and P2. Those are vanilla and would survive uninstalling the plugin.

### Colour by kind

Each note also carries `iconColor`, so the icon is colour-coded by what it is. Templates ship the
pair, so a new epic is teal and a new task is yellow without you doing anything.

| kind | colour | hex |
|---|---|---|
| `area` | violet | `#8B5CF6` |
| `project` | blue | `#3B82F6` |
| `epic` | **teal** | `#14B8A6` |
| `task` | **yellow-gold** | `#D9A21B` |
| `subtask` | muted gold — task's family, one step down | `#B4762A` |
| `routine` | green | `#10B981` |
| `doc` | slate — reference material recedes | `#64748B` |
| `decision` | pink | `#EC4899` |
| `meeting` | cyan | `#06B6D4` |
| `review` | indigo | `#6366F1` |

Folders are coloured to match what they hold, via `{"iconName": …, "iconColor": …}` objects in the
plugin's `data.json`.

**`data.json` is the store, not a cache — do not delete entries from it.** The plugin does read
`icon:`/`iconColor:` from frontmatter, but it writes an entry per file into `data.json` and *that*
is what the file explorer renders from. Repopulation from frontmatter is **lazy** — it happens for
one file when that file's metadata is reprocessed, not for the whole vault on startup. So removing
entries makes icons vanish until each note is individually touched.

To rebuild the whole vault from frontmatter in one go: **Settings → Iconize → Refresh icons from
frontmatter → Refresh**, then restart. Two warnings on that button, both real:

- It **removes** the icon of any note that has no `icon:` in frontmatter. Obsidian only recognises
  frontmatter at the very start of a file, which is why each template's Templater filing block sits
  *below* its frontmatter rather than above it — put it above and the whole file reads as having no
  frontmatter, so Refresh strips the icon. The `<%* … %>` block runs wherever it sits, so there is
  no cost to keeping it second.
- Folder icons live only in `data.json` (folders have no frontmatter), so if you edit that file
  while Obsidian is running the plugin can overwrite your folder colours from its in-memory copy.
  If they vanish, that is what happened: right-click the folder → **Change color**, or re-edit the
  file and reload immediately.

Three things behind those choices:

- **Hex, quoted.** A bare `iconColor: #14B8A6` is a *YAML comment* — the value silently becomes
  empty and you get an uncoloured icon with no error. Always quote it.
- **Hex rather than `var(--color-cyan)`.** Obsidian does define theme-aware colour variables
  (`--color-red/orange/yellow/green/cyan/blue/purple/pink` — note there is no teal, violet or
  indigo), and a variable would adapt to light/dark. But Iconize's `colorize()` writes the value
  into the SVG's `stroke` attribute, and CSS variables inside SVG presentation attributes are not
  something I could verify without running it. Hex is guaranteed in both places. If you want to
  experiment, `var(--color-cyan)` on one note is a safe test.
- **Mid-tone hues.** Picked to stay legible against both light and dark backgrounds. True yellow
  (`#EAB308`) is what you'd reach for, but it nearly vanishes on a white background, hence the
  slightly deeper gold.

Icon names differ between the two mechanisms, which is the thing that will trip you up:

| Where | Format | Example |
|---|---|---|
| `icon:` frontmatter, plugin `data.json` | `Li` + CapitalisedSegments | `LiFolderKanban` |
| `icon()` in a base formula | raw Lucide id | `icon("folder-kanban")` |

The `Li` prefix is the native Lucide pack; the name is the Lucide id with each `-` segment
capitalised and the hyphens removed, so `layers-2` becomes `LiLayers2`.

**Not every Lucide name exists in this build.** Obsidian ships a curated subset of 1408 ids, and
some obvious ones are absent — `compass`, `gavel`, `sun`, `zap`, `flag`, `bug`, `users`, `home`
and `wrench` are all missing, while `users-2`, `triangle-alert` and `repeat-1` are present. A name
that doesn't exist renders as nothing at all, silently. Check before using one: the icon picker in
the Iconize settings only lists real ones.

## Configuration ownership

**`.obsidian/` belongs to the application, not to you.** Your data is the markdown and the `.base`
files; everything under `.obsidian/` is runtime state that a process owns and rewrites on its own
schedule. Change it through the UI, then let git record the result. Editing it by hand while
Obsidian is running loses — silently, because nothing errors.

The line is whether the owner watches the file for external changes:

| File | Owner | Hand-editable? |
|---|---|---|
| `plugins/obsidian-icon-folder/data.json` | Iconize | **No.** `loadData()` once at startup, `saveData()` on every change, no file watcher. Your edit is invisible and gets overwritten. |
| `plugins/templater-obsidian/data.json` | Templater | **No**, same pattern. Set it in Settings. |
| `types.json` | Obsidian | Tolerated — it registers `onRaw` on this exact path and reloads when it changes on disk. Still prefer the Properties UI. |
| `workspace.json` | Obsidian | No, and it is gitignored: pure machine-local churn. |
| `app.json`, `core-plugins.json`, `community-plugins.json` | Obsidian | Tracked as a snapshot; change via Settings. |

Practical consequences:

- **Icons live in frontmatter, which is yours.** `data.json` is downstream of it, and
  **Settings → Iconize → Refresh icons from frontmatter** regenerates it. That is the repair path
  for anything icon-related — never a text editor.
- **Folder icons are the exception**: folders have no frontmatter, so they exist *only* in
  `data.json` — which is **git-ignored**, because Iconize rewrites it on every launch and a
  tracked copy makes the tree dirty just from opening the vault. A fresh clone therefore starts
  with plain folders, and rebuilding them from this table is a one-time setup step, not just a
  repair path (right-click folder → **Change icon** / **Change color**):

  | Folder | Icon | Colour |
  |---|---|---|
  | `Items` | `LiListChecks` | `#D9A21B` |
  | `Docs` | `LiBookOpen` | `#64748B` |
  | `Meetings` | `LiUsers2` | `#06B6D4` |
  | `Reviews` | `LiCalendarCheck` | `#6366F1` |
  | `Bases` | `LiLayoutGrid` | `#3B82F6` |
  | `Templates` | `LiLayoutTemplate` | `#94A3B8` |
  | `Journal` | `LiNotebookPen` | `#F97316` |

## Naming

`Items/` is deliberately flat: re-parenting is a property edit, never a file move. The cost is
that **note titles must be unique across the vault** — Obsidian links by name. When two things
would collide, disambiguate in the title (`Website — write tests`), not with folders.

There are no auto-generated keys like `ORD-14`. Vanilla can't increment a counter; the title is
the identifier.

## The demo dataset

The repo ships **empty** — no notes, just the system. An empty view and a broken view look
identical, so before trusting any of this, fill it:

```sh
python3 demo/demo.py load     # ~25 throwaway notes
python3 demo/demo.py clear    # delete exactly those again
```

**Reload the vault (`Cmd+R`) after either command.** Both write files while Obsidian is running,
and Iconize decorates a note in the file explorer only when that row renders — so new notes show
up with no icon until you reload. The entries are already in its store; they simply have not been
painted. This is the same mechanism described under *Configuration ownership*: the plugin has no
watcher for changes made outside the app.

It writes a `Studio` and a `Household` area, two projects, two epics, ten tickets, three
routines, two docs, a decision, a meeting and a weekly review — covering all seven statuses,
all five issue types, priorities 1–4, a `blocked_by` link, a cancelled ticket and a closed
subtask, so every view in the vault has something in it.

Dates are generated relative to the day you run it, so the board is always live: one task due
today, one overdue, one routine overdue by a week, one subtask closed three days ago. `clear`
removes exactly the files it created and leaves a clean tree.

**Triage should be empty**, and on a fresh clone it is. Every one of its views is a "something
is wrong" query, so an empty Triage means nothing is wrong — not that it is broken. To prove it
fires, open any item and set `priority: 9`, or misspell its `status`; it appears in **Invalid
values** at once, and reverting clears it. Worth doing once, because a misspelled status is the
one failure mode that loses work *silently*: Bases has no enum type, so the ticket does not
error, it just stops showing up where you expect.

## If something looks wrong

- **Lanes in alphabetical order instead of workflow order** — `groupBy` isn't accepting
  `formula.lane`. Fall back to numeric-prefixed status values (`2-todo`) grouped on
  `note.status` directly.
- **A ticket vanished from the board** — almost always a status typo. Look for an
  `8 · Unknown status` lane, then check **Triage → Invalid values**.
- **New didn't pre-fill `parent`** — the view still filters correctly; set it with the property
  editor's autocomplete, or paste it across cells in **Board (edit)**.
- **A base shows an error banner** — the message names the property or function. Filters are
  quoted strings; `!=` and `!` need the quotes to survive YAML.
- **A column shows a raw property name instead of its label** — in the top-level `properties:`
  block, note properties must be keyed **bare** (`status:`, not `note.status:`). Those keys are
  looked up verbatim, unlike `order`, `sort`, `groupBy` and `summaries`, which normalise the
  `note.` prefix away. Keep `file.*` and `formula.*` prefixed everywhere.
- **`list()` takes exactly one argument.** `list("a","b")` raises "too many arguments" and breaks
  the whole filter. For set membership write `kind == "a" || kind == "b"`. (`file.hasTag()` *is*
  variadic — that one takes many.)
