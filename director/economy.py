"""Virtual-coin economy on a scoreboard objective, with hard limits enforced in
code (not in the prompt) and a JSONL ledger of every movement."""

import json
import os
import re
import time
from datetime import date

from .rcon import RconClient

PLAYER = re.compile(r"^[A-Za-z0-9_]{1,16}$")
ITEM = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
SCORE = re.compile(r"has (-?\d+) \[")


class EconomyError(Exception):
    pass


class Economy:
    def __init__(self, rcon: RconClient, objective: str, ledger_path: str, max_tx: int, daily_payout: int):
        self.rcon = rcon
        self.objective = objective
        self.ledger_path = ledger_path
        self.max_tx = max_tx
        self.daily_payout = daily_payout

    def setup(self) -> None:
        # Fails harmlessly with "An objective already exists" after the first run.
        self.rcon.command(f'scoreboard objectives add {self.objective} dummy "Monedas"')

    def balance(self, player: str) -> int:
        self._check_player(player)
        out = self.rcon.command(f"scoreboard players get {player} {self.objective}")
        m = SCORE.search(out)
        return int(m.group(1)) if m else 0

    def pay(self, player: str, amount: int, reason: str) -> int:
        """Director gives coins to a player (rewards, sales to the director)."""
        amount = self._check_amount(amount)
        self._check_player(player)
        paid_today = self._paid_today(player)
        if paid_today + amount > self.daily_payout:
            raise EconomyError(
                f"daily payout limit: {player} already received {paid_today} today (max {self.daily_payout})"
            )
        self.rcon.command(f"scoreboard players add {player} {self.objective} {amount}")
        self._record("pay", player, amount, reason)
        return self.balance(player)

    def charge(self, player: str, amount: int, reason: str) -> int:
        """Take coins from a player. Fails if they can't afford it."""
        amount = self._check_amount(amount)
        current = self.balance(player)
        if current < amount:
            raise EconomyError(f"{player} has {current} coins, needs {amount}")
        self.rcon.command(f"scoreboard players remove {player} {self.objective} {amount}")
        self._record("charge", player, amount, reason)
        return current - amount

    def sell_item(self, player: str, item: str, count: int, price: int) -> str:
        """Charge the player and give them the item; refund if the give fails."""
        if not ITEM.match(item):
            raise EconomyError(f"invalid item id '{item}', use namespace:id like minecraft:bread")
        if not 1 <= int(count) <= 64:
            raise EconomyError("count must be between 1 and 64")
        left = self.charge(player, price, f"buy {count} {item}")
        out = self.rcon.command(f"give {player} {item} {int(count)}")
        if "gave" not in out.lower():
            self.rcon.command(f"scoreboard players add {player} {self.objective} {int(price)}")
            self._record("refund", player, int(price), f"failed give: {out.strip()[:80]}")
            raise EconomyError(f"give failed, refunded: {out.strip()}")
        return f"{player} bought {count} {item} for {price}; balance {left}"

    def report(self, last: int = 10) -> dict:
        entries = self._entries()
        paid = sum(e["amount"] for e in entries if e["kind"] == "pay")
        charged = sum(e["amount"] for e in entries if e["kind"] == "charge")
        refunds = sum(e["amount"] for e in entries if e["kind"] == "refund")
        return {
            "coins_issued": paid + refunds,
            "coins_collected": charged,
            "net_in_circulation": paid + refunds - charged,
            "recent": entries[-last:],
        }

    def _check_player(self, player: str) -> None:
        if not PLAYER.match(player or ""):
            raise EconomyError(f"invalid player name '{player}' (selectors like @a are not allowed)")

    def _check_amount(self, amount) -> int:
        amount = int(amount)
        if not 1 <= amount <= self.max_tx:
            raise EconomyError(f"amount must be between 1 and {self.max_tx}")
        return amount

    def _paid_today(self, player: str) -> int:
        today = date.today().isoformat()
        return sum(
            e["amount"]
            for e in self._entries()
            if e["kind"] == "pay" and e["player"] == player and e["date"] == today
        )

    def _record(self, kind: str, player: str, amount: int, reason: str) -> None:
        os.makedirs(os.path.dirname(self.ledger_path) or ".", exist_ok=True)
        entry = {
            "ts": int(time.time()),
            "date": date.today().isoformat(),
            "kind": kind,
            "player": player,
            "amount": amount,
            "reason": reason,
        }
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _entries(self) -> list[dict]:
        if not os.path.exists(self.ledger_path):
            return []
        with open(self.ledger_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
