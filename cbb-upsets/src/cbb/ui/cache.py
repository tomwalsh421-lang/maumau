"""Compatibility alias for the dashboard backend cache module."""

from __future__ import annotations

import sys

import cbb.dashboard.cache as _cache

sys.modules[__name__] = _cache
