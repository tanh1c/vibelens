"""MCP Server module"""


def __getattr__(name):
    """Lazy import to avoid RuntimeWarning when running as `python -m vibeengine.mcp.server`."""
    if name == "app":
        from vibeengine.mcp.server import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["app"]
