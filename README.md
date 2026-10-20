# AGI in Minecraft

Agente "director" que controla NPCs y el rumbo del metagame de un servidor de Minecraft (NeoForge 1.21.1).

Funciona con cualquier modelo (Claude, GPT, Gemini, modelos locales con Ollama, etc.) gracias a [LiteLLM](https://docs.litellm.ai/): se cambia el modelo con una variable de entorno, sin tocar código.

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
pytest
```
