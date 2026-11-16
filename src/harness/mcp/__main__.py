"""Run a loopback MCP server: python -m harness.mcp zambeel|fe [--port N]."""
import argparse
from contextlib import closing
import anyio

import uvicorn

from harness.config import load_env
from harness.mcp.security import DemoIdentityMiddleware, Principal, principal, service_secret


class RecoveryLifespan:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "lifespan":
            return await self.app(scope, receive, send)
        from harness.mcp.recovery import recover
        async def loop():
            while True:
                await anyio.to_thread.run_sync(recover)
                await anyio.sleep(5)
        async with anyio.create_task_group() as group:
            async def wrapped_send(message):
                if message["type"] == "lifespan.startup.complete":
                    group.start_soon(loop)
                await send(message)
            try:
                await self.app(scope, receive, wrapped_send)
            finally:
                group.cancel_scope.cancel()


def main():
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", choices=["zambeel", "fe"])
    parser.add_argument("--transport", choices=["streamable-http", "stdio"], default="streamable-http")
    parser.add_argument("--port", type=int)
    parser.add_argument("--actor", help="Required demo actor for stdio (not a tool argument)")
    parser.add_argument("--role", choices=["student", "instructor"], default="student")
    args = parser.parse_args()
    from harness.mcp.entra import mode, configured_verifier, BearerMiddleware
    auth_mode = mode()
    if auth_mode == "demo":
        service_secret()  # local mode only
    elif args.transport != "streamable-http":
        parser.error("Entra requires HTTP bearer authentication; demo stdio actors are forbidden")
    if args.server == "fe":
        from harness.mcp.fe import create_server
    else:
        from harness.mcp.zambeel import create_server
    server = create_server()
    if args.transport == "stdio":
        if not args.actor:
            parser.error("--actor is required for stdio demo identity")
        principal.set(Principal(args.actor, args.role))
        server.run(transport="stdio")
    else:
        if args.server == "fe":
            from harness.mock_zambeel import connect
            from harness import jobs
            with closing(connect()) as conn:
                jobs.initialize(conn)
        app = server.streamable_http_app()
        if auth_mode == "entra":
            app = BearerMiddleware(app, configured_verifier(args.server))
            if args.server == "fe":
                app = RecoveryLifespan(app)
        else:
            app = DemoIdentityMiddleware(app)
        uvicorn.run(app, host="127.0.0.1", port=args.port or (8101 if args.server == "fe" else 8102))


if __name__ == "__main__":
    main()
