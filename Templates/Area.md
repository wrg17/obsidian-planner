---
kind: area
icon: LiLandPlot
iconColor: "#8B5CF6"
status: active
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* if (tp.file.folder(true) !== "Items") { await tp.file.move("Items/" + tp.file.title) } -%>

# <% tp.file.title %>

## Purpose

What this area is for, and what "good" looks like. Areas are ongoing — they are never "done",
they are only active or paused.

## Standards

- 

## Projects

```base
newItemFolder: Items
formulas:
  touched: 'file.mtime.relative()'
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
      - formula.touched
    sort:
      - property: note.priority
        direction: ASC
```

## Routines

```base
newItemFolder: Items
formulas:
  next_due: 'if(last_done, if(recur == "weekly", last_done + "1w", if(recur == "monthly", last_done + "1M", if(recur == "weekdays", if(last_done.format("d") == "5", last_done + "3d", if(last_done.format("d") == "6", last_done + "2d", last_done + "1d")), last_done + "1d"))), today())'
views:
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
      - formula.next_due
    sort:
      - property: formula.next_due
        direction: ASC
```

## Notes

