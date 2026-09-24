# Issue Tracker

This project uses **GitHub Issues** for tracking work.

## Where issues live

Issues are stored in the GitHub repository. Skills like `to-tickets`, `triage`, and `to-spec` create and read issues via the GitHub CLI (`gh`).

## How skills interact with it

- **`to-spec`**: creates an issue with the full specification and tags it `ready-for-agent`
- **`to-tickets`**: splits the spec into tracer-bullet tickets, each tagged `ready-for-agent` and linked with blocking edges
- **`triage`**: moves incoming issues through triage roles using labels
- **`implement`**: reads a ticket and opens a branch to work it

## GitHub URL

Set your repository URL when you create the repo on GitHub:

```
git remote add origin https://github.com/YOUR_USERNAME/poker-platform.git
```

Then push:

```
git branch -M main
git push -u origin main
```

## Workflow

1. Create an issue on GitHub or via `gh issue create`
2. Triage it (or `triage` skill will do it)
3. Once triaged to `ready-for-agent`, pick it up with `implement`
4. When done, link the PR to the issue (GitHub does this automatically with `Closes #123` in PR body)

## PRs as a request surface

This setting is **OFF** by default. If you want external PRs to be automatically triaged into the queue, set `pr_surface: true` in this file.
