"""Watch a directory for new screenshots and run the pipeline on each one.

Usage:
    python -m pipeline.watch samples/         # poll samples/ every 2s
    python -m pipeline.watch samples/ --interval 5
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from .run import main as run_main

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _snapshot(folder: Path) -> set[Path]:
    return {p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in EXTS}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Watch folder; process new images.")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--out-dir", type=Path, default=Path("output"))
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    args = ap.parse_args(argv)

    args.folder.mkdir(parents=True, exist_ok=True)
    seen = _snapshot(args.folder)
    print(f"watching {args.folder} (every {args.interval}s); {len(seen)} pre-existing files ignored")

    while True:
        try:
            time.sleep(args.interval)
            current = _snapshot(args.folder)
            new = sorted(current - seen)
            for path in new:
                print(f"new image: {path}")
                run_main([str(path), "--out-dir", str(args.out_dir),
                          "--data-dir", str(args.data_dir)])
            seen = current
        except KeyboardInterrupt:
            print("\nstopped")
            return 0
        except Exception as e:  # keep the loop alive on per-file errors
            print(f"error: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
