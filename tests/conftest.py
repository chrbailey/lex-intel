"""Shared test configuration — stub external dependencies once for all tests."""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stub external packages that may not be installed in test environment.
# Use setdefault so real packages aren't overwritten if installed.
for _mod in ("anthropic", "httpx"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

# pinecone needs a Pinecone class
if "pinecone" not in sys.modules:
    _pinecone = types.ModuleType("pinecone")
    _pinecone.Pinecone = MagicMock()
    sys.modules["pinecone"] = _pinecone
elif not hasattr(sys.modules["pinecone"], "Pinecone"):
    sys.modules["pinecone"].Pinecone = MagicMock()

# anthropic needs APIConnectionError
if not hasattr(sys.modules.get("anthropic", None), "APIConnectionError"):
    sys.modules["anthropic"].APIConnectionError = type("APIConnectionError", (Exception,), {})

# supabase needs create_client and Client attributes
if "supabase" not in sys.modules or not hasattr(sys.modules["supabase"], "create_client"):
    _supabase = types.ModuleType("supabase")
    _supabase.create_client = MagicMock()
    _supabase.Client = MagicMock()
    sys.modules.setdefault("supabase", _supabase)

# fastmcp needs FastMCP that returns a mock with @mcp.tool as passthrough
if "fastmcp" not in sys.modules:
    _fastmcp = types.ModuleType("fastmcp")
    _mock_mcp = MagicMock()
    _mock_mcp.tool = lambda f=None, **kw: f if f else (lambda fn: fn)
    _fastmcp.FastMCP = MagicMock(return_value=_mock_mcp)
    sys.modules["fastmcp"] = _fastmcp
