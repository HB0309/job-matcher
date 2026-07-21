# Git Workflow

## Branching

- Never work on `main` for non-trivial changes.
- One branch per feature/fix: `feat/`, `fix/`, `docs/`, `chore/`.

## Commits

- Small, logical commits. Docs + code in the same commit when they form one unit.
- Update `docs/TODO.md` whenever progress changes.
- Conventional messages: `feat: add lever connector`, `fix: dedupe key`, `chore: seed targets`.

## Pull requests

- One feature per branch. Include docs updates.
- Summarize: what changed, why, any schema/API impact, follow-up tasks.

## Safety

- Never delete large code/doc sections without an intentional replacement.
- Never overwrite user work blindly.
- Inspect unexpected working-tree modifications before proceeding.

## When changing architecture

Update `CLAUDE.md`, relevant `docs/` files, and implementation in the same branch.
