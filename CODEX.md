# CODEX.md

## Project context

This repository contains a Python script that exports SEO data from a remote WordPress + WooCommerce database over SSH into CSV.

Target context:
- WordPress
- WooCommerce
- Bono theme
- Remote hosting with SSH access
- MySQL database
- CSV export for products and categories

The existing implementation is the baseline and must be treated as working unless proven otherwise.

## Primary rule

Do not break existing working behavior just to improve architecture.

Use milestone-based evolution.

If a change can be postponed to a later milestone, postpone it.

## Change policy

Allowed:
- add tests
- add docs
- add diagnostics
- add optional presets
- fix real bugs
- perform minimal refactors required by the current milestone

Not allowed:
- broad rewrites without milestone approval
- changing CLI behavior unnecessarily
- deleting working logic for aesthetics
- changing CSV schema without an explicit milestone

## Milestone workflow

For every task:
1. Read `docs/production-milestones.md`
2. Identify the current milestone
3. State goal and constraints
4. Change only the files required for that milestone
5. Add or update tests
6. Summarize what changed
7. Stop

## Protected baseline

The current manually created code is a protected baseline.

You may modify it only when:
- there is a real bug,
- or the current milestone cannot be completed otherwise,
- and the change is minimal,
- and backward compatibility is preserved.

## Development style

- Keep code in English
- Keep docs for end users in Russian
- Keep commits in English using Conventional Commits
- Prefer small changes
- Prefer explicit behavior
- Prefer preserving current CLI contracts

## Commit examples

- `feat(export): add wp preset queries`
- `fix(cli): handle empty query selection`
- `test(csv): cover output writer`
- `docs(roadmap): refine milestones`

## Test-first priority

Before moving to the next milestone, ensure:
- tests pass
- CLI behavior is still valid
- CSV columns are unchanged unless milestone says otherwise
- config flow still works

## Repository files to respect

- `README.md`
- `docs/github-repo-plan.md`
- `docs/production-milestones.md`
- `config.example.json`
- `Makefile`

If there is any tension between refactoring and shipping the current milestone, prefer shipping the milestone with minimal disruption.
