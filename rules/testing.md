# Testing Rules - Kublai

## Testing Philosophy
- Test critical paths first
- Test edge cases explicitly
- Test failure modes
- Automate where possible

## Test Coverage
- All critical functions must have tests
- Edge cases must be documented
- Integration tests for external dependencies
- Regression tests for bug fixes

## Test Structure
```python
def test_function_name():
    """Test description."""
    # Arrange
    input_data = ...
    
    # Act
    result = function(input_data)
    
    # Assert
    assert result == expected
```

## Validation Before Commit
- [ ] All tests pass
- [ ] No linting errors
- [ ] Documentation updated
- [ ] Change Log updated

## Test Types
1. **Unit Tests** - Test individual functions
2. **Integration Tests** - Test component interactions
3. **End-to-End Tests** - Test full workflows
4. **Regression Tests** - Prevent known bugs from returning
