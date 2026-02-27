# LangGraph Import Workaround

## Problem

This project has a directory named `langgraph/` which conflicts with the external `langgraph` package from PyPI. When Python tries to import `langgraph.graph`, it finds the project's `langgraph` directory first instead of the external package.

## Solution

We use a temporary `sys.path` and `sys.modules` manipulation to import the external `langgraph.graph` module:

```python
import sys
from pathlib import Path

# Step 1: Remove project's langgraph from sys.modules
_original_langgraph = sys.modules.pop("langgraph", None)
_original_langgraph_infra = sys.modules.pop("langgraph.infrastructure", None)

# Step 2: Temporarily filter sys.path to exclude project directory
_project_root = str(Path(__file__).parent.parent.parent.parent)
_original_path = sys.path.copy()

try:
    # Filter out project directory and editable install paths
    sys.path = [
        p for p in sys.path
        if p != _project_root and p != '' and not p.startswith("__editable__")
    ]

    # Import external langgraph
    import langgraph.graph as _lg

    StateGraph = _lg.StateGraph
    END = _lg.END
finally:
    # Restore sys.path and sys.modules
    sys.path = _original_path
    if _original_langgraph is not None:
        sys.modules["langgraph"] = _original_langgraph
    if _original_langgraph_infra is not None:
        sys.modules["langgraph.infrastructure"] = _original_langgraph_infra
```

## Why This Works

1. **Remove from sys.modules**: Python caches imported modules in `sys.modules`. We temporarily remove the project's `langgraph` module.

2. **Filter sys.path**: We remove:
   - The project root directory
   - Empty string (current directory)
   - Editable install paths (which point back to the project)

3. **Import and extract**: We import the external package and extract only what we need (`StateGraph`, `END`).

4. **Restore**: We restore the original `sys.path` and `sys.modules` so the rest of the project code can import from the project's `langgraph` directory normally.

## Alternative Solutions Considered

1. **Rename project directory**: Would be the cleanest solution but requires updating all imports across the project.

2. **Use absolute imports with package prefix**: Doesn't work because Python's import system still finds the project directory first.

3. **Modify PYTHONPATH**: Doesn't work reliably across different execution contexts (pytest, direct execution, etc.).

## Files Using This Workaround

- `langgraph/infrastructure/graph/research_graph.py`
- `langgraph/infrastructure/graph/optimize_graph.py`

## Testing

All tests pass with this workaround:
- `langgraph/tests/unit/infrastructure/graph/test_research_graph.py` (9 tests)
- `langgraph/tests/unit/infrastructure/graph/test_optimize_graph.py` (9 tests)
- `langgraph/tests/unit/infrastructure/graph/test_state.py` (6 tests)
