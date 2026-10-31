"""Run a loopback MCP server: python -m harness.mcp zambeel|fe [--port N]."""
import argparse

import uvicorn

from harness.config import load_env
from harness.mcp.security import DemoIdentityMiddleware, Principal, principal, service_secret


def main():
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", choices=["zambeel", "fe"])
    parser.add_argument("--transport", choices=["streamable-http", "stdio"], default="streamable-http")
    parser.add_argument("--port", type=int)
    parser.add_argument("--actor", help="Required demo actor for stdio (not a tool argument)")
    parser.add_argument("--role", choices=["student", "instructor"], default="student")
    args = parser.parse_args()
    service_secret()  # fail closed; do not invent a default credential
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
        app = DemoIdentityMiddleware(server.streamable_http_app())
        uvicorn.run(app, host="127.0.0.1", port=args.port or (8101 if args.server == "fe" else 8102))


if __name__ == "__main__":
    main()
