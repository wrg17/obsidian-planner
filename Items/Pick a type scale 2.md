---
kind: task
icon: LiSquareCheck
iconColor: "#D9A21B"
status: doing
done: false
type: feature
parent: "[[Design system]]"
project: "[[Website relaunch]]"
priority: 1
due: 2026-08-26
scheduled: 2026-08-26
created: 2026-07-27
demo: true
---

# Pick a type scale

Due **today**, so it shows up in Today and in today's daily note.

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
