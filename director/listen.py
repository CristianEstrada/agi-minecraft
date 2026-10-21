"""Listen mode: `python -m director.listen`.

Follows the server log and wakes the agent when a player talks to an NPC
(chat mentioning an NPC from npcs.yaml / NPC_NAMES, or "director"), and
optionally on joins. Each NPC answers with its own profile and remembers its
last few exchanges.
Each event gets a fresh, short conversation so token use stays flat."""

import os
import re
import time
from collections import deque

from . import config, npcs
from .agent import SYSTEM_PROMPT, Agent

CHAT = re.compile(r"\]: <(?P<player>[\w.]{1,16})> (?P<text>.+)$")
JOIN = re.compile(r"\]: (?P<player>[\w.]{1,16}) joined the game$")
LEAVE = re.compile(r"\]: (?P<player>[\w.]{1,16}) left the game$")

LISTEN_PROMPT = SYSTEM_PROMPT + """
Estás en modo escucha: recibes eventos del servidor en tiempo real.
- Si un jugador le habla a un NPC, responde como ese NPC con npc_say: breve, en el idioma
  del jugador y fiel a su ficha (rol, personalidad, lo que sabe y sus reglas). No ejecutes otros comandos salvo que el jugador
  pida algo concreto que tenga sentido para el NPC.
- Si un jugador quiere comprar algo a un NPC que vende, cobra y entrega con shop_sell usando
  los precios de su ficha; si no le alcanza, el NPC se lo dice. Puedes consultar saldos
  con economy_balance. No regales monedas ni objetos salvo que la ficha lo permita.
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


def build_prompt(kind, player, text, target, recent, profiles, memory) -> str | None:
    context = "\n".join(recent) or "(sin mensajes previos)"
    roster = ", ".join(f"{n} ({p.get('rol', 'sin rol')})" for n, p in profiles.items()) or "(ninguno)"
    if kind == "chat" and target == "director":
        return (
            f"El jugador {player} te habla a ti, el director: \"{text}\"\n\n"
            f"NPCs disponibles: {roster}\n\nChat reciente:\n{context}\n\n"
            "Responde a través del NPC más adecuado con npc_say, o con run_command y 'tellraw' si ninguno encaja."
        )
    if kind == "chat" and target:
        past = "\n".join(memory.get(target, [])) or "(primera conversación)"
        return (
            f"{npcs.describe(target, profiles.get(target, {}))}\n\n"
            f"Conversaciones recientes de {target}:\n{past}\n\n"
            f"Chat reciente del servidor:\n{context}\n\n"
            f"El jugador {player} le dice a {target}: \"{text}\"\n"
            f"Responde como {target} con npc_say."
        )
    if kind == "join":
        return f"El jugador {player} acaba de entrar al servidor. NPCs disponibles: {roster}. Si alguno encaja, salúdalo con npc_say."
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
    profiles = npcs.load(cfg["npc_file"])
    names = list(profiles) + [n for n in cfg["npc_names"] if n not in profiles]
    recent: deque[str] = deque(maxlen=10)
    memory: dict[str, deque[str]] = {}
    print(f"Escuchando {cfg['log_path']} con {cfg['model']}. NPCs: {', '.join(names) or '(ninguno)'}. Ctrl+C para salir.")
    for line in follow(cfg["log_path"]):
        event = parse(line)
        if not event:
            continue
        kind, player, text = event
        target = addressed_npc(text, names) if kind == "chat" else None
        if kind == "join" and not cfg["greet_joins"]:
            prompt = None
        else:
            prompt = build_prompt(kind, player, text, target, list(recent), profiles, memory)
        if kind == "chat":
            recent.append(f"<{player}> {text}")
        if not prompt:
            continue
        print(f"[{kind}] {player}: {text}")
        said = []

        def show(args, result):
            print(f"  > {args}\n  < {result}")
            if " said: " in result:
                said.append(result)

        agent = Agent(cfg["model"], runner, max_steps=cfg["max_steps"], system_prompt=LISTEN_PROMPT)
        try:
            agent.ask(prompt, on_tool=show)
        except Exception as e:  # keep listening even if one model call fails
            print(f"  ! error: {e}")
        if target and target != "director":
            log = memory.setdefault(target, deque(maxlen=6))
            log.append(f"<{player}> {text}")
            log.extend(r.replace(" said: ", ": ", 1) for r in said)


if __name__ == "__main__":
    main()
