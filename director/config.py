"""Shared setup from environment variables (.env)."""

import os

from dotenv import load_dotenv

from .economy import Economy
from .rcon import RconClient
from .tools import ToolRunner

DEFAULT_BLOCKED = "stop,op,deop,ban,ban-ip,pardon,whitelist,save-off,kill,easy_npc test"


def load() -> dict:
    load_dotenv()
    return {
        "model": os.getenv("MODEL", "anthropic/claude-sonnet-5-5"),
        "max_steps": int(os.getenv("MAX_STEPS", "12")),
        "log_path": os.getenv("LOG_PATH", "../server/logs/latest.log"),
        "npc_file": os.getenv("NPC_FILE", "npcs.yaml"),
        "npc_names": [n.strip() for n in os.getenv("NPC_NAMES", "").split(",") if n.strip()],
        "greet_joins": os.getenv("GREET_JOINS", "false").lower() == "true",
    }


def connect_runner() -> ToolRunner:
    load_dotenv()
    rcon = RconClient(
        os.getenv("RCON_HOST", "localhost"),
        int(os.getenv("RCON_PORT", "25575")),
        os.environ["RCON_PASSWORD"],
    )
    rcon.connect()
    blocked = os.getenv("BLOCKED_COMMANDS", DEFAULT_BLOCKED).split(",")
    economy = None
    if os.getenv("ECONOMY_ENABLED", "false").lower() == "true":
        # Coins may only move through the economy tools, which enforce limits.
        blocked.append("scoreboard players")
        economy = Economy(
            rcon,
            objective=os.getenv("ECONOMY_OBJECTIVE", "monedas"),
            ledger_path=os.getenv("ECONOMY_LEDGER", "data/ledger.jsonl"),
            max_tx=int(os.getenv("ECONOMY_MAX_TX", "500")),
            daily_payout=int(os.getenv("ECONOMY_DAILY_PAYOUT", "2000")),
        )
        economy.setup()
    return ToolRunner(rcon, blocked, economy)
