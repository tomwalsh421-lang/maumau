#!/usr/bin/env python3
"""Run the local autonomous loop supervisor across enabled lanes."""

from __future__ import annotations

import sys

from cbb.autonomous_loop import main

if __name__ == "__main__":
    sys.exit(main())
