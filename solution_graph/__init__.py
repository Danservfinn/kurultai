"""Offline, read-only Solution Graph kernel for Kurultai."""

from .resolver import resolve_objective, simulate_plan

__all__ = ["resolve_objective", "simulate_plan"]
__version__ = "0.1.0"
