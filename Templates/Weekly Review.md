---
kind: review
icon: LiCalendarCheck
iconColor: "#6366F1"
week: "<% tp.date.now('GGGG-[W]WW') %>"
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* await tp.file.move("Reviews/" + tp.date.now('GGGG-[W]WW')) -%>

# Week <% tp.date.now('GGGG-[W]WW') %>

The three sections below are **pinned to this note's week**, taken from its own `week` property
(falling back to its filename). Open last month's review and you get that week's numbers, not a
rolling window ending today.

## Closed this week

```base
newItemFolder: Items
formulas:
  wk: 'if(this.week, this.week, this.file.basename)'
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: Closed
    filters:
      and:
        - 'closed'
        - 'closed.format("GGGG-[W]WW") == formula.wk'
    order:
      - file.name
      - note.kind
      - note.type
      - note.closed
      - note.project
    sort:
      - property: note.closed
        direction: DESC
    summaries:
      formula.done_num: Sum
```

## Due this week

Everything dated into this week, with `status` showing how it turned out. Anything still open
here is what slipped — do it, re-date it, or drop it.

```base
newItemFolder: Items
formulas:
  wk: 'if(this.week, this.week, this.file.basename)'
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: Due this week
    filters:
      and:
        - 'due'
        - 'due.format("GGGG-[W]WW") == formula.wk'
    order:
      - file.name
      - done
      - note.status
      - note.due
      - note.priority
      - note.project
    sort:
      - property: note.due
        direction: ASC
    summaries:
      formula.done_num: Sum
      note.status: Filled
```

## Opened this week

```base
newItemFolder: Items
formulas:
  wk: 'if(this.week, this.week, this.file.basename)'
views:
  - type: table
    name: Opened
    filters:
      and:
        - 'created'
        - 'created.format("GGGG-[W]WW") == formula.wk'
        - 'kind == "epic" || kind == "task" || kind == "subtask"'
    order:
      - file.name
      - note.kind
      - note.status
      - note.priority
      - note.project
    sort:
      - property: note.created
        direction: ASC
```

## Routines missed

Live, not pinned — `last_done` stores one value, not a history, so a routine's state three weeks
ago cannot be reconstructed. Only meaningful in the current week's review.

```base
newItemFolder: Items
formulas:
  next_due: 'if(last_done, if(recur == "weekly", last_done + "1w", if(recur == "monthly", last_done + "1M", if(recur == "weekdays", if(last_done.format("d") == "5", last_done + "3d", if(last_done.format("d") == "6", last_done + "2d", last_done + "1d")), last_done + "1d"))), today())'
  when: 'if(formula.next_due, formula.next_due.relative(), "")'
views:
  - type: table
    name: Behind
    filters:
      and:
        - 'kind == "routine"'
        - 'status == "active"'
        - 'formula.next_due < today()'
    order:
      - file.name
      - note.recur
      - note.last_done
      - formula.when
    sort:
      - property: formula.next_due
        direction: ASC
```

## Stale

Live as well — `file.mtime` is the current modification time, so this always means "untouched for
30 days as of right now".

```base
newItemFolder: Items
formulas:
  open: '!done && status != "done" && status != "cancelled"'
  touched: 'file.mtime.relative()'
views:
  - type: table
    name: Stale
    filters:
      and:
        - 'formula.open'
        - 'kind == "epic" || kind == "task" || kind == "subtask"'
        - 'file.mtime < now() - "30d"'
    order:
      - file.name
      - done
      - note.status
      - note.project
      - formula.touched
    sort:
      - property: file.mtime
        direction: ASC
```

## Reflection

What went well:

What to change next week:
