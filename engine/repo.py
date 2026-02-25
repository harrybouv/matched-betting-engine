# engine/repo.py
from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .models import LedgerEntry, OpenBet, Settlement, now_iso


class JsonRepo:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

        self.bankroll_path = os.path.join(self.data_dir, "bankroll.json")
        self.ledger_path = os.path.join(self.data_dir, "ledger.json")
        self.open_path = os.path.join(self.data_dir, "open_bets.json")
        self.settled_path = os.path.join(self.data_dir, "settled_bets.json")

        self._ensure_files()

    def reset_ledger_to_cash(self, cash: float) -> None:
        # wipe ledger and set bankroll to exact value
        self._write_json(self.ledger_path, [])
        self.set_available_cash(float(cash))

    def _ensure_files(self) -> None:
        if not os.path.exists(self.bankroll_path):
            self._write_json(self.bankroll_path, {"available_cash": 0.0})
        if not os.path.exists(self.ledger_path):
            self._write_json(self.ledger_path, [])
        if not os.path.exists(self.open_path):
            self._write_json(self.open_path, [])
        if not os.path.exists(self.settled_path):
            self._write_json(self.settled_path, [])

    def _read_json(self, path: str) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: str, obj: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)

    # ---- Bankroll ----
    def get_available_cash(self) -> float:
        d = self._read_json(self.bankroll_path)
        return float(d.get("available_cash", 0.0))

    def set_available_cash(self, amount: float) -> None:
        self._write_json(self.bankroll_path, {"available_cash": float(amount)})

    # ---- Ledger ----
    def load_ledger(self) -> List[LedgerEntry]:
        raw = self._read_json(self.ledger_path)
        return [LedgerEntry.from_dict(x) for x in raw]

    def append_ledger(self, entry_type: str, amount: float, reference_id: Optional[str] = None, note: Optional[str] = None) -> LedgerEntry:
        ledger = self.load_ledger()
        running = ledger[-1].running_balance if ledger else self.get_available_cash()
        running = float(running + amount)

        e = LedgerEntry(
            timestamp=now_iso(),
            type=entry_type,  # validated by models via convention
            amount=float(amount),
            running_balance=running,
            reference_id=reference_id,
            note=note,
        )
        ledger.append(e)
        self._write_json(self.ledger_path, [x.to_dict() for x in ledger])
        # keep bankroll.json in sync (single source of truth remains ledger + bankroll mirror)
        self.set_available_cash(running)
        return e

    # ---- Open Bets ----
    def load_open_bets(self) -> List[OpenBet]:
        raw = self._read_json(self.open_path)
        return [OpenBet.from_dict(x) for x in raw]

    def save_open_bets(self, bets: List[OpenBet]) -> None:
        self._write_json(self.open_path, [b.to_dict() for b in bets])

    def add_open_bet(self, bet: OpenBet) -> None:
        bets = self.load_open_bets()
        bets.append(bet)
        self.save_open_bets(bets)

    def remove_open_bet(self, bet_id: str) -> OpenBet:
        bets = self.load_open_bets()
        for i, b in enumerate(bets):
            if b.bet_id == bet_id:
                removed = bets.pop(i)
                self.save_open_bets(bets)
                return removed
        raise KeyError(f"Open bet not found: {bet_id}")

    # ---- Settled ----
    def load_settled(self) -> List[Dict[str, Any]]:
        return self._read_json(self.settled_path)

    def append_settlement(self, settlement: Settlement, bet: OpenBet) -> None:
        raw = self._read_json(self.settled_path)
        raw.append({
            "settlement": settlement.to_dict(),
            "bet": bet.to_dict(),
        })
        self._write_json(self.settled_path, raw)