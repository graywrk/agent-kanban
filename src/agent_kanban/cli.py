"""`kanban` CLI entry point."""
import argparse
import sys

import uvicorn

from agent_kanban import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="kanban", description="Agent Kanban board")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Run the production server")
    serve_p.add_argument("--port", type=int, default=7331)
    serve_p.add_argument("--host", default="0.0.0.0")

    dev_p = sub.add_parser("dev", help="Run the dev server with reload")
    dev_p.add_argument("--port", type=int, default=7331)
    dev_p.add_argument("--host", default="0.0.0.0")

    sub.add_parser("migrate", help="Apply database migrations")

    args = parser.parse_args()

    if args.command == "migrate":
        _run_migrations()
    elif args.command == "serve":
        uvicorn.run(
            "agent_kanban.server:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            log_level="info",
        )
    elif args.command == "dev":
        uvicorn.run(
            "agent_kanban.server:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
            log_level="debug",
        )


def _run_migrations() -> None:
    import os
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    url = os.environ.get("DATABASE_URL")
    if url:
        cfg.set_main_option("sqlalchemy.url", url.replace("+asyncpg", ""))
    command.upgrade(cfg, "head")
    print("Migrations applied.")


if __name__ == "__main__":
    main()
