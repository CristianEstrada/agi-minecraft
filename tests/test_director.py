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
