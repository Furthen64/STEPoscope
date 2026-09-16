## Environment (uv only)

This project uses `uv` exclusively for Python environment and dependency management.

Rules:

- Do not run `pip install`.
- Do not run `python -m pip`.
- Do not run `python -m venv`.
- The virtual environment is `.venv`.
- Create it with `uv venv`.
- Add dependencies with `uv add <package>`.
- Add development dependencies with `uv add --dev <package>`.
- Remove dependencies with `uv remove <package>`.
- Install/synchronize dependencies with `uv sync`.
- Run project commands with `uv run <command>` when appropriate.
- Do not modify the environment behind uv's back.

If `.venv` does not exist, create/sync it using uv rather than falling back to pip.


