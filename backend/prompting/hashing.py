"""Prompt Hashing — deterministic hashing for cache stability.

Stable segments MUST hash identically across calls given same config.
No dynamic timestamps in stable sections.
"""
import hashlib
import json
from typing import List

from prompting.types import SectionOutput, CacheClass


def _normalize_content(content) -> str:
    """Normalize section content to a stable string for hashing."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return json.dumps(content, sort_keys=True, ensure_ascii=True)
    return str(content)


def compute_hash(sections: List[SectionOutput], target_class: CacheClass) -> str:
    """Compute SHA-256 hash of sections matching the target cache class."""
    parts = []
    for s in sorted(sections, key=lambda x: x.priority):
        if s.included and s.cache_class == target_class:
            parts.append(f"{s.section_id.value}:{_normalize_content(s.content)}")
    if not parts:
        return "empty"
    combined = "\n---\n".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def compute_stable_hash(sections: List[SectionOutput]) -> str:
    """Hash only STABLE sections."""
    return compute_hash(sections, CacheClass.STABLE)


def compute_volatile_hash(sections: List[SectionOutput]) -> str:
    """Hash only VOLATILE sections."""
    return compute_hash(sections, CacheClass.VOLATILE)
