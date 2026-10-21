"""Tools the model can call. Defined in the OpenAI tool format, which LiteLLM
translates for every provider (Anthropic, Gemini, Ollama, ...)."""

import json

from .rcon import RconClient

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a Minecraft server command through RCON and return its output. "
                "Write the command without the leading slash, e.g. 'list' or 'help easy_npc'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command without the leading slash."}
                },
                "required": ["command"],
            },
        },
    },
]


class ToolRunner:
    def __init__(self, rcon: RconClient, blocked: list[str]):
        self.rcon = rcon
        self.blocked = [b.strip().lower() for b in blocked if b.strip()]

    def is_blocked(self, command: str) -> bool:
        """An entry blocks every command starting with it ("stop", "easy_npc test").
        Commands nested in `execute ... run <cmd>` are checked too."""
        words = command.strip().lstrip("/").lower().split()
        candidates = [words] + [words[i + 1 :] for i, w in enumerate(words) if w == "run"]
        for cmd in candidates:
            for entry in self.blocked:
                prefix = entry.split()
                if cmd[: len(prefix)] == prefix:
                    return True
        return False

    def run(self, name: str, arguments: str) -> str:
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return "error: arguments are not valid JSON"
        if name != "run_command":
            return f"error: unknown tool {name}"
        command = str(args.get("command", "")).strip().lstrip("/")
        if not command:
            return "error: empty command"
        if self.is_blocked(command):
            return f"error: command '{command}' is blocked by BLOCKED_COMMANDS"
        output = self.rcon.command(command)
        return output or "(no output)"
