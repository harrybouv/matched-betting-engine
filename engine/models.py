# engine/models.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional


OfferType = Literal["qualifying", "freebet_snr", "freebet_sr"]
BetStatus = Literal["open", "partially_matched", "fully_matched", "settled"]
LedgerType = Literal["deposit", "withdrawal", "lock", "unlock", "profit", "fee"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Offer:
    offer_id: str
    type: OfferType
    stake_cap: float
    min_odds: float = 1.01
    expiry: Optional[str] = None  # ISO string
    stake_returned: bool = False  # mainly for freebet variants

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Offer":
        return Offer(**d)


@dataclass(frozen=True)
class Candidate:
    # Bookie side
    team: str
    bookmaker: str
    offer_type: OfferType
    back_odds: float
    back_stake: float
    commission: float  # exchange commission (0.02 = 2%)

    # Exchange metadata (optional until Betfair integration is on)
    market_id: Optional[str] = None
    selection_id: Optional[int] = None
    event_name: Optional[str] = None
    event_time: Optional[str] = None  # ISO string

    # Exchange quote
    lay_odds: float = 0.0
    lay_size: float = 0.0  # available money at best lay

    # Derived hedge
    lay_stake: float = 0.0
    lay_liability: float = 0.0
    guaranteed_profit: float = 0.0
    roi: float = 0.0

    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            object.__setattr__(self, "created_at", now_iso())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Candidate":
        return Candidate(**d)


@dataclass
class OpenBet:
    bet_id: str
    candidate: Candidate
    status: BetStatus = "open"

    expected_lay_odds: float = 0.0
    matched_lay_stake: float = 0.0
    avg_lay_odds: float = 0.0

    settled_at: Optional[str] = None

    def required_capital(self) -> float:
        if self.candidate.offer_type == "qualifying":
            return float(self.candidate.back_stake + self.candidate.lay_liability)
        else:
            return float(self.candidate.lay_liability)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["candidate"] = self.candidate.to_dict()
        return d

    def remaining_lay_stake(self) -> float:
        return max(0.0, float(self.candidate.lay_stake) - float(self.matched_lay_stake))


    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "OpenBet":
        cand = Candidate.from_dict(d["candidate"])
        d2 = dict(d)
        d2["candidate"] = cand
        return OpenBet(**d2)


@dataclass(frozen=True)
class Settlement:
    bet_id: str
    result: Literal["win", "lose", "void"]
    actual_bookie_payout: float
    actual_exchange_pnl: float
    realised_profit: float
    settled_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Settlement":
        return Settlement(**d)

    def remaining_lay_stake(self) -> float:
        return max(0.0, self.candidate.lay_stake - self.matched_lay_stake)


@dataclass
class LedgerEntry:
    timestamp: str
    type: LedgerType
    amount: float
    running_balance: float
    reference_id: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "LedgerEntry":
        return LedgerEntry(**d)