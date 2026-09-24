# claude.md

Instructions for working with this project and deploying AI-assisted changes.

## Agent skills

Engineering workflows for this project are built on Matt Pocock's agent skills. See `docs/agents/` for configuration.

### Issue tracker

Work is tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Five-role triage vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` + `docs/adr/` for decisions. See `docs/agents/domain.md`.

## Workflow

1. **Sharpen the idea**: `/grill-with-docs` (interview to sharpen thinking and fill `CONTEXT.md`)
2. **Write the spec**: `/to-spec` (turn the grilling into a GitHub issue with full spec, tagged `ready-for-agent`)
3. **Split into tickets**: `/to-tickets` (spec becomes multiple tracer-bullet tickets, each `ready-for-agent`)
4. **Implement each**: `/implement` for each ticket (uses `/tdd` red-green, then `/code-review`)
5. **Deploy**: Push to main (GitHub Actions CI/CD runs tests and deploys to staging/prod)

## Domain glossary

See `CONTEXT.md` for the living glossary of terms used in this project.

## Decisions

See `docs/adr/` for Architecture Decision Records on why we chose this tech stack, architecture, integrations.

## Deployment

(To be filled in once CI/CD is set up)

- Staging: auto-deploy on push to `main`
- Production: manual approval needed or automatic after tests pass
- Rollback: `git revert` and push, then re-run deploy

## Contact

**Owner**: Matt Getsov (mattgets1@gmail.com)

---

This file is meant to be edited as the project evolves. Keep it a living document.
