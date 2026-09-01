# Contributing to Multi-AGY

Thank you for your interest in contributing to Multi-AGY!

## Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/sudhir-asuracore/multi-agy.git
   cd multi-agy
   ```

2. **Run the test suite**:
   ```bash
   python3 -m unittest discover -s tests -p "test_*.py" -v
   ```
   Or using make:
   ```bash
   make test
   ```

3. **Install locally for development**:
   ```bash
   make install
   ```

## Pull Request Guidelines

- Ensure all existing unit tests pass.
- Add test coverage for any new features or edge cases.
- Follow PEP 8 guidelines and keep code clean and typed.
- Update documentation in `README.md` if CLI flags or workflows change.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
