---
kind: task
icon: LiSquareCheck
iconColor: "#D9A21B"
status: backlog
done: false
type: bug
parent: "[[Design system]]"
project: "[[Website relaunch]]"
priority: 2
created: 2026-07-27
demo: true
---

# Fix button contrast

Fails contrast against the accent background. The only `bug` in the demo, so **Board -> Bugs** shows exactly this.

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
