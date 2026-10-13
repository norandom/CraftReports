"""Canonical check modes; later foundation tasks supply their implementations."""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CraftReport verification.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--fast", action="store_true", help="Run engineering and focused tests")
    modes.add_argument("--integration", action="store_true", help="Run installed-wheel conformance")
    args = parser.parse_args()
    mode = "fast" if args.fast else "integration"
    prerequisite = "foundation task 1.4" if args.fast else "conformance harness task 8.1"
    print(f"{mode} check unavailable: {prerequisite} is not implemented.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
