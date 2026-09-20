# Repository Instructions

## Scope and navigation

- Maumau contains local sports betting applications. The implemented app is
  `cbb-upsets/`: NCAA men's basketball ingestion, modeling, and a dashboard.
- Before working in CBB, read [cbb-upsets/AGENTS.md](cbb-upsets/AGENTS.md).
  Its commands and paths are relative to `cbb-upsets/`.
- Add future sports applications as siblings when requested. They may share
  the local k3d cluster, but should own their code, configuration, data,
  deployments, and tests. Keep the requested MVP small; extract shared code
  only when concrete applications need it.
- The repository model default lives in [.codex/config.toml](.codex/config.toml).
  Keep model selection there rather than duplicating it in role prompts.

## Working approach

- Inspect the current source and Git status before editing. Historical
  roadmap entries describe past work and proposals, not necessarily current
  behavior or authorization to build the next item.
- Carry out the user's current request, including relevant verification.
  Resolve routine implementation choices without asking for confirmation.
- Keep ordinary focused changes in the current checkout when safe. Use an
  isolated worktree when parallel work or conflicting changes require it.
- Keep changes scoped and preserve unrelated work. Do not recreate custom
  agent roles or background development supervisors unless requested.
- Never print or commit credentials, credential-bearing URLs, or local secret
  overrides. Preserve databases, volumes, backups, and unrelated worktrees.
- Keep instructions concise and tied to actual source paths and commands.
  Update them when workflows change; avoid duplicating the application docs.

## Commit completed work

- After completing a requested file change, run the relevant checks, review
  the diff, and create a local Git commit before sending the final response.
- Commit by default without asking for routine confirmation, unless the user
  explicitly requests otherwise.
- Stage only changes made for the task. Preserve unrelated user changes and
  untracked files; do not include them in the commit.
- Include the commit hash and verification results in the final response.
- Push or merge only when the user requests it.
- Read-only answers need no empty commit. If a check or commit is blocked,
  report the blocker accurately; do not bypass hooks or claim success.

Read any nested `AGENTS.md` for project-specific working rules.
