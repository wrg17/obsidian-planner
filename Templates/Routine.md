---
kind: routine
icon: LiRepeat1
iconColor: "#10B981"
status: active
recur: daily
last_done: 
created: "<% tp.date.now('YYYY-MM-DD') %>"
---
<%* if (tp.file.folder(true) !== "Items") { await tp.file.move("Items/" + tp.file.title) } -%>

# <% tp.file.title %>

## Done means

The smallest thing that honestly counts as done. Keep it small enough that you never skip it.

## How to check off

Set `last_done` to today — in **Today → Due today**, click the `last_done` cell and pick
today's date. The routine leaves the view immediately and returns on its next cadence
(`recur`: `daily`, `weekdays`, `weekly`, `monthly`).

Set `status: paused` to retire it without deleting the history.

## Notes

