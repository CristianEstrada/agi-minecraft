"""Shared setup from environment variables (.env)."""

import os

from dotenv import load_dotenv

from .rcon import RconClient
from .tools import ToolRunner

DEFAULT_BLOCKED = "stop,op,deop,ban,ban-ip,pardon,whitelist,save-off,kill,easy_npc test"


def load() -> dict:
    load_dotenv()
    return {
        "model": os.getenv("MODEL", "anthropic/claude-sonnet-5-5"),
        "max_steps": int(os.getenv("MAX_STEPS", "12")),
        "log_path": os.getenv("LOG_PATH", "../server/logs/latest.log"),
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
    return ToolRunner(rcon, os.getenv("BLOCKED_COMMANDS", DEFAULT_BLOCKED).split(","))
