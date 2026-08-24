---
kind: task
icon: LiSquareCheck
iconColor: "#D9A21B"
status: backlog
done: false
type: research
parent: "[[Kitchen refit]]"
project: "[[Kitchen refit]]"
priority: 3
created: 2026-07-25
---

# Compare worktop quotes

No date and no priority pressure -- sits in Backlog until it earns one.

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
