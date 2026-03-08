# Contributing to agent-trust-telemetry

Thank you for your interest in contributing!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/wharfe/agent-trust-telemetry.git
cd agent-trust-telemetry

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev,otel]"

# Run tests
pytest

# Run linter
ruff check src/ tests/

# Run type checker
mypy src/ tests/
```

## Commit Message Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(evaluator): add instruction_override detection rule
fix(schemas): correct content_hash pattern validation
docs: update ADR-003 with redaction examples
test(envelope): add negative validation cases
chore: update dev dependencies
```

## Adding Detection Rules

Detection rules live in `src/att/rules/builtin/` as YAML files. Each rule **must** have corresponding test cases (both positive and negative examples).

See `docs/mvp-requirements-v0.3.md` Section 5 for the rule format specification.

## Code Style

- Code comments in English
- Documentation may be in Japanese or English
- Run `ruff check` and `mypy` before submitting
- Target Python 3.10+ compatibility

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
