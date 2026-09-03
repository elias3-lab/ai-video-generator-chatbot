"""Automatic provider fallback primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class Attempt:
    provider: str
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class FallbackResult:
    value: T
    provider: str
    attempts: tuple[Attempt, ...]


class AllProvidersFailed(RuntimeError):
    """Raised when every provider in the fallback chain fails."""

    def __init__(self, attempts: Iterable[Attempt]) -> None:
        self.attempts = tuple(attempts)
        summary = "; ".join(
            f"{item.provider}: {item.error or 'failed'}" for item in self.attempts
        )
        super().__init__(f"All providers failed: {summary}")


def run_with_fallback(
    providers: Iterable[str],
    operation: Callable[[str], T],
) -> FallbackResult[T]:
    """Try providers in order and return the first successful result."""
    attempts: list[Attempt] = []
    for provider in dict.fromkeys(p for p in providers if p):
        try:
            value = operation(provider)
            attempts.append(Attempt(provider=provider, success=True))
            return FallbackResult(value=value, provider=provider, attempts=tuple(attempts))
        except Exception as exc:
            attempts.append(Attempt(provider=provider, success=False, error=str(exc)))

    raise AllProvidersFailed(attempts)
