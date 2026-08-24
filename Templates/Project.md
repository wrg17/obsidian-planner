---
kind: project
icon: LiFolderKanban
iconColor: "#3B82F6"
status: active
priority: 3
due: 
closed: 
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* if (tp.file.folder(true) !== "Items") { await tp.file.move("Items/" + tp.file.title) } -%>

# <% tp.file.title %>

## Goal

The outcome that means this project is finished. Projects end; areas don't.

## Epics

```base
newItemFolder: Items
views:
  - type: table
    name: Epics
    filters:
      and:
        - 'kind == "epic"'
        - 'parent == this'
    order:
      - file.name
      - done
      - note.status
      - note.type
      - note.priority
      - note.due
    sort:
      - property: note.priority
        direction: ASC
```

## All work

Grouped by parent, so subtasks appear nested under their task. The `Sum` at the top of each
group is the count of closed items in that group.

```base
newItemFolder: Items
formulas:
  open: '!done && status != "done" && status != "cancelled"'
  done_num: 'if(done || status == "done", 1, 0)'
  lane: 'if(done || status == "done", "6 · Done", if(status == "cancelled", "7 · Cancelled", if(status == "backlog", "1 · Backlog", if(status == "todo", "2 · Todo", if(status == "doing", "3 · Doing", if(status == "blocked", "4 · Blocked", if(status == "review", "5 · Review", "8 · Unknown status")))))))'
views:
  - type: table
    name: All work
    filters:
      and:
        - 'project == this'
        - 'kind == "epic" || kind == "task" || kind == "subtask"'
    groupBy:
      property: note.parent
      direction: ASC
    order:
      - file.name
      - note.kind
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
  - type: table
    name: Open by lane
    filters:
      and:
        - 'project == this'
        - 'kind == "epic" || kind == "task" || kind == "subtask"'
        - 'formula.open'
    groupBy:
      property: formula.lane
      direction: ASC
    order:
      - file.name
      - note.kind
      - note.type
      - note.priority
      - note.due
    sort:
      - property: note.priority
        direction: ASC
```

## Docs

```base
newItemFolder: Items
views:
  - type: table
    name: Docs
    filters:
      and:
        - 'kind == "doc"'
        - 'project == this'
    order:
      - file.name
      - done
      - note.status
    sort:
      - property: file.mtime
        direction: DESC
  - type: table
    name: Decisions
    filters:
      and:
        - 'kind == "decision"'
        - 'project == this'
    order:
      - file.name
      - done
      - note.status
      - note.date
    sort:
      - property: note.date
        direction: DESC
```

## Notes

