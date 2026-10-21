"""CLI: `python -m director` (interactive) or `python -m director "orden"`."""

import sys

from . import config
from .agent import Agent


def main() -> None:
    cfg = config.load()
    agent = Agent(model=cfg["model"], tools=config.connect_runner(), max_steps=cfg["max_steps"])

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
