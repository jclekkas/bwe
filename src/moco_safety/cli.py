from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load_categories, load_settings
from .digest import builder, sender
from .fetchers.crime import CrimeFetcher
from .fetchers.dispatched import DispatchedFetcher
from .fetchers.fire_ems import FireEmsFetcher
from .fetchers.sex_offenders import SexOffenderFetcher
from .snapshot import (
    Snapshot,
    apply_offender_fallback,
    build_snapshot,
    load_previous,
    prune_history,
    save,
)

ALL_FETCHERS = [CrimeFetcher(), DispatchedFetcher(), FireEmsFetcher(), SexOffenderFetcher()]


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def cmd_fetch(args: argparse.Namespace) -> int:
    settings = load_settings()
    cat_map = load_categories()
    since = _since(args.days)
    previous = load_previous()

    results = {}
    for f in ALL_FETCHERS:
        print(f"[fetch] {f.name} ...", file=sys.stderr)
        results[f.name] = f.fetch(settings, since)
        print(f"  status={results[f.name].status} note={results[f.name].note}", file=sys.stderr)

    snap = build_snapshot(results, settings, cat_map)
    apply_offender_fallback(snap, previous, results["offenders"].status)
    save(snap)
    prune_history(settings.history_days)
    print(f"snapshot written: {len(snap.incidents)} incidents, {len(snap.offenders)} offenders", file=sys.stderr)
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    settings = load_settings()
    snap_path = Path(args.snapshot) if args.snapshot else None
    if snap_path and snap_path.exists():
        snapshot = json.loads(snap_path.read_text())
    else:
        snapshot = load_previous()
        if snapshot is None:
            print("no snapshot found; run `fetch` first", file=sys.stderr)
            return 2

    previous = None
    if args.previous:
        prev_path = Path(args.previous)
        if prev_path.exists():
            previous = json.loads(prev_path.read_text())

    subject, html, text = builder.render(snapshot, settings, previous)

    if args.out:
        out = Path(args.out)
        out.write_text(html)
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)

    if args.send:
        sender.send(subject, html, text)
        print("sent", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="moco_safety")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="Fetch all sources and write snapshot")
    pf.add_argument("--days", type=int, default=7, help="lookback window in days")
    pf.set_defaults(func=cmd_fetch)

    pd = sub.add_parser("digest", help="Build and optionally send the digest")
    pd.add_argument("--send", action="store_true", help="actually send via SMTP")
    pd.add_argument("--out", type=str, help="write rendered HTML to this path")
    pd.add_argument("--snapshot", type=str, help="path to snapshot.json (default: data/snapshot.json)")
    pd.add_argument("--previous", type=str, help="path to previous snapshot for offender diff")
    pd.set_defaults(func=cmd_digest)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
