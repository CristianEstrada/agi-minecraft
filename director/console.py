"""Plain RCON console for humans: `python -m director.console`.
No model involved and no BLOCKED_COMMANDS: whatever you type is sent as is."""

import os

from dotenv import load_dotenv

from .rcon import RconClient


def main() -> None:
    load_dotenv()
    rcon = RconClient(
        os.getenv("RCON_HOST", "localhost"),
        int(os.getenv("RCON_PORT", "25575")),
        os.environ["RCON_PASSWORD"],
    )
    rcon.connect()
    print("Consola RCON. Escribe comandos sin '/', o 'salir'.")
    while True:
        try:
            line = input("rcon> ").strip()
        except EOFError:
            break
        if line.lower() in {"salir", "exit", "quit"}:
            break
        if line:
            print(rcon.command(line.lstrip("/")) or "(sin salida)")


if __name__ == "__main__":
    main()
