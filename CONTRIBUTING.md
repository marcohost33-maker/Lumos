# Contributing to Lumos

Thanks for your interest in improving **Lumos** — a small personal assistant
with reminders and Google Drive sync, exposed as a Python library and a `lumos`
command-line tool.

This guide explains how to set up a development environment, run the test
suite, and submit changes.

## Project at a glance

- **Language:** Python (>= 3.9)
- **Shape:** a `lumos` package (`src/lumos/`) with a CLI entry point and a
  small set of focused modules:
  - `cli.py` — command-line interface (`lumos` / `python -m lumos`)
  - `reminders.py` — reminder logic
  - `storage.py` — local persistence
  - `drive.py` — Google Drive sync (`DriveClient` abstraction)
  - `config.py` — configuration handling
- **License:** MIT (see [`LICENSE`](LICENSE)).

## Development setup

```bash
# clone, then from the repo root:
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .[dev,gdrive]
```

- `dev` installs the test tooling (`pytest`, `pytest-cov`, `freezegun`).
- `gdrive` installs the Google Drive client libraries. It is optional — the
  test suite runs without network access and without Drive credentials.

## Running the tests

```bash
pytest                 # full suite
pytest --cov=lumos     # with coverage
```

The test suite is designed to run **without network access**: Drive
interactions go through the `DriveClient` abstraction and are exercised with
fakes/fixtures. Please keep new tests offline-safe.

## Making a change

1. Create a topic branch off `main`.
2. Make your change with accompanying tests.
3. Run `pytest` locally and make sure it is green.
4. Open a pull request describing **what** changed and **why**. CI must pass
   before review.

Small, focused PRs are easier to review than large ones. If you are planning a
larger change, please open an issue first so we can agree on the direction.

## Code style

Keep the style consistent with the surrounding code: clear names, small
functions, and comments only where the *why* is not obvious. There is no
enforced formatter in the repo today; match what is already there.

## Licensing of contributions

Lumos is released under the **MIT License**. By contributing, you agree that
your contributions are licensed under the same MIT terms as the rest of the
project. There is no contributor license agreement (CLA) to sign.

## Reporting bugs and security issues

- **Bugs / feature requests:** open a GitHub issue with steps to reproduce.
- **Security vulnerabilities:** please do **not** open a public issue. Follow
  the process described in [`SECURITY.md`](SECURITY.md).

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By
participating, you are expected to uphold it.
