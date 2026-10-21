# Guía del proyecto

Esta guía explica cada parte del director: qué hace, cómo se conecta con lo demás, cómo usarla y cómo extenderla. Para instalarlo desde cero, ver [SETUP.md](SETUP.md).

**Contenido**

1. [Qué es el director](#1-qué-es-el-director)
2. [Mapa del proyecto](#2-mapa-del-proyecto)
3. [Cómo piensa el agente](#3-cómo-piensa-el-agente)
4. [Herramientas](#4-herramientas)
5. [Seguridad](#5-seguridad)
6. [Formas de usarlo](#6-formas-de-usarlo)
7. [NPCs con personalidad](#7-npcs-con-personalidad)
8. [Configuración (.env)](#8-configuración-env)
9. [Modelos y costos](#9-modelos-y-costos)
10. [Economía (en pausa)](#10-economía-en-pausa)
11. [Próximas features](#11-próximas-features)
12. [Cómo agregar una feature nueva](#12-cómo-agregar-una-feature-nueva)
13. [Operación diaria y problemas comunes](#13-operación-diaria-y-problemas-comunes)
14. [Convenciones del repositorio](#14-convenciones-del-repositorio)

---

## 1. Qué es el director

El director es un programa en Python que corre en la misma VPS del servidor de Minecraft. Usa un modelo de lenguaje (Claude, GPT, Gemini, uno local...) para **decidir** qué hacer y lo **ejecuta** en el servidor con comandos de consola enviados por RCON.

No es un mod: el servidor no sabe que existe. Para el servidor, el director es como un administrador que escribe comandos en la consola. Eso tiene dos ventajas:

- Funciona con cualquier mod que tenga comandos (Easy NPC hoy, otros mañana).
- Se puede actualizar o reiniciar sin tocar el servidor.

Y una limitación: solo "ve" lo que los comandos responden y lo que aparece en el log del servidor.

```
                      ┌───────────── npcs.yaml (fichas de NPCs)
                      ▼
 Chat del juego ──► listen ───┐
 (logs/latest.log)            │
                              ├──► Agente ──► Herramientas ──► RCON ──► Servidor NeoForge
 Órdenes tuyas ──► director ──┘   (LLM)       run_command              ├─ Easy NPC
 (terminal)                                   npc_say                  └─ resto de mods
```

## 2. Mapa del proyecto

```
agi-minecraft/
├── director/
│   ├── __main__.py   CLI: `python -m director "orden"` o modo interactivo
│   ├── listen.py     Modo escucha: lee el chat en vivo y hace hablar a los NPCs
│   ├── console.py    Consola RCON para humanos, sin IA ni bloqueos
│   ├── agent.py      El "cerebro": bucle de conversación con el modelo
│   ├── tools.py      Las herramientas que el modelo puede usar
│   ├── npcs.py       Lee las fichas de personalidad de npcs.yaml
│   ├── rcon.py       Cliente RCON (el protocolo de la consola remota)
│   ├── config.py     Lee el .env y arma la conexión
│   └── economy.py    Prototipo de economía (en pausa)
├── tests/            Pruebas automáticas (no necesitan servidor ni API key)
├── docs/
│   ├── SETUP.md      Instalación paso a paso
│   └── GUIA.md       Esta guía
├── npcs.example.yaml Ejemplo de fichas de NPCs
├── .env.example      Ejemplo de configuración
└── requirements.txt  Dependencias de Python
```

Archivos que **no** se suben a git (están en `.gitignore`): `.env` (contraseñas y keys), `npcs.yaml` (tus fichas reales) y `data/`.

## 3. Cómo piensa el agente

Todo pasa en `director/agent.py`. Cuando le das una tarea, el agente:

1. Arma una conversación con el **prompt de sistema** (sus reglas generales) y tu tarea.
2. Le envía al modelo esa conversación más la lista de herramientas disponibles.
3. El modelo responde de dos formas posibles:
   - **Pide usar una herramienta**, por ejemplo `run_command("help easy_npc")`. El agente la ejecuta, agrega el resultado a la conversación y vuelve al paso 2.
   - **Responde con texto**. Eso significa que terminó, y el texto es su resumen.
4. Si llega a `MAX_STEPS` llamadas sin terminar, se detiene. Es un freno para que un error no gaste tokens sin fin.

En la terminal ves cada paso: `>` es lo que el modelo pidió y `<` es lo que respondió el servidor.

**El prompt de sistema** (`SYSTEM_PROMPT` en `agent.py`) define el carácter del director: consultar `help` antes de usar comandos desconocidos, hacer el mínimo de comandos, no usar comandos de prueba ni que afecten a muchas entidades, y preguntar si no está seguro. Si quieres cambiar el comportamiento general del director, este es el lugar.

**Por qué funciona con cualquier modelo**: el agente no habla directamente con Anthropic, OpenAI o Google. Usa [LiteLLM](https://docs.litellm.ai/), que traduce una misma llamada al formato de cada proveedor. Por eso cambiar de modelo es cambiar `MODEL` en el `.env`.

## 4. Herramientas

Las herramientas son lo único que el modelo puede hacer en el mundo. Están definidas en `director/tools.py` en dos partes: la **descripción** que lee el modelo (qué hace y qué parámetros recibe) y el **código** que se ejecuta de verdad.

### `run_command`

Ejecuta cualquier comando del servidor (sin la `/`) y devuelve la respuesta. Ejemplos de lo que el modelo hace con ella: `list`, `help easy_npc`, `easy_npc name set <uuid> Bob`, `time set day`, `give Steve minecraft:bread 4`.

Antes de ejecutar, pasa por la lista de bloqueos (ver [Seguridad](#5-seguridad)).

### `npc_say`

Hace hablar a un NPC: muestra `<Bob> texto` en amarillo en el chat de los jugadores que están cerca de ese NPC (16 bloques por defecto).

Por dentro hace dos cosas:
1. Comprueba que existe una entidad con ese nombre exacto (`execute if entity @e[name="Bob"]`). Si no hay ningún jugador cerca, la zona no está cargada y el NPC "no existe" para el servidor: la herramienta devuelve un error claro.
2. Envía un `tellraw` a los jugadores en el radio, posicionado en el NPC.

Existe porque Easy NPC no permite escribir diálogos por comandos (solo abrir o cerrar diálogos creados en su interfaz). Así, quien escribe lo que dicen los NPCs es el modelo, en el momento.

### Herramientas de economía

`economy_balance`, `economy_pay`, `economy_charge`, `shop_sell`, `economy_report`. Solo se cargan con `ECONOMY_ENABLED=true`. Hoy están en pausa (ver [sección 10](#10-economía-en-pausa)).

## 5. Seguridad

El modelo puede equivocarse. Ya pasó: usó `easy_npc test spawn` y creó 37 NPCs de prueba. Por eso hay varias capas:

1. **Lista de bloqueos** (`BLOCKED_COMMANDS` en `.env`). Cada entrada bloquea todo comando que empiece con ella:
   - `stop` bloquea `stop`.
   - `easy_npc test` bloquea `easy_npc test spawn ...`, pero no `easy_npc name set ...`.
   - También revisa lo que va después de `run` dentro de `execute`, así que `execute as Steve run kill @e` se bloquea igual.

   Bloqueados por defecto: `stop, op, deop, ban, ban-ip, pardon, whitelist, save-off, kill, easy_npc test`.
2. **Prompt de sistema**: le pide no usar comandos de prueba ni masivos, y detenerse a preguntar si no está seguro.
3. **Herramientas acotadas**: para cosas sensibles (como el dinero) la idea es no darle `run_command` libre, sino herramientas con límites escritos en el código, que no dependen de que el modelo obedezca.
4. **`MAX_STEPS`**: tope de acciones por tarea.
5. **Red**: RCON solo escucha en la VPS (`RCON_HOST=localhost`) y el puerto 25575 está cerrado con `ufw`.

La consola `python -m director.console` **no** tiene bloqueos: es para ti.

**Recuerda**: si tu `.env` tiene `BLOCKED_COMMANDS`, ese valor reemplaza al de por defecto. Cuando el proyecto agregue bloqueos nuevos, cópialos a tu `.env`.

## 6. Formas de usarlo

Siempre desde la carpeta del proyecto y con el entorno activado:
```bash
cd ~/minecraft/agi-minecraft && source .venv/bin/activate
```

### Orden suelta

```bash
python -m director "pon de día y despeja el clima"
```
Ejecuta la tarea y termina. Cada orden empieza de cero, así que es lo más barato.

### Modo interactivo

```bash
python -m director
```
Conversación continua: recuerda lo que le dijiste antes. Cada mensaje reenvía toda la conversación, así que gasta más tokens a medida que avanza. Escribe `salir` para cerrar.

### Modo escucha

```bash
python -m director.listen
```
Lee `logs/latest.log` en vivo y reacciona a:
- **Mensajes del chat que mencionan a un NPC** de `npcs.yaml` (por ejemplo "Bob, ¿qué sabes del Nether?"). Responde ese NPC, con su ficha.
- **Mensajes que dicen "director"**. Responde el director, usando el NPC que mejor encaje.
- **Jugadores que entran**, solo si `GREET_JOINS=true`.

Todo lo demás del chat no llama al modelo, así que no gasta tokens. Déjalo corriendo en `tmux` (`tmux new -s director`, y para salir sin cerrarlo, `Ctrl+B` y luego `D`).

Si el servidor se reinicia, el modo escucha detecta el log nuevo y sigue funcionando.

### Consola RCON

```bash
python -m director.console
```
Envía comandos tal cual, sin IA ni bloqueos. Útil para revisar cosas o corregir errores a mano.

## 7. NPCs con personalidad

### Paso 1: el NPC en el juego

Los NPCs son entidades de Easy NPC. Necesitas uno con un nombre único. Si ya hay uno cerca de ti, el agente puede nombrarlo:
```bash
python -m director "ponle Ana al NPC de Easy NPC más cercano al jugador TU_NICK. No crees NPCs nuevos."
```
También puedes crearlo y nombrarlo desde la interfaz de Easy NPC en el juego.

### Paso 2: la ficha

Crea `npcs.yaml` a partir del ejemplo:
```bash
cp npcs.example.yaml npcs.yaml
nano npcs.yaml
```

Cada NPC es una entrada cuya clave es **exactamente** su nombre en el juego (mayúsculas incluidas):

```yaml
Ana:
  rol: Guardiana del templo del spawn
  personalidad: >
    Seria, solemne y misteriosa. Habla en tono antiguo y responde con acertijos.
  sabe: >
    Custodia la historia del servidor. Sabe que Bob, el mercader, le debe un favor.
  reglas: >
    Nunca da respuestas directas sobre el futuro. Nunca regala objetos.
```

| Campo | Para qué sirve | Ejemplo |
|---|---|---|
| `rol` | Qué hace en el mundo. También se usa para que el director sepa a quién elegir. | `Herrero de la aldea` |
| `personalidad` | Cómo habla y se comporta. | `Gruñón pero honesto, frases cortas` |
| `sabe` | Lo que conoce: historia, rumores, relación con otros NPCs. | `Ha visto un dragón al este` |
| `reglas` | Lo que nunca debe hacer. | `No revela dónde está el tesoro` |
| `vende` | Productos y precios. Solo se usa con la economía activada. | `minecraft:bread x4 por 10` |

El `>` en YAML permite escribir textos largos en varias líneas. La indentación con espacios es obligatoria (nunca tabs).

### Paso 3: activarlo

Reinicia el modo escucha (`Ctrl+C` y otra vez `python -m director.listen`). Al arrancar muestra la lista de NPCs que cargó. En el juego, acércate al NPC y escribe en el chat un mensaje que lo mencione.

### Cómo funciona por dentro

Cuando alguien menciona a Ana, `listen.py` arma un mensaje corto para el modelo con:
- la ficha de Ana (solo la de ella, no las de todos),
- las últimas 6 líneas de conversación de Ana,
- las últimas 10 líneas del chat general,
- lo que dijo el jugador.

El modelo responde llamando a `npc_say("Ana", "...")`. Cada mensaje es una conversación nueva y corta, así que el gasto por mensaje no crece con el tiempo.

**Memoria**: cada NPC recuerda sus últimas conversaciones mientras el modo escucha esté encendido. Si lo reinicias, empiezan de cero. (Memoria permanente está en las próximas features.)

### Consejos para escribir buenas fichas

- **Concreto y corto**: "Habla con frases cortas y siempre intenta vender algo" funciona mejor que un párrafo de historia.
- **Conecta a los NPCs entre sí** en `sabe`: "Bob es mi hermano y no le confío nada". Eso da sensación de mundo vivo.
- **Usa `reglas` para los límites duros**: secretos, objetos que no se regalan, temas que evita.
- **Dale un "gancho" a cada NPC**: un rumor, una misión, un secreto. Es lo que hace que los jugadores vuelvan a hablarle.
- **Prueba y ajusta**: habla con el NPC, mira cómo responde y edita la ficha. Los cambios se aplican al reiniciar la escucha.

## 8. Configuración (.env)

| Variable | Qué hace | Valor por defecto |
|---|---|---|
| `RCON_HOST`, `RCON_PORT`, `RCON_PASSWORD` | Conexión a la consola del servidor | `localhost`, `25575`, (obligatoria) |
| `MODEL` | Modelo a usar, formato LiteLLM | `anthropic/claude-sonnet-5-5` |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` | Keys de cada proveedor; solo hace falta la del modelo elegido | vacías |
| `BLOCKED_COMMANDS` | Comandos prohibidos (por prefijo) | ver sección 5 |
| `MAX_STEPS` | Máximo de acciones por tarea | `12` |
| `LOG_PATH` | Log del servidor, relativo a la carpeta del proyecto | `../server/logs/latest.log` |
| `NPC_FILE` | Archivo de fichas | `npcs.yaml` |
| `NPC_NAMES` | NPCs extra sin ficha, separados por coma | vacío |
| `GREET_JOINS` | Saludar a los jugadores al entrar | `false` |
| `ECONOMY_*` | Economía (en pausa) | desactivada |

Para usar otro modelo en una sola ejecución, sin editar el `.env`:
```bash
MODEL=gemini/gemini-2.5-flash python -m director "orden"
```

## 9. Modelos y costos

- **Para NPCs y órdenes simples**: un modelo pequeño y barato (`anthropic/claude-haiku-5-5`, Gemini Flash, GPT mini).
- **El modelo debe soportar tool calling**. Si no ejecuta herramientas y solo responde texto, prueba con otro.
- **Modelos locales** (Ollama): no cuestan tokens, pero en CPU son lentos y fallan más.
- **Lo que más gasta**: el modo interactivo con conversaciones largas, y `GREET_JOINS=true` en servidores con muchas entradas.
- **Protección**: pon un límite de gasto mensual en la consola de cada proveedor.

## 10. Economía (en pausa)

Está pausada hasta decidir qué mod de economía usará el servidor (hoy no tiene ninguno). Con `ECONOMY_ENABLED=false` (por defecto) el director no la conoce ni la usa.

Existe un prototipo funcional (`director/economy.py`) con monedas virtuales en un scoreboard, por si sirve de referencia o de plan B:
- Herramientas: saldo, pagar, cobrar, vender objetos y reporte.
- Límites en código: máximo por transacción, máximo pagado por jugador al día, solo nombres exactos (sin `@a`).
- Historial de movimientos en `data/ledger.jsonl`.
- Al activarla, también se bloquea `scoreboard players` en `run_command`.

**Cuando se elija el mod**, el trabajo es reemplazar el interior de `economy.py` por los comandos de ese mod (o su API), manteniendo las mismas herramientas y límites. Lo que conviene revisar de un mod candidato:
- Que tenga versión para NeoForge 1.21.1.
- Que tenga **comandos** para consultar saldos y mover dinero (sin eso el director no puede administrarlo).
- Si las monedas son físicas (objetos) o virtuales, y si los jugadores necesitan el mod en su cliente.

## 11. Próximas features

### Eventos

- **Reloj** (`python -m director.loop`): cada N minutos le da al director un resumen del servidor (jugadores conectados, hora del juego, eventos recientes) y le pregunta si toca lanzar algo.
- **Catálogo** (`events.yaml`): cada evento define sus comandos, duración, requisitos (mínimo de jugadores, horario) y tiempo de espera entre repeticiones. El director elige y parametriza eventos del catálogo, no improvisa comandos.
- **Herramienta `start_event`**: lanza un evento, lo anuncia con un NPC y registra cuándo termina.
- **Ideas**: invasión nocturna en la aldea, mercader ambulante, búsqueda del tesoro con pistas de los NPCs, recompensas dobles el fin de semana.

### Interacciones

Que hacer clic derecho sobre un NPC también lo despierte. Easy NPC puede ejecutar un comando al interactuar; si ese comando escribe una marca en el log, el modo escucha la detecta igual que el chat.

### Memoria permanente

Guardar en disco un resumen de lo que cada NPC habló con cada jugador, para que Bob recuerde a Steve aunque se reinicie el director.

### Modelo por tarea

Un modelo barato para las conversaciones de NPCs y uno más capaz para decisiones de eventos y economía.

## 12. Cómo agregar una feature nueva

La mayoría de las features son **una herramienta nueva** más, a veces, **una entrada nueva**.

### Agregar una herramienta

1. En `director/tools.py`, agrega la descripción a la lista `TOOLS`. El modelo decide cuándo usarla según `description`, así que escríbela clara:
   ```python
   {
       "type": "function",
       "function": {
           "name": "set_weather",
           "description": "Change the weather. Use it for events or when players ask for it.",
           "parameters": {
               "type": "object",
               "properties": {"kind": {"type": "string", "enum": ["clear", "rain", "thunder"]}},
               "required": ["kind"],
           },
       },
   },
   ```
2. En `ToolRunner.run`, agrega el caso y escribe el método que la ejecuta:
   ```python
   if name == "set_weather":
       return self.rcon.command(f"weather {args['kind']}")
   ```
3. Valida en el código todo lo que pueda ser peligroso (nombres, cantidades, selectores), en lugar de confiar en el prompt.
4. Agrega un test en `tests/test_director.py` con un RCON falso (hay ejemplos con `SimpleNamespace` y `FakeScoreboard`).

### Agregar una entrada (algo que despierte al agente)

Sigue el modelo de `listen.py`: detecta el evento, arma un mensaje corto con solo el contexto necesario y crea un `Agent` nuevo para responder. Mantener los mensajes cortos es lo que mantiene bajo el costo.

### Probar sin servidor

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```
Los tests usan un servidor RCON falso y respuestas de modelo simuladas: no necesitan API key ni Minecraft. GitHub Actions los corre en cada push.

## 13. Operación diaria y problemas comunes

**Servidor**
- Arrancar o reiniciar: `sudo systemctl start minecraft` / `sudo systemctl restart minecraft`.
- Ver el log: `sudo tail -f ~/minecraft/server/logs/latest.log`.
- Nunca lo arranques con `sudo ./start.sh`: los archivos quedarían a nombre de root.

**Actualizar el director**
```bash
cd ~/minecraft/agi-minecraft && git pull
source .venv/bin/activate && pip install -r requirements.txt
```
Revisa si `.env.example` trae variables nuevas y cópialas a tu `.env`.

**Problemas comunes**

| Síntoma | Causa probable |
|---|---|
| `Connection refused` | El servidor está apagado o RCON no está activo |
| `RCON authentication failed` | La contraseña del `.env` no coincide con `server.properties` |
| `no NPC named 'X' is loaded` | El nombre no coincide exacto, o no hay jugadores cerca del NPC |
| `command '...' is blocked` | Está en `BLOCKED_COMMANDS` |
| El NPC no responde en el chat | No está en `npcs.yaml`/`NPC_NAMES`, el mensaje no menciona su nombre, o `listen` no está corriendo |
| `Permission denied` al leer el log | Ver el paso de `setfacl` en SETUP.md |
| El modelo solo responde texto | El modelo no soporta tool calling |

## 14. Convenciones del repositorio

- Commits en inglés, en imperativo ("Add events loop") y sin referencias a herramientas de IA.
- Antes de subir cambios: `python -m pytest -q`.
- Nunca subas `.env`, `npcs.yaml` ni `data/`.
