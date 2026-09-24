# Domain Documentation

This project uses a **single-context** layout: one `CONTEXT.md` at the repo root, plus Architecture Decision Records (ADRs) in `docs/adr/`.

## What goes where

### `CONTEXT.md`

A glossary of terms, domain concepts, and the current state of the project. Read it first when joining the project.

**Contents:**
- **Project overview**: what this project does and why
- **Domain glossary**: all terms the team uses (e.g., "Tournament", "Blind Level", "Rating", "Club")
- **Architecture overview**: the high-level design (which services, layers, integrations)
- **Known constraints**: what we can't change easily (e.g., "iiko integration is read-only for now")
- **Running the project**: how to start the dev environment

**Update it when:**
- You define or refine a term
- You learn a new constraint
- You change a major architectural decision

### `docs/adr/`

One ADR (Architecture Decision Record) per significant technical decision. Format: `ADR-NNNN-decision-name.md`.

**ADR template:**
```
# ADR-0001: Why we chose FastAPI over Django

## Status
Accepted

## Context
We needed a Python API framework that supports WebSockets for realtime tournament updates, async handlers for Telegram bot, and easy testing.

## Decision
We chose FastAPI because [reasons].

## Consequences
- Pro: fast, async-first, automatic OpenAPI docs
- Con: smaller ecosystem than Django, requires Python 3.7+
```

**When to write an ADR:**
- Choosing a framework or library
- Deciding on database schema (especially for multi-tenant design)
- Choosing between two architectural approaches (monolith vs microservices, etc.)
- Integrating with external systems (iiko, Telegram, VK ID)

**When NOT to write:**
- Bug fixes
- Routine feature development (if architecture is already decided)
- Tiny local refactors

## Consumer rules

**For agents (skills):**
- Before writing code, read `CONTEXT.md` to understand domain terms and constraints
- Before proposing architecture, check `docs/adr/` for prior decisions
- When you need to make a domain decision, propose an ADR and ask the human

**For humans (you):**
- Keep `CONTEXT.md` up to date as the project evolves
- Write ADRs when the decision is hard or might be reversed later
- Link ADRs from code comments when code depends on the decision

## Monorepo note

This is **not** a monorepo. If it becomes one (multiple packages, separate `CONTEXT.md` per package), switch to **multi-context** layout: root `CONTEXT-MAP.md` pointing to per-package `CONTEXT.md` files.
