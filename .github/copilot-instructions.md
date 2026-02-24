# GitHub Copilot PR Review Instructions

## Overview
This file defines the guidelines for GitHub Copilot when reviewing pull requests in this repository.

## Review Focus Areas

### 1. Code Quality & Best Practices
- Check for proper error handling and edge cases
- Verify code follows Python 3.12+ best practices
- Ensure proper use of type hints (use `int | None` instead of `Optional[int]`)
- Verify financial calculations use `Decimal` instead of `float`
- Check for proper resource cleanup (context managers, try-finally blocks)
- Ensure code follows single responsibility principle

### 2. Testing Requirements
- Verify new features have corresponding unit tests
- Check test coverage meets minimum threshold (28%)
- Ensure tests are properly organized in `tests/` directory
- Verify test names follow `test_*.py` pattern
- Check that tests actually test the intended functionality

### 3. Code Style & Formatting
- Verify code follows Ruff formatting rules
- Check line length (max 100 characters)
- Ensure proper naming conventions:
  - Functions/variables: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`
  - Private members: `_leading_underscore`
- Verify imports are properly organized

### 4. Security & Safety
- Check for hardcoded credentials or API keys
- Verify sensitive data is not logged
- Ensure proper input validation
- Check for SQL injection vulnerabilities (if applicable)
- Verify network requests have proper timeout and retry logic

### 5. Performance Considerations
- Flag inefficient algorithms or data structures
- Check for unnecessary loops or repeated calculations
- Verify proper use of caching mechanisms
- Ensure database queries are optimized (if applicable)
- Check for memory leaks or resource exhaustion

### 6. NautilusTrader Specific
- Verify proper use of NautilusTrader 1.223.0 API
- Check strategy configuration follows project patterns
- Ensure proper instrument and data handling
- Verify position management follows best practices
- Check for proper use of custom data types (OI, Funding Rate)

### 7. Documentation
- Verify functions have proper docstrings
- Check that complex logic has explanatory comments
- Ensure README or CLAUDE.md is updated for new features
- Verify configuration changes are documented

### 8. Architecture & Design
- Check if changes follow existing patterns in `strategy/common/`
- Verify proper separation of concerns
- Ensure new code doesn't duplicate existing functionality
- Check if refactoring maintains backward compatibility
- Verify proper use of configuration system (YAML → Pydantic → Adapter)

### 9. Git & CI/CD
- Verify commit messages follow conventional format: `<type>(<scope>): <description>`
- Check branch naming follows pattern: `<type>/<description>`
- Ensure PR size is reasonable (< 500 lines net change preferred)
- Verify CI checks will pass before merge

### 10. Anti-Patterns to Flag
- Over-engineering for small number of use cases
- Creating abstractions without clear need
- Adding "future-proof" code that isn't needed now
- Large refactorings without clear business value
- Creating documentation that won't be maintained

## Review Tone
- Be constructive and helpful
- Provide specific suggestions with code examples
- Explain the "why" behind recommendations
- Acknowledge good practices when present
- Prioritize critical issues over nitpicks

## What NOT to Review
- Personal coding style preferences (if code follows project standards)
- Minor formatting issues that Ruff will catch
- Theoretical performance issues without evidence
- Suggestions for features not in scope of the PR

## Special Considerations

### For Strategy Development
- Verify strategy uses reusable components from `strategy/common/` when possible
- Check if new indicators/signals should be extracted to common library
- Ensure strategy configuration is properly validated

### For Performance Changes
- Request benchmark data or profiling results
- Verify optimization doesn't sacrifice code clarity
- Check if performance claims are measurable

### For Refactoring PRs
- Verify tests pass and behavior is unchanged
- Check if refactoring reduces code complexity
- Ensure refactoring has clear motivation

## Approval Criteria
A PR should be approved if:
- All CI checks pass (tests, lint, coverage)
- No critical security or correctness issues
- Code follows project conventions
- Changes are well-tested
- Documentation is updated (if needed)
- PR size is reasonable

## Rejection Criteria
A PR should request changes if:
- Tests are failing
- Critical bugs or security issues present
- Code violates project standards
- Missing tests for new functionality
- Breaking changes without migration path
- PR is too large (> 1000 lines net change)
