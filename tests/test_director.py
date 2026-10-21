import json
import socket
import struct
import threading
from types import SimpleNamespace

import pytest

from director import agent as agent_mod
from director.agent import Agent
from director.rcon import RconClient, RconError
from director.tools import ToolRunner


def _read_packet(conn):
    (length,) = struct.unpack("<i", conn.recv(4))
    data = b""
    while len(data) < length:
        data += conn.recv(length - len(data))
    req_id, ptype = struct.unpack("<ii", data[:8])
    return req_id, ptype, data[8:-2].decode()


def _write_packet(conn, req_id, body):
    payload = struct.pack("<ii", req_id, 0) + body.encode() + b"\x00\x00"
    conn.sendall(struct.pack("<i", len(payload)) + payload)


@pytest.fixture
def fake_server():
    """A fake RCON server that echoes commands and accepts password 'secret'."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    received = []

    def serve():
        conn, _ = srv.accept()
        with conn:
            req_id, _, password = _read_packet(conn)
            _write_packet(conn, req_id if password == "secret" else -1, "")
            while True:
                try:
                    req_id, _, cmd = _read_packet(conn)
                except (struct.error, OSError):
                    return
                received.append(cmd)
                _write_packet(conn, req_id, f"ran: {cmd}")

    threading.Thread(target=serve, daemon=True).start()
    yield srv.getsockname()[1], received
    srv.close()


def test_rcon_command_roundtrip(fake_server):
    port, received = fake_server
    with RconClient("127.0.0.1", port, "secret") as rcon:
        assert rcon.command("list") == "ran: list"
    assert received == ["list"]


def test_rcon_bad_password(fake_server):
    port, _ = fake_server
    with pytest.raises(RconError):
        RconClient("127.0.0.1", port, "wrong").connect()


def test_blocked_commands_never_reach_server():
    rcon = SimpleNamespace(command=lambda c: pytest.fail("should not run"))
    runner = ToolRunner(rcon, ["stop", "op"])
    assert "blocked" in runner.run("run_command", json.dumps({"command": "/stop"}))
    assert "blocked" in runner.run("run_command", json.dumps({"command": "OP Steve"}))


def _response(content=None, tool_calls=None):
    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        model_dump=lambda exclude_none=True: {"role": "assistant", "content": content},
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_agent_runs_tool_then_answers(monkeypatch):
    call = SimpleNamespace(
        id="1", function=SimpleNamespace(name="run_command", arguments=json.dumps({"command": "list"}))
    )
    replies = iter([_response(tool_calls=[call]), _response(content="Hay 0 jugadores.")])
    monkeypatch.setattr(agent_mod.litellm, "completion", lambda **kw: next(replies))
    ran = []
    rcon = SimpleNamespace(command=lambda c: ran.append(c) or "There are 0 players")
    agent = Agent("any/model", ToolRunner(rcon, []))
    assert agent.ask("¿quién está conectado?") == "Hay 0 jugadores."
    assert ran == ["list"]
    assert agent.messages[-2]["role"] == "tool"


def test_blocked_prefixes_and_execute_run():
    rcon = SimpleNamespace(command=lambda c: "ok")
    runner = ToolRunner(rcon, ["kill", "easy_npc test"])
    assert runner.is_blocked("easy_npc test spawn standard_npc")
    assert runner.is_blocked("execute as Steve run easy_npc  test spawn x")
    assert runner.is_blocked("execute positioned 0 64 0 run kill @e")
    assert not runner.is_blocked("easy_npc name set abc Bob")
    assert not runner.is_blocked("help easy_npc test")


def test_npc_say_targets_named_npc():
    sent = []

    def command(c):
        sent.append(c)
        return "Test passed, count: 1" if c.startswith("execute if") else ""

    runner = ToolRunner(SimpleNamespace(command=command), [])
    out = runner.run("npc_say", json.dumps({"npc": "Bob Smith", "text": "Hola,  soy Bob"}))
    assert out == "Bob Smith said: Hola, soy Bob"
    assert sent[0] == 'execute if entity @e[type=!player,name="Bob Smith",limit=1]'
    assert sent[1].startswith('execute at @e[type=!player,name="Bob Smith",limit=1] run tellraw @a[distance=..16] ')
    assert json.loads(sent[1].split("..16] ", 1)[1])["text"] == "<Bob Smith> Hola, soy Bob"


def test_npc_say_missing_npc():
    runner = ToolRunner(SimpleNamespace(command=lambda c: "Test failed"), [])
    assert "no NPC named 'Bob'" in runner.run("npc_say", json.dumps({"npc": "Bob", "text": "hi"}))


def test_listen_parses_log_lines():
    from director.listen import addressed_npc, parse

    prefix = "[21Oct2026 02:57:49.123] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: "
    assert parse(prefix + "<SUREGHOST12> Bob, ¿qué vendes?") == ("chat", "SUREGHOST12", "Bob, ¿qué vendes?")
    assert parse(prefix + "SUREGHOST12 joined the game") == ("join", "SUREGHOST12", "")
    assert parse(prefix + "SUREGHOST12 left the game") == ("leave", "SUREGHOST12", "")
    assert parse(prefix + "Done (6.983s)! For help, type \"help\"") is None
    assert addressed_npc("Bob, ¿qué vendes?", ["Bob"]) == "Bob"
    assert addressed_npc("bobina de cobre", ["Bob"]) is None
    assert addressed_npc("hey director", ["Bob"]) == "director"


def test_npc_profiles_and_prompt(tmp_path):
    from collections import deque

    from director import npcs
    from director.listen import build_prompt

    f = tmp_path / "npcs.yaml"
    f.write_text("Bob:\n  rol: Mercader\n  personalidad: >\n    Astuto y\n    amable\n", encoding="utf-8")
    profiles = npcs.load(str(f))
    assert npcs.describe("Bob", profiles["Bob"]) == "Ficha del NPC Bob:\n- Rol: Mercader\n- Personalidad: Astuto y amable"
    memory = {"Bob": deque(["<Steve> hola", "Bob: ¡Bienvenido!"])}
    prompt = build_prompt("chat", "Steve", "Bob, ¿qué vendes?", "Bob", [], profiles, memory)
    assert "Personalidad: Astuto y amable" in prompt
    assert "Bob: ¡Bienvenido!" in prompt
    assert npcs.load(str(tmp_path / "missing.yaml")) == {}


class FakeScoreboard:
    """Minimal fake of the scoreboard and give commands over RCON."""

    def __init__(self, give_ok=True):
        self.scores = {}
        self.give_ok = give_ok
        self.sent = []

    def command(self, c):
        self.sent.append(c)
        parts = c.split()
        if parts[:2] == ["scoreboard", "players"]:
            op, player, amount = parts[2], parts[3], parts[5] if len(parts) > 5 else "0"
            if op == "get":
                if player not in self.scores:
                    return f"Can't get value of monedas for {player}; none is set"
                return f"{player} has {self.scores[player]} [Monedas]"
            sign = 1 if op == "add" else -1
            self.scores[player] = self.scores.get(player, 0) + sign * int(amount)
            return "ok"
        if parts[0] == "give":
            return f"Gave {parts[3]} [{parts[2]}] to {parts[1]}" if self.give_ok else "Unknown item"
        return ""


def _economy(tmp_path, fake, **kw):
    from director.economy import Economy

    return Economy(fake, "monedas", str(tmp_path / "ledger.jsonl"), kw.get("max_tx", 500), kw.get("daily", 1000))


def test_economy_pay_charge_and_limits(tmp_path):
    from director.economy import EconomyError

    fake = FakeScoreboard()
    eco = _economy(tmp_path, fake, daily=600)
    assert eco.balance("Steve") == 0
    assert eco.pay("Steve", 400, "quest") == 400
    with pytest.raises(EconomyError, match="daily payout"):
        eco.pay("Steve", 300, "again")
    with pytest.raises(EconomyError, match="between 1 and 500"):
        eco.pay("Alex", 501, "too much")
    with pytest.raises(EconomyError, match="invalid player"):
        eco.pay("@a", 10, "everyone")
    assert eco.charge("Steve", 100, "fee") == 300
    with pytest.raises(EconomyError, match="has 300 coins"):
        eco.charge("Steve", 400, "too expensive")
    report = eco.report()
    assert report["net_in_circulation"] == 300


def test_shop_sell_gives_item_or_refunds(tmp_path):
    from director.economy import EconomyError

    fake = FakeScoreboard()
    eco = _economy(tmp_path, fake)
    eco.pay("Steve", 100, "start")
    assert "bought 2 minecraft:bread for 30; balance 70" in eco.sell_item("Steve", "minecraft:bread", 2, 30)
    fake.give_ok = False
    with pytest.raises(EconomyError, match="refunded"):
        eco.sell_item("Steve", "minecraft:nope", 1, 50)
    assert eco.balance("Steve") == 70


def test_economy_tools_via_runner(tmp_path):
    fake = FakeScoreboard()
    runner = ToolRunner(fake, ["scoreboard players"], _economy(tmp_path, fake))
    assert {"economy_pay", "shop_sell"} <= {t["function"]["name"] for t in runner.tools}
    assert runner.run("economy_pay", json.dumps({"player": "Steve", "amount": 50, "reason": "x"})) == "paid 50 to Steve; balance 50"
    assert "error" in runner.run("economy_pay", json.dumps({"player": "Steve", "amount": -5, "reason": "x"}))
    assert "blocked" in runner.run("run_command", json.dumps({"command": "scoreboard players add Steve monedas 999"}))


def test_npc_spawn_near():
    sent = []

    def command(c):
        sent.append(c)
        if c.startswith("execute if entity @a[name=Luminux15"):
            return "Test passed, count: 1"
        if c.startswith("execute if entity @e"):
            return "Test failed"
        if " summon " in c:
            return "Summoned new Kira"
        return ""

    runner = ToolRunner(SimpleNamespace(command=command), [])
    out = runner.run("npc_spawn_near", json.dumps({"player": "Luminux15", "name": "Kira"}))
    assert out == "spawned easy_npc:humanoid named 'Kira' 2 blocks in front of Luminux15"
    assert sent[-1] == (
        "execute at Luminux15 rotated as Luminux15 run summon easy_npc:humanoid ^ ^ ^2 "
        '{CustomName:"{\\"text\\": \\"Kira\\"}",CustomNameVisible:1b,PersistenceRequired:1b}'
    )
    assert "invalid player" in runner.run("npc_spawn_near", json.dumps({"player": "@a", "name": "Kira"}))
