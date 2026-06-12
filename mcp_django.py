"""Django MCP server — gives Claude Code tools to interact with this Django project."""
import os
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
MANAGE = os.path.join(PROJECT_DIR, "manage.py")

mcp = FastMCP("OpenSkagit Django")


def _run(args: list[str], input_text: str | None = None) -> str:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        input=input_text,
        timeout=60,
    )
    out = result.stdout.strip()
    err = result.stderr.strip()
    if out and err:
        return f"{out}\n\nSTDERR:\n{err}"
    return out or err or "(no output)"


@mcp.tool()
def manage(command: str, args: str = "") -> str:
    """Run any Django management command.

    Examples:
      manage("migrate")
      manage("showmigrations")
      manage("dbshell", "--command='SELECT count(*) FROM auth_user'")
      manage("import_assessor", "--remote")
    """
    cmd_parts = [PYTHON, MANAGE, command]
    if args:
        import shlex
        cmd_parts += shlex.split(args)
    return _run(cmd_parts)


@mcp.tool()
def shell(code: str) -> str:
    """Execute Python code inside the Django shell (full ORM access).

    Example:
      shell("from django.contrib.auth.models import User; print(User.objects.count())")
    """
    return _run([PYTHON, MANAGE, "shell", "-c", code])


@mcp.tool()
def list_commands() -> str:
    """List all available Django management commands."""
    return _run([PYTHON, MANAGE, "help", "--commands"])


@mcp.tool()
def check(deploy: bool = False) -> str:
    """Run Django system checks (optionally with --deploy flag)."""
    args = [PYTHON, MANAGE, "check"]
    if deploy:
        args.append("--deploy")
    return _run(args)


@mcp.tool()
def migrations_status() -> str:
    """Show status of all Django migrations."""
    return _run([PYTHON, MANAGE, "showmigrations"])


if __name__ == "__main__":
    mcp.run()
