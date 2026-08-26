---
kind: task
icon: LiSquareCheck
iconColor: "#D9A21B"
status: blocked
done: false
type: chore
parent: "[[Content migration]]"
project: "[[Website relaunch]]"
priority: 3
due: 2026-09-05
blocked_by:
  - "[[Pick a type scale]]"
created: 2026-07-27
demo: true
---

# Export old posts

Blocked, with `blocked_by` pointing at the thing in the way.

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
