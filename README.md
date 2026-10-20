# Minecraft LLM Director

Experimental Python tool-calling agent for a Minecraft server. The repository name is aspirational: this prototype implements a bounded command-execution loop, not general intelligence.

The current implementation includes an RCON client, configurable blocked commands, an interactive CLI, and regression tests with a fake server and mocked model responses.

Agente "director" que controla NPCs y el rumbo del metagame de un servidor de Minecraft (NeoForge 1.21.1).

Se integra con proveedores de modelos (Claude, GPT, Gemini, modelos locales con Ollama, etc.) compatibles con tool calling gracias a [LiteLLM](https://docs.litellm.ai/): se cambia el modelo con una variable de entorno, sin tocar código.

## Cómo funciona

```
Orden (texto) ─► Agente (cualquier LLM) ─► run_command ─► RCON ─► Servidor NeoForge
                                                                    └─ Easy NPC (NPCs)
```

El agente recibe una orden, decide qué comandos ejecutar, los envía por RCON, lee la respuesta y repite hasta terminar. Los comandos peligrosos (`stop`, `op`, `ban`, ...) están bloqueados por configuración.

## Inicio rápido

```bash
pip install -r requirements.txt
cp .env.example .env   # rellena RCON_PASSWORD, MODEL y la API key
python -m director "crea un NPC llamado Bob junto al spawn"
python -m director     # modo interactivo
```

La configuración del servidor (RCON, Easy NPC) está en [docs/SETUP.md](docs/SETUP.md).

## Roadmap

1. **Control de NPCs y comandos** (en curso)
2. Economía
3. Eventos
4. Interacciones

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The tests exercise RCON authentication/command round trips, command blocking, and an agent tool-call cycle. They use a local fake server and mock model responses; no model API credentials or Minecraft instance are required for the test suite.

[Python tests](https://github.com/CristianEstrada/agi-minecraft/actions/workflows/tests.yml) runs the existing regression suite for pushes and pull requests. See the latest workflow run for verification; live Minecraft/LLM integration is a separate check.
