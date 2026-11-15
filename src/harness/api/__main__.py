"""Run the API on this machine only:  uv run python -m harness.api [--port 8000]

Demo mode trusts claimed IDs. Optional Entra API validation is a foundation, not a complete deployment.
Both modes bind to loopback; see docs/ammar-agent-integration.md for current limitations.
"""

import argparse

import uvicorn

from harness.api.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
