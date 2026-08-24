---
kind: decision
icon: LiGitBranch
iconColor: "#EC4899"
status: proposed
date: "<% tp.date.now('YYYY-MM-DD') %>"
supersedes: []
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* if (tp.file.folder(true) !== "Docs") { await tp.file.move("Docs/" + tp.file.title) } -%>

# <% tp.file.title %>

> Status: `proposed` → `accepted` | `rejected`, and later `superseded`. When superseding an old
> decision, add it to `supersedes` on the new note and set the old one to `superseded`.

## Context

The forces at play. What made a decision necessary.

## Options considered

1. **Option A** — 
2. **Option B** — 

## Decision

What was chosen, and the deciding reason.

## Consequences

What this makes easy, and what it makes harder or expensive to change later.
