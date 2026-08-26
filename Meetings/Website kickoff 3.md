---
kind: meeting
icon: LiUsers2
iconColor: "#06B6D4"
date: 2026-08-21
project: "[[Website relaunch]]"
attendees: []
created: 2026-07-27
demo: true
---

# Website kickoff

## Agenda

- Scope
- Timeline

## Notes

Agreed to cut the blog redesign from phase one.

## Actions

Action items become real tickets here:

```base
newItemFolder: Items
views:
  - type: table
    name: Actions
    filters:
      and:
        - 'kind == "task"'
        - 'parent == this'
    order:
      - file.name
      - done
      - note.status
      - note.due
```

