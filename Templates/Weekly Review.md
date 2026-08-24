---
kind: review
icon: LiCalendarCheck
iconColor: "#6366F1"
week: "<% tp.date.now('GGGG-[W]WW') %>"
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* await tp.file.move("Reviews/" + tp.date.now('GGGG-[W]WW')) -%>

# Week <% tp.date.now('GGGG-[W]WW') %>

## Closed this week

```base
newItemFolder: Items
formulas:
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: Closed
    filters:
      and:
        - 'closed'
        - 'closed >= today() - "7d"'
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

## Slipped

Open work whose due date has passed. Either do it, re-date it, or drop it — don't let it rot.

```base
newItemFolder: Items
formulas:
  open: '!done && status != "done" && status != "cancelled"'
views:
  - type: table
    name: Slipped
    filters:
      and:
        - 'formula.open'
        - 'due'
        - 'due < today()'
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
```

## Routines missed

```base
newItemFolder: Items
formulas:
  next_due: 'if(last_done, if(recur == "weekly", last_done + "1w", if(recur == "monthly", last_done + "1M", last_done + "1d")), today())'
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
