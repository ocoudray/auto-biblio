"""Weekly LLM budget: reserve an estimate before each call, settle the real cost after."""

import math
from itertools import count
from typing import Literal

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.errors import BudgetExhaustedError
from auto_biblio.domain.triage import LLMUsage
from auto_biblio.repo_config.llm import CHARS_PER_TOKEN, Budget, ModelSpec

_USD: Literal["usd"] = "usd"
_TOKENS: Literal["tokens"] = "tokens"


class Reservation(BaseModel):
    """Budget held for a call in progress."""

    model_config = ConfigDict(frozen=True)

    id: int
    usd: float
    tokens: int


class BudgetLedger:
    """Tracks spending against the two weekly caps: dollars and tokens.

    Tokens count for every model (free quotas are finite too); dollars only for paid ones.
    """

    def __init__(
        self,
        limit: Budget,
        spent_usd: float = 0.0,
        spent_tokens: int = 0,
        *,
        chars_per_token: float = CHARS_PER_TOKEN,
        safety_margin: float = 1.2,
    ) -> None:
        """Start a ledger, possibly from what was already spent this week.

        Args:
            limit: The weekly caps.
            spent_usd: Dollars already spent this week.
            spent_tokens: Tokens already consumed this week.
            chars_per_token: Rough size of a token, used to estimate prompts.
            safety_margin: Factor applied to the estimated prompt tokens.
        """
        self._limit = limit
        self._spent_usd = spent_usd
        self._spent_tokens = spent_tokens
        self._chars_per_token = chars_per_token
        self._safety_margin = safety_margin
        self._held: dict[int, Reservation] = {}
        self._ids = count()

    @property
    def remaining_usd(self) -> float:
        """Dollars still available, reservations deducted."""
        held = sum(r.usd for r in self._held.values())
        return self._limit.usd - self._spent_usd - held

    @property
    def remaining_tokens(self) -> int:
        """Tokens still available, reservations deducted."""
        held = sum(r.tokens for r in self._held.values())
        return self._limit.tokens - self._spent_tokens - held

    def estimate(self, spec: ModelSpec, prompt_chars: int) -> tuple[float, int]:
        """Estimate the worst-case cost of a call.

        Args:
            spec: The model called.
            prompt_chars: Length of the whole prompt.

        Returns:
            Dollars and tokens: estimated prompt tokens plus the maximum output.
        """
        input_tokens = math.ceil(prompt_chars / self._chars_per_token * self._safety_margin)
        tokens = input_tokens + spec.max_output_tokens
        return spec.cost_usd(input_tokens, spec.max_output_tokens), tokens

    def reserve(self, usd: float, tokens: int) -> Reservation:
        """Hold budget for a call.

        Args:
            usd: Estimated dollars.
            tokens: Estimated tokens.

        Returns:
            The reservation, to settle or release afterwards.

        Raises:
            BudgetExhaustedError: If either cap would be exceeded.
        """
        if usd > self.remaining_usd:
            raise BudgetExhaustedError(_USD, usd, self.remaining_usd)
        if tokens > self.remaining_tokens:
            raise BudgetExhaustedError(_TOKENS, tokens, self.remaining_tokens)
        reservation = Reservation(id=next(self._ids), usd=usd, tokens=tokens)
        self._held[reservation.id] = reservation
        return reservation

    def settle(self, reservation: Reservation, usage: LLMUsage) -> None:
        """Replace a reservation by what the call really consumed.

        Args:
            reservation: The reservation of the call.
            usage: The real consumption.
        """
        self._held.pop(reservation.id, None)
        self._spent_usd += usage.cost_usd
        self._spent_tokens += usage.input_tokens + usage.output_tokens

    def release(self, reservation: Reservation) -> None:
        """Drop a reservation whose call failed without consuming.

        Args:
            reservation: The reservation of the call.
        """
        self._held.pop(reservation.id, None)
