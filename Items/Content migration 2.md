---
kind: epic
icon: LiLayers2
iconColor: "#14B8A6"
status: backlog
done: false
type: chore
parent: "[[Website relaunch]]"
project: "[[Website relaunch]]"
priority: 3
created: 2026-07-27
demo: true
---

# Content migration

## Scope

Moving old posts across with redirects intact.

## Tasks

```base
newItemFolder: Items
formulas:
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: Tasks
    filters:
      and:
        - 'kind == "task"'
        - 'parent == this'
    order:
      - file.name
      - done
      - note.status
      - note.type
      - note.priority
      - note.due
      - formula.done_num
    sort:
      - property: note.priority
        direction: ASC
    summaries:
      formula.done_num: Sum
      note.status: Filled
```
