#!/usr/bin/env python3
"""Compatibility wrapper for the infra-only autonomous loop."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from cbb.autonomous_loop import main as autonomous_main


def main(argv: Sequence[str] | None = None) -> int:
    """Run the generic supervisor in infra-only compatibility mode."""

    passthrough = list(argv) if argv is not None else sys.argv[1:]
    return autonomous_main(["--lanes", "infra", *passthrough])


if __name__ == "__main__":
    sys.exit(main())
