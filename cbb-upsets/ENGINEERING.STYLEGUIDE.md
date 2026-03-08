# Repository Engineering Style Guide

This repository is a focused ingest and storage tool for NCAA men's basketball
data. The supported workflows are:

- initialize and inspect the local Postgres database
- ingest historical ESPN game data
- ingest current and historical Odds API odds data
- train, backtest, and invoke betting models
- audit and repair stored game data
- run the local Helm chart and supporting Make targets

Anything outside that scope should not be added unless the repository direction
changes first.

## Core Principles

- Keep the repository aligned with its active workflows. Remove dead code,
  placeholder features, and speculative schema before adding new abstractions.
- Favor simple, explicit code over cleverness.
- Optimize for correctness, repeatability, and low operational surprise.
- Make changes safe to rerun. Idempotent schema, ingest checkpoints, and
  deterministic CLI behavior are preferred.
- Do not widen scope accidentally. If a feature is not implemented, do not
  leave partial interfaces behind.

## Python Standards

### Tooling

- Use `uv` or the existing `.venv` workflow to manage Python dependencies.
- Keep runtime dependencies in `pyproject.toml`.
- Use Ruff for linting and formatting.
- Use mypy for static type checking.
- Use pytest for tests.

### Code Style

- Follow PEP 8 and keep line length at 88 characters.
- Use snake_case for functions and variables, PascalCase for classes, and
  UPPER_CASE for constants.
- Keep imports grouped and sorted automatically by Ruff.
- Avoid wildcard imports.
- Prefer dataclasses for simple immutable value objects.

### Typing

- Add type hints to all public function and method signatures.
- Use `T | None` for nullable values.
- Avoid `Any` unless there is no practical alternative.
- Keep mypy clean for the `src/` tree.

### Function Design

- Keep functions focused on one job.
- Prefer small helpers over deeply nested control flow.
- Use early returns to keep the happy path obvious.
- Do not use mutable default arguments.
- Use context managers for files, database connections, and subprocess-related
  resources when possible.

### Error Handling

- Catch specific exceptions.
- Raise actionable error messages.
- Do not silently swallow failures.
- Never log or print secrets, tokens, or URLs that embed credentials.

### Documentation

- Every public function, class, and module should have a clear docstring.
- Complex internal helpers should also be documented when their behavior is not
  obvious from the code.
- Keep comments factual and short.
- Every repository change that affects user-facing behavior should keep the
  canonical repository documentation current.

### Repository Documentation Structure

- The repository must contain `README.md`, `docs/model.md`, and
  `docs/architecture.md`.
- `README.md` is the repository entry point. It must explain what the system
  does, how to run it locally, the major CLI commands, and where to find deeper
  documentation.
- `docs/model.md` must explain the machine learning system from the top down:
  prediction goal, data inputs, features, model type, training, calibration,
  improvement strategy, and evaluation.
- `docs/architecture.md` must explain the engineering system from the top down:
  major components, storage, Kubernetes shape, training workflow, prediction
  workflow, and artifact management.
- The three canonical docs must stay cross-linked. `README.md` must link to
  both docs, and both docs must link back to `README.md`.
- Prefer clear engineering language over marketing language.
- Explain concepts before implementation details.
- Prefer conceptual explanations over code dumps.
- Every major subsystem must be documented.
- The major CLI commands must be documented in `README.md`.
- Future pull requests that change the model, architecture, deployment, or CLI
  must update these docs as part of the change.

### Testing

- Add or update tests for every behavior change.
- Mock network APIs and filesystem effects in unit tests.
- Prefer deterministic test fixtures over real-time behavior.
- Run Ruff, mypy, and pytest before considering the work complete.

## SQL Standards

- The schema must reflect only supported product behavior.
- Prefer additive, idempotent DDL in `sql/schema.sql` so `cbb db init` is safe
  to rerun on an existing local database.
- Use explicit constraint and index names when they add clarity.
- Keep table and column names snake_case.
- Use the narrowest practical data type.
- Prefer `TIMESTAMP WITH TIME ZONE` for event times.
- Prefer `JSONB` for structured queryable data. Opaque raw payload archives may
  remain `TEXT` when they are stored and retrieved as raw upstream blobs.
- Add indexes only for active query patterns.
- Remove unused tables and indexes instead of carrying forward speculative
  modeling structures.

## Helm Standards

- Treat `values.yaml` as the stable base configuration and
  `values-local.yaml` as the minimal local override layer.
- Do not use floating image tags such as `latest`.
- Keep templates declarative and value-driven. Avoid hardcoded environment
  details inside templates when they belong in values files.
- Reuse helper templates for shared labels and selectors.
- Omit empty blocks rather than rendering no-op YAML.
- Keep chart metadata explicit, including `type` and `appVersion`.
- Validate changes with `helm lint` and `helm template`.

## Makefile Standards

- Keep target names short, literal, and task-oriented.
- Reuse shared variables for repeated tool paths and chart arguments.
- Mark non-file targets with `.PHONY`.
- Prefer shell settings that fail fast.
- Keep targets composable so `make check` can run the full local verification
  path.
- Do not hide destructive behavior behind ambiguous target names.

## Verification Checklist

- `ruff check src tests`
- `mypy`
- `pytest -q`
- `helm lint chart/cbb-upsets -f chart/cbb-upsets/values.yaml -f chart/cbb-upsets/values-local.yaml`
- `helm template cbb-upsets chart/cbb-upsets -f chart/cbb-upsets/values.yaml -f chart/cbb-upsets/values-local.yaml`
- smoke test any changed CLI commands against the forwarded local Postgres when
  the change affects runtime behavior
- verify `README.md`, `docs/model.md`, and `docs/architecture.md` exist and
  that their cross-links resolve
