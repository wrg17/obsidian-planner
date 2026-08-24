---
kind: area
icon: LiLandPlot
iconColor: "#8B5CF6"
status: active
created: 2026-07-25
---

# Studio

Creative and client work. Areas never finish; projects inside them do.

## Projects and routines

```base
newItemFolder: Items
views:
  - type: table
    name: Projects
    filters:
      and:
        - 'kind == "project"'
        - 'area == this'
    order:
      - file.name
      - note.status
      - note.priority
      - note.due
  - type: table
    name: Routines
    filters:
      and:
        - 'kind == "routine"'
        - 'area == this'
    order:
      - file.name
      - note.recur
      - note.last_done
```
