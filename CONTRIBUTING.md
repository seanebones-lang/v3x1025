# Contributing to Dealership RAG

Thank you for your interest in contributing to the Dealership RAG system! This document provides guidelines for contributing to the project.

## 🎯 How to Contribute

### Reporting Bugs

1. Check existing [GitHub Issues](https://github.com/seanebones-lang/AutoRAG/issues)
2. Create a new issue with:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)
   - Relevant logs or error messages

### Suggesting Features

1. Open a GitHub Issue with the `enhancement` label
2. Describe the feature and its use case
3. Provide examples if possible
4. Discuss with maintainers before implementing

### Pull Requests

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following our coding standards
4. **Add tests** for new functionality
5. **Update documentation** as needed
6. **Run tests** to ensure everything passes:
   ```bash
   pytest --cov=src
   ```
7. **Commit** with clear messages:
   ```bash
   git commit -m "feat: add new DMS adapter for XYZ"
   ```
8. **Push** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
9. **Create Pull Request** on GitHub

## 📝 Coding Standards

### Python Style

- Follow [PEP 8](https://pep8.org/)
- Use type hints for function signatures
- Write docstrings for all public functions/classes
- Maximum line length: 100 characters

### Code Quality Tools

```bash
# Linting
ruff check src/ tests/

# Type checking
mypy src/ --ignore-missing-imports

# Formatting
black src/ tests/

# Sort imports
isort src/ tests/
```

### Testing

- Write tests for all new features
- Maintain >80% code coverage
- Use pytest fixtures from `tests/conftest.py`
- Test edge cases and error handling

Example test structure:
```python
@pytest.mark.asyncio
async def test_new_feature(sample_data):
    """Test description."""
    # Arrange
    component = MyComponent()
    
    # Act
    result = await component.method(sample_data)
    
    # Assert
    assert result.success is True
    assert result.data is not None
```

## 🏗️ Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/AutoRAG.git
   cd AutoRAG
   ```

2. Create virtual environment:
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"  # If dev extras are defined
   ```

4. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

## 🔍 Areas for Contribution

### High Priority

- **DMS Adapters**: Additional dealership management systems
- **Performance**: Query optimization, caching improvements
- **Testing**: Increase coverage, add integration tests
- **Documentation**: Tutorials, examples, API guides

### Feature Ideas

- Multimodal support (vehicle images)
- Voice interface integration
- Custom embedding models
- Advanced analytics dashboard
- Mobile SDK
- Multi-language support

### Bug Fixes

Check the [Issues page](https://github.com/seanebones-lang/AutoRAG/issues) for bugs labeled `good first issue`.

## 📚 Documentation

When adding features:

1. Update relevant `.md` files in `docs/`
2. Add docstrings to all new functions/classes
3. Update API documentation if endpoints change
4. Add examples to README if applicable

Documentation style:
```python
def function_name(param1: str, param2: int) -> bool:
    """
    Brief description of what the function does.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When validation fails
        
    Example:
        >>> result = function_name("test", 42)
        >>> print(result)
        True
    """
```

## 🎨 Commit Message Guidelines

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions/changes
- `refactor:` Code refactoring
- `perf:` Performance improvements
- `chore:` Maintenance tasks

Examples:
```
feat: add Dealertrack DMS adapter
fix: resolve embedding batch size issue
docs: update API examples in README
test: add tests for hybrid retrieval
```

## 🔐 Security

- Never commit API keys or secrets
- Use environment variables for configuration
- Report security issues privately to maintainers
- Follow OWASP security best practices

## 📋 Review Process

1. Automated checks must pass (CI/CD)
2. Code review by maintainer(s)
3. All discussions resolved
4. Tests passing with adequate coverage
5. Documentation updated
6. Merge when approved

## 🤝 Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help newcomers learn
- Assume good intentions
- Keep discussions professional

## 📞 Questions?

- Open a GitHub Discussion
- Comment on relevant issues
- Reach out to maintainers

## 🏆 Recognition

Contributors will be:
- Listed in CHANGELOG.md
- Credited in release notes
- Added to CONTRIBUTORS.md (if created)

Thank you for contributing to Dealership RAG! 🚀

