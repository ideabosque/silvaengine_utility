# Repository Guidelines

## Project Structure & Module Organization
`silvaengine_utility/` contains the core package. Key modules include `utility.py` (AWS + orchestration), `json_handler.py` (orjson-based serialization), `datetime_handler.py` (Pendulum parsing), and `performance_monitor.py` (metrics). Tests reside in `tests/`; mirror the directory layout when adding new suites. Build artefacts land in `build/` and should stay out of source control. Update `API_DOCUMENTATION.md`, `MIGRATION_GUIDE.md`, and `PERFORMANCE_IMPROVEMENT_PLAN.md` whenever public interfaces or performance benchmarks change.

## Build, Test, and Development Commands
- `python -m pip install -e .[dev]` sets up editable installs with linting and typing extras.
- `pytest` runs the default suite (`tests/`) with coverage configured in `pyproject.toml`.
- `pytest --cov=silvaengine_utility --cov-report=term-missing` surfaces coverage gaps before review.
- `black .` formats to the repository standard (88 characters, Python 3.9 target).
- `flake8 silvaengine_utility tests` and `mypy silvaengine_utility` catch style and typing regressions.
- `python -m build` produces distributable wheels and source archives in `dist/`.

## Coding Style & Naming Conventions
Follow Black formatting with 4-space indents and wrap at 88 characters. Modules and functions use `snake_case`; classes use `PascalCase`; constants stay upper snake. Type hints are required for public functions because `mypy` runs with `disallow_untyped_defs`. Place shared serialization logic in `json_handler.py` or helpers in `utility.py`; avoid duplicating AWS wrappers. Keep docstrings concise and describe side effects or external service calls.

## Testing Guidelines
Pytest discovers files named `test_*.py`, `Test*` classes, and functions named `test_*`. Add new cases next to the features they exercise (e.g., JSON helpers belong in `tests/test_json_handler.py`). Maintain or raise coverage reported by `--cov`, and include benchmark markers when touching hot paths such as the JSON handler. Use descriptive test names and fixtures that mirror realistic AWS payloads for regression tests.

## Commit & Pull Request Guidelines
Commit messages are short and imperative (e.g., `Update invoke logic`); scope each commit to a single concern. Reference GitHub issues in the footer when applicable. Pull requests should outline the change, list verification commands, and call out performance impacts or schema updates. Attach before/after metrics or console snippets when altering monitoring logic, and request review from owners of the affected area.
