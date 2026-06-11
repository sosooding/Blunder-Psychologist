"""Small management CLI. Usage: python -m blunder.manage <command>."""

import argparse

from .db import SessionLocal
from .queue import enqueue


def main() -> None:
    parser = argparse.ArgumentParser(prog="blunder.manage")
    sub = parser.add_subparsers(dest="cmd", required=True)

    hello = sub.add_parser("enqueue-hello", help="enqueue a hello job")
    hello.add_argument("--name", default="world")

    args = parser.parse_args()

    if args.cmd == "enqueue-hello":
        with SessionLocal() as session:
            job_id = enqueue(session, "hello", {"name": args.name}, priority=0)
        print(f"enqueued hello job id={job_id}")


if __name__ == "__main__":
    main()
