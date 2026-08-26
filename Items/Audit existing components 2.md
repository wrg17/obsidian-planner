---
kind: task
icon: LiSquareCheck
iconColor: "#D9A21B"
status: todo
done: false
type: spike
parent: "[[Design system]]"
project: "[[Website relaunch]]"
priority: 2
due: 2026-08-31
created: 2026-07-27
demo: true
---

# Audit existing components

Timeboxed look at what already exists before deciding what to keep.

## Subtasks

```base
newItemFolder: Items
views:
  - type: table
    name: Subtasks
    filters:
      and:
        - 'kind == "subtask"'
        - 'parent == this'
    order:
      - file.name
      - done
      - note.status
      - note.priority
      - note.due
    sort:
      - property: note.priority
        direction: ASC
```
