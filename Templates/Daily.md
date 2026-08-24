---
icon: LiCalendarDays
iconColor: "#F97316"
---

# {{date:dddd D MMMM YYYY}}

## Checks

Trivial daily things. These are plain checkboxes — no notes, no fields, no metadata. A fresh
unchecked copy appears automatically every morning, and yesterday's stays in yesterday's note.

- [ ] have lunch
- [ ] move for 20 minutes
- [ ] morning review — open Today, pick the one thing that matters
- [ ] inbox to zero

## Due this day

Pinned to **this note's date**, taken from its filename — not to the current date. Open a
journal note from three weeks ago and this shows what was due that day, with `status` and
`done` recording how it turned out.

```base
filters:
  and:
    - kind == "task" || kind == "subtask" || kind == "epic"
formulas:
  day: date(this.file.basename)
views:
  - type: table
    name: Due this day
    filters:
      and:
        - formula.day
        - due == formula.day
    order:
      - file.name
      - kind
      - done
      - status
      - priority
      - project
    sort:
      - property: priority
        direction: ASC
```

## Carried over

Live, not pinned — anything still open and past its date **as of right now**. Only meaningful
in today's note; on an old one it shows today's backlog, not that day's.

![[Today.base#Overdue]]

## Routines due

Live. The sparse ones (weekly, monthly); the daily habits are the checkboxes above.

![[Today.base#Routines due]]

## In progress

Live.

![[Board.base#Doing now]]

## Capture

Anything that occurs to you. Most of it will not survive the week, and that is the point —
promote only what does into a real task at the weekly review.

- 
