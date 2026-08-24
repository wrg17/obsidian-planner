---
kind: task
icon: LiSquareCheck
iconColor: "#D9A21B"
status: todo
done: false
type: feature
priority: 3
due: 
scheduled: 
closed: 
blocked_by: []
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* if (tp.file.folder(true) !== "Items") { await tp.file.move("Items/" + tp.file.title) } -%>

# <% tp.file.title %>

## Context

Why this exists. Link the doc or decision it came from.

## Acceptance

- 

## Steps

Optional scratch checkboxes for the obvious steps, when a step isn't worth a note of its own.
Anything that needs its own due date, priority, or place on the board should be a real subtask.

- [ ] 

## Subtasks

```base
newItemFolder: Items
formulas:
  done_num: 'if(done || status == "done", 1, 0)'
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
      - note.type
      - note.priority
      - note.due
      - formula.done_num
    sort:
      - property: note.priority
        direction: ASC
    summaries:
      formula.done_num: Sum
      note.status: Filled
```

## Work log

