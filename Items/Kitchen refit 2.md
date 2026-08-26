---
kind: project
icon: LiFolderKanban
iconColor: "#3B82F6"
status: active
area: "[[Household]]"
priority: 1
due: 2026-09-16
created: 2026-07-27
demo: true
---

# Kitchen refit

## Goal

Worktop replaced and the alcove shelved out.

## Epics

```base
newItemFolder: Items
views:
  - type: table
    name: Epics
    filters:
      and:
        - 'kind == "epic"'
        - 'parent == this'
    order:
      - file.name
      - done
      - note.status
      - note.priority
      - note.due
```

## All work

```base
newItemFolder: Items
formulas:
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: All work
    filters:
      and:
        - 'project == this'
        - 'kind == "epic" || kind == "task" || kind == "subtask"'
    groupBy:
      property: note.parent
      direction: ASC
    order:
      - file.name
      - note.kind
      - done
      - note.status
      - note.priority
      - note.due
      - formula.done_num
    summaries:
      formula.done_num: Sum
      note.status: Filled
```
