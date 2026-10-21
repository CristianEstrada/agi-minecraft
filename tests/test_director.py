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
