"""The `zetesis` command.

In a terminal it opens the chat. Launched by an MCP client, which talks over pipes
rather than a terminal, it runs the MCP server, so existing configs keep working.

  zetesis          chat when run in a terminal, MCP server otherwise
  zetesis chat     the chat
  zetesis mcp      the MCP server (same as zetesis-client)
"""
import sys


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg in ("-h", "--help"):
        print(__doc__.strip())
        return
    if arg in ("-V", "--version"):
        from . import __version__
        print(__version__)
        return
    if arg == "chat" or (not arg and sys.stdin.isatty() and sys.stdout.isatty()):
        from .chat import main as chat
        chat()
        return
    from .client import main as server
    server()
