---
kind: task
icon: LiSquareCheck
iconColor: "#D9A21B"
status: review
done: false
type: chore
parent: "[[Content migration]]"
project: "[[Website relaunch]]"
priority: 2
due: 2026-08-29
created: 2026-08-24
demo: true
---

# Proofread the about page

In review -- written, not yet signed off.

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
