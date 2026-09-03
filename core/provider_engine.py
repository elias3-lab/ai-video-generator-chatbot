"""Provider-agnostic execution engine with deterministic fallback handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional

from .provider_fallback import FallbackResult, run_with_fallback


@dataclass(frozen=True)
class ProviderOperationResult:
    """Normalized result returned by a provider operation."""

    value: Any
    provider: str
    attempts: tuple


class ProviderEngine:
    """Execute a scene operation through an ordered provider chain.

    Provider callables are injected by the application, keeping API credentials
    and SDK-specific code outside the orchestration layer.
    """

    def __init__(self, operations: Optional[Mapping[str, Callable[..., Any]]] = None) -> None:
        self.operations = dict(operations or {})

    def register(self, provider: str, operation: Callable[..., Any]) -> None:
        if not provider:
            raise ValueError("Provider name is required")
        self.operations[provider] = operation

    def available(self, providers: Iterable[str]) -> tuple[str, ...]:
        return tuple(provider for provider in dict.fromkeys(providers) if provider in self.operations)

    def execute(
        self,
        providers: Iterable[str],
        **kwargs: Any,
    ) -> ProviderOperationResult:
        candidates = self.available(providers)
        if not candidates:
            raise RuntimeError("No registered providers are available for this operation")

        result: FallbackResult[Any] = run_with_fallback(
            candidates,
            lambda provider: self.operations[provider](**kwargs),
        )
        return ProviderOperationResult(
            value=result.value,
            provider=result.provider,
            attempts=result.attempts,
        )
