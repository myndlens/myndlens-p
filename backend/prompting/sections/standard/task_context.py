"""TASK_CONTEXT section — volatile.

The per-call context: transcript, task description, etc.
"""
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass


def generate(ctx: PromptContext) -> SectionOutput:
    parts = []

    if ctx.transcript:
        parts.append(f"User transcript:\n\"{ctx.transcript}\"")

    if ctx.task_description:
        parts.append(f"Task: {ctx.task_description}")

    if ctx.dimensions:
        import json
        parts.append(f"Current dimensions:\n{json.dumps(ctx.dimensions, indent=2)}")

    content = "\n\n".join(parts) if parts else "No task context provided."

    return SectionOutput(
        section_id=SectionID.TASK_CONTEXT,
        content=content,
        priority=9,
        cache_class=CacheClass.VOLATILE,
        tokens_est=len(content) // 4,
        included=True,
    )
