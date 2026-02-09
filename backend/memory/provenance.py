"""Provenance model — tracks source authority of memory nodes.

EXPLICIT: Directly stated by user.
OBSERVED: Inferred / low confidence.

Tier Downgrade Rule: If ANY execution-critical dimension depends
on an OBSERVED node → action auto-downgraded to Tier 2.
"""
from enum import Enum


class Provenance(str, Enum):
    EXPLICIT = "EXPLICIT"
    OBSERVED = "OBSERVED"


def requires_tier_downgrade(provenance_flags: dict) -> bool:
    """Check if any node has OBSERVED provenance → requires Tier 2."""
    for node_id, prov in provenance_flags.items():
        if prov == Provenance.OBSERVED.value:
            return True
    return False
