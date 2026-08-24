---
kind: task
icon: LiSquareCheck
iconColor: "#D9A21B"
status: todo
done: false
type: chore
parent: "[[Kitchen refit]]"
project: "[[Kitchen refit]]"
priority: 1
due: 2026-08-26
scheduled: 2026-08-26
created: 2026-08-24
---

# Measure the alcove

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
