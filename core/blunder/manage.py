"""Small management CLI. Usage: python -m blunder.manage <command>."""

import argparse

from .db import SessionLocal
from .flows import PRIORITY_BACKFILL, PRIORITY_ONDEMAND
from .queue import enqueue


def main() -> None:
    parser = argparse.ArgumentParser(prog="blunder.manage")
    sub = parser.add_subparsers(dest="cmd", required=True)

    hello = sub.add_parser("enqueue-hello", help="enqueue a hello job")
    hello.add_argument("--name", default="world")

    bf = sub.add_parser("enqueue-backfill", help="enqueue a user backfill")
    bf.add_argument("--username", required=True)
    bf.add_argument("--strategy", default=None, choices=["recent", "random", "stratified"])
    bf.add_argument("--max-games", type=int, default=None)

    an = sub.add_parser("enqueue-analyze", help="enqueue an on-demand single-game analysis")
    an.add_argument("--username", required=True)
    an.add_argument("--game-url", default=None)
    an.add_argument("--pgn-file", default=None, help="path to a PGN file to analyze")

    args = parser.parse_args()

    if args.cmd == "enqueue-hello":
        with SessionLocal() as session:
            job_id = enqueue(session, "hello", {"name": args.name}, priority=PRIORITY_ONDEMAND)
        print(f"enqueued hello job id={job_id}")

    elif args.cmd == "enqueue-backfill":
        payload: dict[str, object] = {"username": args.username}
        if args.strategy:
            payload["strategy"] = args.strategy
        if args.max_games:
            payload["max_games"] = args.max_games
        with SessionLocal() as session:
            job_id = enqueue(session, "backfill", payload, priority=PRIORITY_BACKFILL)
        print(f"enqueued backfill job id={job_id} for {args.username}")

    elif args.cmd == "enqueue-analyze":
        if not args.game_url and not args.pgn_file:
            parser.error("provide --game-url or --pgn-file")
        pgn = None
        if args.pgn_file:
            with open(args.pgn_file, encoding="utf-8") as fh:
                pgn = fh.read()
        payload = {"username": args.username, "pgn": pgn, "game_url": args.game_url}
        with SessionLocal() as session:
            job_id = enqueue(session, "analyze_game", payload, priority=PRIORITY_ONDEMAND)
        print(f"enqueued analyze_game job id={job_id} for {args.username}")


if __name__ == "__main__":
    main()
