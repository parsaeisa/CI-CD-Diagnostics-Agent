# CI-CD-Diagnostics-Agent
An AI agent backed by Claude API key, which checks failed test jobs in a project and suggests solutions and unit tests.


Output example:
```bash
[Agent] Starting diagnostic process...
[Agent] Iteration 1/5
[Agent] Calling tool 'get_failed_run_logs' with arguments: {'repo_name': 'parsaeisa/ci-cd-diagnostic-agent-sandbox', 'run_id': 44584440522}
[Agent] Iteration 2/5
[Agent] Calling tool 'get_file_content' with arguments: {'repo_name': 'parsaeisa/ci-cd-diagnostic-agent-sandbox', 'file_path': 'tests/test_calculator.py', 'ref': '1395d548c1b2d7fd1d1b6859a6e744c540fea74c'}
[Agent] Calling tool 'get_file_content' with arguments: {'repo_name': 'parsaeisa/ci-cd-diagnostic-agent-sandbox', 'file_path': 'app/calculator.py', 'ref': '1395d548c1b2d7fd1d1b6859a6e744c540fea74c'}
[Agent] Calling tool 'get_file_content' with arguments: {'repo_name': 'parsaeisa/ci-cd-diagnostic-agent-sandbox', 'file_path': '.github/workflows/ci.yml', 'ref': '1395d548c1b2d7fd1d1b6859a6e744c540fea74c'}
[Agent] Iteration 3/5
[Agent] Final diagnostic report is ready.

{
  "root_cause": "Collection fails with `ModuleNotFoundError: No module named 'app'`. The workflow runs bare `pytest`, not `python -m pytest`, so the repository root is not put on `sys.path`. 
    With pytest's default `prepend` import mode and no `__init__.py` or `conftest.py` in `tests/`, pytest only inserts `tests/` into `sys.path`. `from app.calculator import ...` therefore 
    can't find the `app` package at the repo root. No `pytest.ini`, `conftest.py` or package install makes the root importable.

Once the import is fixed, three tests will fail because of bugs in `app/calculator.py`:
- `calculate_discount` adds the discount (`price + ...`) instead of subtracting it, so the standard-discount test would get 120.0, not 80.0.
- `calculate_discount` doesn't validate `discount_percent`, so -10 never raises `ValueError`.
- `get_average_latency([])` raises `ZeroDivisionError` instead of returning 0.0.",
  "proposed_fix": "1) Make the repo root importable. Add a `pytest.ini` at the repo root:

```ini
[pytest]
pythonpath = .
testpaths = tests
```
(Alternatives: an empty `conftest.py` at the repo root, or changing the workflow step to `python -m pytest -v --tb=short`.)

Also add an empty `app/__init__.py` if it doesn't already exist.

2) Fix `app/calculator.py`:

```python
def calculate_discount(price: float, discount_percent: float) -> float:
    \"\"\"Calculates the final price after applying a percentage discount.\"\"\"
    if price < 0:
        raise ValueError(\"Price cannot be negative\")
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError(\"Discount percent must be between 0 and 100\")
    final_price = price - (price * (discount_percent / 100))
    return round(final_price, 2)


def get_average_latency(latencies: list[float]) -> float:
    \"\"\"Computes average latency from a list of response times.\"\"\"
    if not latencies:
        return 0.0
    return sum(latencies) / len(latencies)
```",
  "unit_test": "
import pytest
from app.calculator import calculate_discount, get_average_latency


def test_app_package_importable():
    import app.calculator  # fails with ModuleNotFoundError if the root is not on sys.path


def test_calculate_standard_discount():
    assert calculate_discount(100.0, 20.0) == 80.0


@pytest.mark.parametrize(\"pct\", [-10.0, 100.01, 150.0])
def test_calculate_invalid_discount(pct):
    with pytest.raises(ValueError):
        calculate_discount(100.0, pct)


def test_negative_price():
    with pytest.raises(ValueError):
        calculate_discount(-1.0, 10.0)


def test_average_latency_empty_list():
    assert get_average_latency([]) == 0.0


def test_average_latency_values():
    assert get_average_latency([100.0, 200.0]) == 150.0"
}
```