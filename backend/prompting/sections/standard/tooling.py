"""TOOLING section generator — tools available to LLM.

Tools MUST be gated via PolicyEngine.
This section provides the LLM with capabilities and syntax.
"""
import logging
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass

logger = logging.getLogger(__name__)


def generate(ctx: PromptContext) -> SectionOutput:
    """Generate TOOLING section content."""
    # For now, basic tooling section - in future this would list actual tools
    content = """## TOOLS AVAILABLE

You have access to the following tools when explicitly requested:
- File operations (read, write, delete) with safety checks
- Web search for information gathering
- Data processing and transformation
- Communication tools (send messages, make calls)

All tool usage MUST follow safety protocols and user consent.
Destructive operations require explicit confirmation.
"""
    
    return SectionOutput(
        section_id=SectionID.TOOLING,
        content=content,
        priority=40,  # After core sections, before task context
        cache_class=CacheClass.SEMISTABLE,  # tools change occasionally
        tokens_est=100,
        included=True,
    )