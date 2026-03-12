"""Compatibility alias for the dashboard backend service module."""

from __future__ import annotations

import sys

import cbb.dashboard.service as _service

sys.modules[__name__] = _service
