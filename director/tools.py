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
    {
        "type": "function",
        "function": {
            "name": "npc_say",
            "description": (
                "Make an NPC speak: shows '<npc> text' in the chat of players near that NPC. "
                "The NPC is found by its exact name (as set with 'easy_npc name set')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "npc": {"type": "string", "description": "Exact name of the NPC, e.g. 'Bob'."},
                    "text": {"type": "string", "description": "What the NPC says. One or two short sentences."},
                    "radius": {"type": "integer", "description": "Blocks around the NPC that hear it. Default 16."},
                },
                "required": ["npc", "text"],
            },
        },
    },
]


def _selector_name(name: str) -> str:
    """Quote a name for an entity selector so names with spaces work."""
    return json.dumps(name)


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
        if name == "run_command":
            return self.run_command(str(args.get("command", "")))
        if name == "npc_say":
            return self.npc_say(str(args.get("npc", "")), str(args.get("text", "")), args.get("radius"))
        return f"error: unknown tool {name}"

    def run_command(self, command: str) -> str:
        command = command.strip().lstrip("/")
        if not command:
            return "error: empty command"
        if self.is_blocked(command):
            return f"error: command '{command}' is blocked by BLOCKED_COMMANDS"
        output = self.rcon.command(command)
        return output or "(no output)"

    def npc_say(self, npc: str, text: str, radius=None) -> str:
        npc, text = npc.strip(), " ".join(text.split())
        if not npc or not text:
            return "error: npc and text are required"
        radius = max(1, min(int(radius or 16), 128))
        target = f"@e[type=!player,name={_selector_name(npc)},limit=1]"
        found = self.rcon.command(f"execute if entity {target}")
        if "passed" not in found.lower():
            return f"error: no NPC named '{npc}' is loaded (is a player nearby?)"
        message = json.dumps({"text": f"<{npc}> {text}", "color": "yellow"})
        self.rcon.command(f"execute at {target} run tellraw @a[distance=..{radius}] {message}")
        return f"{npc} said: {text}"
