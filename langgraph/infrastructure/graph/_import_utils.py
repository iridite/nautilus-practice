"""Utility for importing external langgraph.graph without conflicts"""

import sys
from pathlib import Path
from typing import Any


def import_external_langgraph() -> tuple[Any, Any]:
    """Import external langgraph.graph by temporarily modifying sys.modules and sys.path.

    This prevents conflicts with the project's langgraph module by:
    1. Temporarily removing project's langgraph from sys.modules
    2. Filtering sys.path to exclude project directory
    3. Importing external langgraph.graph
    4. Restoring original sys.modules and sys.path

    Returns:
        tuple[Any, Any]: (StateGraph, END) from external langgraph.graph
    """
    _original_langgraph = sys.modules.pop("langgraph", None)
    _original_langgraph_infra = sys.modules.pop("langgraph.infrastructure", None)
    _project_root = str(Path(__file__).parent.parent.parent.parent)
    _original_path = sys.path.copy()

    try:
        sys.path = [
            p
            for p in sys.path
            if p != _project_root and p != "" and not p.startswith("__editable__")
        ]
        import langgraph.graph as _lg  # type: ignore[import-untyped]

        return _lg.StateGraph, _lg.END
    finally:
        sys.path = _original_path
        if _original_langgraph is not None:
            sys.modules["langgraph"] = _original_langgraph
        if _original_langgraph_infra is not None:
            sys.modules["langgraph.infrastructure"] = _original_langgraph_infra
