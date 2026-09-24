# Triage Labels

This project uses the standard five-role triage label vocabulary.

## Labels

| Label | Meaning | Who uses it |
|-------|---------|------------|
| `needs-triage` | New issue, not yet reviewed | Incoming issues (bugs, features, questions) |
| `needs-info` | Issue is waiting for clarification from the reporter | `triage` skill when info is missing |
| `ready-for-agent` | Issue is fully specified and ready to be picked up by `implement` | `to-tickets` or `triage` when done |
| `ready-for-human` | Issue needs human decision or approval | `triage` when escalating to a human |
| `wontfix` | Issue is rejected or intentionally closed | `triage` or manually |

## How `triage` uses them

The `triage` skill reads incoming issues (those without a triage label) and applies one of the five labels based on:

1. **`needs-info`**: if the issue is missing required context (unclear reproduction, missing API response, etc.)
2. **`ready-for-agent`**: if the issue is well-formed, actionable, and ready for an agent to implement
3. **`ready-for-human`**: if the issue requires human judgment (architecture decision, third-party integration question, etc.)
4. **`wontfix`**: if the issue is intentionally out of scope, a duplicate, or a non-issue
5. **`needs-triage`** is left as-is if the skill is unsure and needs human review

## No custom labels yet

These are the standard labels. If your workflow needs custom labels (e.g., `priority:high`, `area:backend`), add them here and update the `triage` configuration separately.
