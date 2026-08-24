---
kind: doc
icon: LiFileText
iconColor: "#64748B"
status: draft
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* if (tp.file.folder(true) !== "Docs") { await tp.file.move("Docs/" + tp.file.title) } -%>

# <% tp.file.title %>

> Status: `draft` → `current` → `stale`. Anything left in `draft`, or untouched for 180 days,
> shows up in **Docs → Needs review**.

## Summary

One paragraph. If someone reads only this, what must they know?

## Detail

## Open questions

- 

## Related work

```base
newItemFolder: Items
views:
  - type: table
    name: Mentioned by
    filters: 'file.hasLink(this.file)'
    order:
      - file.name
      - note.kind
      - note.status
      - note.project
    sort:
      - property: file.mtime
        direction: DESC
```
