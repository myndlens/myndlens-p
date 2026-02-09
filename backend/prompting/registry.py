"""Section Registry — maps SectionID → generator.

Generators MUST be pure functions: (PromptContext) → SectionOutput.
"""
import logging
from typing import Callable, Dict

from prompting.types import PromptContext, SectionID, SectionOutput

logger = logging.getLogger(__name__)

# Type alias for section generators
SectionGenerator = Callable[[PromptContext], SectionOutput]


class SectionRegistry:
    """Maps SectionID to generator functions."""

    def __init__(self):
        self._generators: Dict[SectionID, SectionGenerator] = {}

    def register(self, section_id: SectionID, generator: SectionGenerator) -> None:
        """Register a generator for a section."""
        self._generators[section_id] = generator
        logger.debug("Section registered: %s", section_id.value)

    def has(self, section_id: SectionID) -> bool:
        return section_id in self._generators

    def generate(self, section_id: SectionID, ctx: PromptContext) -> SectionOutput:
        """Invoke the generator for a section. Raises if not registered."""
        gen = self._generators.get(section_id)
        if gen is None:
            raise KeyError(f"No generator registered for section: {section_id.value}")
        return gen(ctx)

    def registered_sections(self) -> list:
        return list(self._generators.keys())


def build_default_registry() -> SectionRegistry:
    """Build the standard section registry with all implemented generators."""
    from prompting.sections.standard import (
        identity_role,
        purpose_contract,
        output_schema,
        safety_guardrails,
        task_context,
        runtime_capabilities,
        tooling,
    )

    registry = SectionRegistry()
    registry.register(SectionID.IDENTITY_ROLE, identity_role.generate)
    registry.register(SectionID.PURPOSE_CONTRACT, purpose_contract.generate)
    registry.register(SectionID.OUTPUT_SCHEMA, output_schema.generate)
    registry.register(SectionID.SAFETY_GUARDRAILS, safety_guardrails.generate)
    registry.register(SectionID.TASK_CONTEXT, task_context.generate)
    registry.register(SectionID.RUNTIME_CAPABILITIES, runtime_capabilities.generate)
    registry.register(SectionID.TOOLING, tooling.generate)

    logger.info(
        "SectionRegistry built with %d sections: %s",
        len(registry.registered_sections()),
        [s.value for s in registry.registered_sections()],
    )
    return registry
