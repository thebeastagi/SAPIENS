"""Demonstration adapters; not scientific models.

The synthetic adapters exercise orchestration on deterministic fake data.
The Kepler adapter re-derives a **published** signal from public data as a
validation of the pipeline — it claims no discovery.
"""

from .kepler import KeplerPhotometryAdapter, kepler_holdout_protocol
from .linear import SyntheticLinearAdapter
from .photometry import SyntheticPhotometryAdapter
from .threshold import SyntheticThresholdAdapter

__all__ = [
    "KeplerPhotometryAdapter",
    "SyntheticLinearAdapter",
    "SyntheticPhotometryAdapter",
    "SyntheticThresholdAdapter",
    "kepler_holdout_protocol",
]
