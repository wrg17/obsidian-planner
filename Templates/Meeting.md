---
kind: meeting
icon: LiUsers2
iconColor: "#06B6D4"
date: "<% tp.date.now('YYYY-MM-DD') %>"
attendees: []
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%*
const topic = await tp.system.prompt("Meeting topic");
if (topic) { await tp.file.move("Meetings/" + tp.date.now('YYYY-MM-DD') + " " + topic); }
-%>

# <% tp.file.title %>

## Agenda

- 

## Notes

## Actions

Click **New** in the view below to turn a discussion point into a real ticket — `kind` and
`parent` are filled in for you, so the action item stays linked to this meeting. Set its
`project` afterwards, or it will show up in **Triage → Missing project**.

```base
newItemFolder: Items
views:
  - type: table
    name: Action items
    filters:
      and:
        - 'kind == "task"'
        - 'parent == this'
    order:
      - file.name
      - note.status
      - note.priority
      - note.due
      - note.project
    sort:
      - property: note.priority
        direction: ASC
```
