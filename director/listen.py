"""Listen mode: `python -m director.listen`.

Follows the server log and wakes the agent when a player talks to an NPC
(chat mentioning one of NPC_NAMES, or "director"), and optionally on joins.
Each event gets a fresh, short conversation so token use stays flat."""

import os
import re
import time
from collections import deque

from . import config
from .agent import SYSTEM_PROMPT, Agent

CHAT = re.compile(r"\]: <(?P<player>[\w.]{1,16})> (?P<text>.+)$")
JOIN = re.compile(r"\]: (?P<player>[\w.]{1,16}) joined the game$")
LEAVE = re.compile(r"\]: (?P<player>[\w.]{1,16}) left the game$")

LISTEN_PROMPT = SYSTEM_PROMPT + """
Estás en modo escucha: recibes eventos del servidor en tiempo real.
- Si un jugador le habla a un NPC, responde como ese NPC con npc_say: breve, en el idioma
  del jugador y fiel a su personalidad. No ejecutes otros comandos salvo que el jugador
  pida algo concreto que tenga sentido para el NPC.
- Si el evento no requiere nada, no hagas nada.
"""


def parse(line: str):
    """Return (kind, player, text) for interesting log lines, else None."""
    line = line.rstrip("\n")
    if m := CHAT.search(line):
        return "chat", m["player"], m["text"]
    if m := JOIN.search(line):
        return "join", m["player"], ""
    if m := LEAVE.search(line):
        return "leave", m["player"], ""
    return None


def addressed_npc(text: str, npc_names: list[str]) -> str | None:
    lowered = text.lower()
    for name in npc_names:
        if re.search(rf"\b{re.escape(name.lower())}\b", lowered):
            return name
    if "director" in lowered:
        return "director"
    return None


def build_prompt(kind: str, player: str, text: str, target: str | None, recent: list[str]) -> str | None:
    context = "\n".join(recent) or "(sin mensajes previos)"
    if kind == "chat" and target:
        who = "a ti (el director)" if target == "director" else f"al NPC {target}"
        return (
            f"El jugador {player} le habla {who}: \"{text}\"\n\n"
            f"Chat reciente:\n{context}\n\n"
            "Responde a través de npc_say" + ("." if target != "director" else " usando el NPC más adecuado, o run_command con 'tellraw' si ningún NPC encaja.")
        )
    if kind == "join":
        return f"El jugador {player} acaba de entrar al servidor. Si hay un NPC adecuado, salúdalo con npc_say."
    return None


def follow(path: str, poll: float = 0.5):
    """Yield new lines of `path`, surviving log rotation on server restart."""
    f = open(path, encoding="utf-8", errors="replace")
    f.seek(0, os.SEEK_END)
    inode = os.fstat(f.fileno()).st_ino
    while True:
        line = f.readline()
        if line:
            yield line
            continue
        time.sleep(poll)
        try:
            st = os.stat(path)
        except FileNotFoundError:
            continue
        if st.st_ino != inode or st.st_size < f.tell():
            f.close()
            f = open(path, encoding="utf-8", errors="replace")
            inode = os.fstat(f.fileno()).st_ino


def main() -> None:
    cfg = config.load()
    runner = config.connect_runner()
    recent: deque[str] = deque(maxlen=10)
    names = ", ".join(cfg["npc_names"]) or "(ninguno; define NPC_NAMES)"
    print(f"Escuchando {cfg['log_path']} con {cfg['model']}. NPCs: {names}. Ctrl+C para salir.")
    for line in follow(cfg["log_path"]):
        event = parse(line)
        if not event:
            continue
        kind, player, text = event
        target = addressed_npc(text, cfg["npc_names"]) if kind == "chat" else None
        if kind == "join" and not cfg["greet_joins"]:
            prompt = None
        else:
            prompt = build_prompt(kind, player, text, target, list(recent))
        if kind == "chat":
            recent.append(f"<{player}> {text}")
        if not prompt:
            continue
        print(f"[{kind}] {player}: {text}")
        agent = Agent(cfg["model"], runner, max_steps=cfg["max_steps"], system_prompt=LISTEN_PROMPT)
        try:
            agent.ask(prompt, on_tool=lambda a, r: print(f"  > {a}\n  < {r}"))
        except Exception as e:  # keep listening even if one model call fails
            print(f"  ! error: {e}")


if __name__ == "__main__":
    main()
