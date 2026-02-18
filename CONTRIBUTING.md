# Contributing to Model Council

Thank you for your interest in contributing! 🎉

## Getting Started

### Prerequisites

- Python 3.10+
- Git

### Development Setup

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/model-council-applications.git
cd model-council-applications

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"

# Verify
pytest tests/ -v
council models
```

---

## How to Contribute

### Reporting Bugs

Open an issue with:
- Clear description
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

### Suggesting Features

Open an issue with:
- Use case description
- Proposed solution

### Submitting Code

1. Fork the repository
2. Create branch from `main`
3. Make changes with tests
4. Run `pytest tests/ -v`
5. Submit PR

---

## Code Guidelines

- Python 3.10+
- Type hints required
- Docstrings for public functions
- Async/await for I/O

### Commit Messages

```
feat: add new feature
fix: resolve bug
docs: update documentation
test: add tests
```

---

## Testing

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=council
```

---

## Questions?

Open a [GitHub Issue](https://github.com/kraghavan/model-council-applications/issues).

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
