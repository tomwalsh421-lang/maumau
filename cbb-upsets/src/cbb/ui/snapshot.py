"""Compatibility alias for the dashboard backend snapshot module."""

from __future__ import annotations

import sys

import cbb.dashboard.snapshot as _snapshot

sys.modules[__name__] = _snapshot
