from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.intelligence import IntelligenceExecution
from app.schemas.orchestration import OrchestrationAnalyticalLevel, OrchestrationCreate


@dataclass(frozen=True)
class EngineCapability:
    engine_code: str
    engine_name: str
    engine_version: str
    analytical_level: OrchestrationAnalyticalLevel
    capability_code: str
    input_contract_version: str = "1.0"
    output_contract_version: str = "1.0"
    is_available: bool = True
    supports_sync: bool = True
    supports_async: bool = False
    implementation_reference: str = ""


class EngineAdapter(Protocol):
    capability: EngineCapability

    def can_execute(self, definition_level: OrchestrationAnalyticalLevel) -> bool: ...

    def execute(
        self,
        db: Session,
        organization_id: UUID,
        payload: OrchestrationCreate,
        actor_user_id: UUID,
        execution_idempotency_key: str,
    ) -> IntelligenceExecution: ...


class EngineRegistryError(ValueError):
    pass


class EngineRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, EngineAdapter] = {}

    def register(self, adapter: EngineAdapter) -> None:
        code = adapter.capability.engine_code
        if code in self._adapters:
            raise EngineRegistryError(f"Engine {code} is already registered")
        self._adapters[code] = adapter

    def get(self, engine_code: str) -> EngineAdapter:
        try:
            return self._adapters[engine_code]
        except KeyError as exc:
            raise EngineRegistryError(f"Engine {engine_code} is not registered") from exc

    def for_level(self, level: OrchestrationAnalyticalLevel) -> EngineAdapter | None:
        eligible = [
            adapter
            for adapter in self._adapters.values()
            if adapter.capability.analytical_level == level
            and adapter.capability.is_available
            and adapter.can_execute(level)
        ]
        return (
            sorted(eligible, key=lambda item: item.capability.engine_code)[0] if eligible else None
        )

    def list(self) -> list[EngineAdapter]:
        return [self._adapters[code] for code in sorted(self._adapters)]
