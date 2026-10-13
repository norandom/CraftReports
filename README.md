# CraftReport operation kernel

The engineering foundation is implemented. Product operations and installed-wheel
REST/MCP conformance remain pending their approved implementation tasks. Fast
engineering results do not establish browser behavior, durable state, or verified
reporting artifacts.

Use CPython 3.12.10 and uv 0.13.0. Development dependencies are pinned in
`pyproject.toml` and `uv.lock`:

```sh
uv sync --frozen --group dev
uv run python scripts/check.py --fast
uv run pre-commit install
uv run pre-commit run --all-files
```

On this Windows workstation, invoke `uv.exe` to bypass the PowerShell `uv` wrapper.
The portable commands above are the hook and CI commands.

The fast command runs Ruff lint and format checking, strict Pyright, approved
size/branching budgets, breadth and retirement aging, import boundaries, and focused
tests. It checks all source, scripts, tests, and any activated capability packages,
including unstaged files. Tests are measured separately from production budgets.
An unavailable or failed check stops the pipeline with a nonzero exit. Focused
tests exclude the declared `integration` marker; the pipeline tests execute real
subprocess effects without recursively invoking the fast command.

The local hook always invokes the whole-scope fast command and takes no staged
filenames. Install it in each clone; repository metadata records the verified
development workspace, not installation on every machine. CI uses the same command
on pushes, pull requests, manual runs, and a daily schedule so retirement aging is
checked without a new commit. Hosted CI execution has not yet been observed.

```sh
uv run python scripts/check.py --integration
```

Integration currently reports unavailable and exits nonzero. Its separate CI job
is explicitly skipped pending task 8.1's real installed-wheel harness; no passing
conformance result is implied. Task 8.4 completes that stage's conformance coverage.

Gate inputs include `quality.toml`, `breadth.toml`, the two registered specifications'
`spec.json` files, the kernel `design-review.md` approval reference, and
`.kiro/steering/overview.md`. Keep these versioned with the scripts and configuration
so a fresh checkout can execute the same checks.
