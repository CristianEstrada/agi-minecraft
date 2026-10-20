# Guía de configuración (fase 1)

Objetivo: que el agente pueda ejecutar comandos y controlar NPCs en el servidor NeoForge 21.1.248 (Minecraft 1.21.1).

## 1. Activar RCON en el servidor

Con el servidor apagado, edita `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=UNA-CONTRASEÑA-LARGA-Y-ALEATORIA
broadcast-rcon-to-ops=false
```

Arranca el servidor. En el log debe aparecer `RCON running on 0.0.0.0:25575`.

**Seguridad:** RCON da control total del servidor y viaja sin cifrar. No abras el puerto 25575 a internet. Si el agente corre en otra máquina, usa una VPN (por ejemplo Tailscale) o un túnel SSH (`ssh -L 25575:localhost:25575 usuario@servidor`). Si tu hosting no permite eso, limita el puerto por IP en el firewall.

## 2. Instalar Easy NPC

1. Descarga **Easy NPC (bundle)** para **NeoForge 1.21.1** desde [Modrinth](https://modrinth.com/mod/easy-npc) o [CurseForge](https://www.curseforge.com/minecraft/mc-mods/easy-npc). Revisa que el archivo diga `neoforge-1.21.1` (por ejemplo `easy_npc_bundle-neoforge-1.21.1-6.12.0.jar`).
2. Cópialo en la carpeta `mods/` del servidor.
3. Los jugadores también deben tenerlo en su cliente, porque el mod añade entidades y pantallas propias.
4. Reinicia el servidor y comprueba en consola: `help easy_npc`.

## 3. Configurar el agente

Necesitas Python 3.11 o superior.

```bash
git clone https://github.com/CristianEstrada/agi-minecraft.git
cd agi-minecraft
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env`:

- `RCON_HOST`, `RCON_PORT`, `RCON_PASSWORD`: los del paso 1.
- `MODEL`: el modelo a usar, en formato LiteLLM. Para cambiar de proveedor solo cambias esta línea y su API key:

| Proveedor | `MODEL` | Variable de la key |
|---|---|---|
| Anthropic | `anthropic/claude-sonnet-5-5` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai/gpt-5` | `OPENAI_API_KEY` |
| Google | `gemini/gemini-2.5-pro` | `GEMINI_API_KEY` |
| Local (Ollama) | `ollama/llama3.1` | ninguna |

El modelo debe soportar *tool calling*. La lista completa de proveedores está en la [documentación de LiteLLM](https://docs.litellm.ai/docs/providers).

## 4. Primera prueba

```bash
python -m director "¿cuántos jugadores hay conectados?"
```

Verás cada comando que ejecuta (`>`) y la respuesta del servidor (`<`). Si funciona, prueba con NPCs:

```bash
python -m director "crea un NPC llamado Bob en las coordenadas del spawn y haz que salude"
```

El agente consulta `help easy_npc` para aprender la sintaxis antes de usarla.

## Problemas comunes

- **`Connection refused`**: RCON no está activo, el puerto es otro o un firewall lo bloquea.
- **`RCON authentication failed`**: la contraseña de `.env` no coincide con `rcon.password`.
- **El modelo no ejecuta comandos**: el modelo elegido no soporta tool calling; prueba con otro.
- **`command 'x' is blocked`**: está en `BLOCKED_COMMANDS`; quítalo de la lista si de verdad quieres permitirlo.
