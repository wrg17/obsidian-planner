---
kind: decision
icon: LiGitBranch
iconColor: "#EC4899"
status: accepted
date: 2026-08-19
project: "[[Website relaunch]]"
supersedes: []
created: 2026-07-27
demo: true
---

# Use system fonts

## Context

Webfonts were costing about 400ms on first paint.

## Options

1. Keep the webfont
2. System font stack
3. Subset the webfont

## Decision

System font stack.

## Consequences

Faster, slightly less distinctive. Revisit if branding objects.

