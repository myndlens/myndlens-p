"""Prompt System — Core Types.

All enums, dataclasses, and models for the dynamic prompt system.
Prompts are programs, not strings.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid


# ---- Enums ----

class PromptPurpose(str, Enum):
    """Every LLM call MUST declare a purpose. No default."""
    THOUGHT_TO_INTENT = "THOUGHT_TO_INTENT"
    DIMENSIONS_EXTRACT = "DIMENSIONS_EXTRACT"
    PLAN = "PLAN"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    SAFETY_GATE = "SAFETY_GATE"
    SUMMARIZE = "SUMMARIZE"
    SUBAGENT_TASK = "SUBAGENT_TASK"
    MICRO_QUESTION = "MICRO_QUESTION"


class PromptMode(str, Enum):
    """Affects verbosity, refusal style, explanation depth."""
    INTERACTIVE = "INTERACTIVE"
    BATCH = "BATCH"
    SILENT = "SILENT"
    AUDIT = "AUDIT"


class SectionID(str, Enum):
    """Canonical section identifiers. No others permitted without ADR."""
    IDENTITY_ROLE = "IDENTITY_ROLE"
    PURPOSE_CONTRACT = "PURPOSE_CONTRACT"
    OUTPUT_SCHEMA = "OUTPUT_SCHEMA"
    TOOLING = "TOOLING"
    WORKSPACE_BOOTSTRAP = "WORKSPACE_BOOTSTRAP"
    SKILLS_INDEX = "SKILLS_INDEX"
    RUNTIME_CAPABILITIES = "RUNTIME_CAPABILITIES"
    SAFETY_GUARDRAILS = "SAFETY_GUARDRAILS"
    TASK_CONTEXT = "TASK_CONTEXT"
    MEMORY_RECALL_SNIPPETS = "MEMORY_RECALL_SNIPPETS"
    LEARNED_EXAMPLES = "LEARNED_EXAMPLES"
    DIMENSIONS_INJECTED = "DIMENSIONS_INJECTED"
    CONFLICTS_SUMMARY = "CONFLICTS_SUMMARY"


class CacheClass(str, Enum):
    """Determines hashing and caching behavior."""
    STABLE = "STABLE"          # identity, purpose, schema, safety
    SEMISTABLE = "SEMISTABLE"  # tools, skills, workspace
    VOLATILE = "VOLATILE"      # task context, memory, dimensions


# ---- Section Output ----

@dataclass
class SectionOutput:
    """Return type from every section generator."""
    section_id: SectionID
    content: Union[str, List[Dict[str, str]]]  # string or role-tagged messages
    priority: int  # ordering (lower = first)
    cache_class: CacheClass
    tokens_est: int
    included: bool
    gating_reason: Optional[str] = None


# ---- Prompt Context ----

@dataclass
class PromptContext:
    """All inputs needed to build a prompt. Passed to orchestrator."""
    purpose: PromptPurpose
    mode: PromptMode
    session_id: str
    user_id: str
    env: str = "dev"

    # Task-specific context (volatile)
    transcript: Optional[str] = None
    task_description: Optional[str] = None
    dimensions: Optional[Dict[str, Any]] = None
    conflicts: Optional[List[str]] = None

    # Tool context
    available_tools: List[str] = field(default_factory=list)

    # Memory context
    memory_snippets: Optional[List[Dict[str, Any]]] = None

    # Per-user optimization adjustments (from user_profiles)
    user_adjustments: Optional[Dict[str, Any]] = None


# ---- Prompt Artifact ----

@dataclass
class PromptArtifact:
    """The assembled prompt ready for LLM consumption."""
    prompt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    purpose: PromptPurpose = PromptPurpose.THOUGHT_TO_INTENT
    mode: PromptMode = PromptMode.INTERACTIVE
    messages: List[Dict[str, str]] = field(default_factory=list)  # [{role, content}]
    sections_included: List[SectionID] = field(default_factory=list)
    sections_excluded: List[SectionID] = field(default_factory=list)
    stable_hash: str = ""
    volatile_hash: str = ""
    total_tokens_est: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---- Prompt Report ----

@dataclass
class SectionStatus:
    """Status of a section in the prompt report."""
    section_id: SectionID
    included: bool
    gating_reason: Optional[str] = None
    cache_class: Optional[CacheClass] = None
    tokens_est: int = 0
    priority: int = 0


@dataclass
class PromptReport:
    """Immutable report emitted per LLM call. Mandatory."""
    prompt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    purpose: PromptPurpose = PromptPurpose.THOUGHT_TO_INTENT
    mode: PromptMode = PromptMode.INTERACTIVE
    sections: List[SectionStatus] = field(default_factory=list)
    token_estimates: Dict[str, int] = field(default_factory=dict)
    budget_used: int = 0
    allowed_tools: List[str] = field(default_factory=list)
    stable_hash: str = ""
    volatile_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_doc(self) -> dict:
        """Serialize for MongoDB persistence."""
        return {
            "prompt_id": self.prompt_id,
            "purpose": self.purpose.value,
            "mode": self.mode.value,
            "sections": [
                {
                    "section_id": s.section_id.value,
                    "included": s.included,
                    "gating_reason": s.gating_reason,
                    "cache_class": s.cache_class.value if s.cache_class else None,
                    "tokens_est": s.tokens_est,
                }
                for s in self.sections
            ],
            "token_estimates": self.token_estimates,
            "budget_used": self.budget_used,
            "allowed_tools": self.allowed_tools,
            "stable_hash": self.stable_hash,
            "volatile_hash": self.volatile_hash,
            "created_at": self.created_at,
        }
