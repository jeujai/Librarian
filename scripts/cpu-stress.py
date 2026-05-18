#!/usr/bin/env python3
"""Burn ~98% CPU for a configurable duration (default 2 minutes)."""
import argparse
import multiprocessing
import time


def burn(duration: float):
    """Spin until duration elapses."""
    end = time.time() + duration
    while time.time() < end:
        pass


def main():
    parser = argparse.ArgumentParser(description="CPU stress test")
    parser.add_argument("--duration", type=float, default=120, help="Seconds to run (default: 120)")
    parser.add_argument("--cores", type=int, default=None, help="Cores to use (default: all)")
    args = parser.parse_args()

    cores = args.cores or multiprocessing.cpu_count()
    # Leave one core mostly idle to hit ~98% rather than 100%
    workers = max(1, cores - 1) if args.cores is None else cores

    print(f"Burning {workers}/{cores} cores for {args.duration}s...")
    procs = [multiprocessing.Process(target=burn, args=(args.duration,)) for _ in range(workers)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    print("Done.")


if __name__ == "__main__":
    main()
