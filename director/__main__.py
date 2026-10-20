"""CLI: `python -m director` (interactive) or `python -m director "orden"`."""

import os
import sys

from dotenv import load_dotenv

from .agent import Agent
from .rcon import RconClient
from .tools import ToolRunner


def main() -> None:
    load_dotenv()
    rcon = RconClient(
        os.getenv("RCON_HOST", "localhost"),
        int(os.getenv("RCON_PORT", "25575")),
        os.environ["RCON_PASSWORD"],
    )
    rcon.connect()
    blocked = os.getenv("BLOCKED_COMMANDS", "stop,op,deop,ban,ban-ip,pardon,whitelist,save-off").split(",")
    agent = Agent(
        model=os.getenv("MODEL", "anthropic/claude-sonnet-5-5"),
        tools=ToolRunner(rcon, blocked),
        max_steps=int(os.getenv("MAX_STEPS", "12")),
    )

    def show(args, result):
        print(f"  > {args}\n  < {result}")

    if len(sys.argv) > 1:
        print(agent.ask(" ".join(sys.argv[1:]), on_tool=show))
        return
    print(f"Director conectado ({agent.model}). Escribe una orden, o 'salir'.")
    while True:
        try:
            text = input("> ").strip()
        except EOFError:
            break
        if text.lower() in {"salir", "exit", "quit"}:
            break
        if text:
            print(agent.ask(text, on_tool=show))


if __name__ == "__main__":
    main()
