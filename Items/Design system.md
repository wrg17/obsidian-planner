---
kind: epic
icon: LiLayers2
iconColor: "#14B8A6"
status: doing
done: false
type: feature
parent: "[[Website relaunch]]"
project: "[[Website relaunch]]"
priority: 2
due: 2026-09-23
created: 2026-07-25
---

# Design system

## Scope

Type, colour and the component set. Not page layouts.

## Done when

- Every component has one documented state

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
