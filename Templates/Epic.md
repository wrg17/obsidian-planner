---
kind: epic
icon: LiLayers2
iconColor: "#14B8A6"
status: backlog
done: false
type: feature
priority: 3
due: 
closed: 
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* if (tp.file.folder(true) !== "Items") { await tp.file.move("Items/" + tp.file.title) } -%>

# <% tp.file.title %>

## Scope

What this epic covers, and what it explicitly does not.

## Done when

- 

## Tasks

Direct children only. Subtasks live on their parent task note, and the whole tree is visible
on the project note's **All work** view.

```base
newItemFolder: Items
formulas:
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: Tasks
    filters:
      and:
        - 'kind == "task"'
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

## Notes

