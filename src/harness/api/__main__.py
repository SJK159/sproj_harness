"""Run the API on this machine only:  uv run python -m harness.api [--port 8000]

There is no authentication (the frontend sends a claimed student or instructor id), so it binds to 127.0.0.1.
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
