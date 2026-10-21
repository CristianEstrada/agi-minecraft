# Guía del director

Cómo está armado el agente, cómo darle vida a los NPCs y el plan para la economía y los eventos.

## Arquitectura

```
                 ┌──────────── npcs.yaml (personalidades)
                 ▼
Chat del juego ─► listen ─┐
Órdenes (CLI) ───────────►├─► Agente (cualquier LLM vía LiteLLM) ─► herramientas ─► RCON ─► Servidor
Reloj (eventos, futuro) ─┘                                          run_command
                                                                    npc_say
```

- **Agente** (`director/agent.py`): recibe una situación, decide y llama herramientas hasta terminar.
- **Herramientas** (`director/tools.py`): `run_command` ejecuta comandos con lista de bloqueos; `npc_say` hace hablar a un NPC.
- **Entradas**: órdenes por consola (`python -m director`), el chat del juego (`python -m director.listen`) y, más adelante, un reloj para eventos.
- **Seguridad**: `BLOCKED_COMMANDS` en `.env` bloquea comandos por prefijo, también dentro de `execute ... run`.

## NPCs con personalidad

1. Ponle nombre al NPC en el juego. Puede hacerlo el agente: `python -m director "ponle Ana al NPC más cercano a TU_NICK"`.
2. Crea su ficha en `npcs.yaml` (copia `npcs.example.yaml`). La clave debe ser exactamente el nombre del NPC:
   ```yaml
   Ana:
     rol: Guardiana del templo
     personalidad: Seria y misteriosa, responde con acertijos.
     sabe: La historia del servidor y qué eventos se avecinan.
     reglas: Nunca da respuestas directas sobre el futuro.
   ```
3. Reinicia `python -m director.listen`. Cuando un jugador escriba en el chat un mensaje que mencione a Ana, responderá con esa ficha.

Cómo funciona por dentro:
- Cada mensaje es una llamada corta al modelo con **solo la ficha del NPC mencionado**, sus últimas 6 líneas de conversación y las últimas 10 líneas del chat. Así el gasto de tokens no crece con el tiempo.
- La memoria de cada NPC vive mientras la escucha esté encendida; al reiniciarla, empieza de cero.
- Si un jugador escribe `director`, responde el director usando el NPC que mejor encaje.

Consejos para escribir fichas:
- Frases cortas y concretas: el modelo las sigue mejor que párrafos largos.
- Usa `reglas` para lo que nunca debe pasar (regalar objetos, revelar secretos).
- Los NPCs pueden conocerse entre sí: menciónalo en `sabe` ("Bob es mi hermano y no le confío nada").

## Economía (fase 2, plan)

El director no inventa la economía: la **administra** usando el mod de economía que tenga el servidor.

1. **Identificar el mod**. En la VPS:
   ```bash
   ls ~/minecraft/server/mods | grep -iE "econ|currency|coin|money|numismatic|shop|trade"
   ```
   Según el resultado se definen los comandos que el director puede usar (consultar saldo, pagar, cobrar, precios de tienda).
2. **Herramientas acotadas**: en vez de dejarle `run_command` libre para el dinero, se agregan herramientas específicas (`economy_balance`, `economy_pay`, `set_price`) con límites en código: monto máximo por transacción y por jugador al día.
3. **Estado persistente**: un archivo o base SQLite con precios, historial de transacciones y la "salud" de la economía (dinero en circulación, inflación). El director lo lee para decidir.
4. **Política**: el director revisa la economía cada cierto tiempo y ajusta precios o recompensas para mantenerla equilibrada. Los NPCs mercaderes usan esos precios al negociar.

## Eventos (fase 3, plan)

1. **Reloj**: un modo `python -m director.loop` que cada N minutos le da al director un resumen del servidor (jugadores conectados, hora del juego, estado de la economía, eventos recientes) y le pregunta si toca lanzar algo.
2. **Catálogo de eventos** en `events.yaml`: cada evento define sus comandos, duración, requisitos (mínimo de jugadores, horario) y enfriamiento. El director elige y parametriza eventos del catálogo; no improvisa comandos peligrosos.
3. **Herramienta `start_event`**: lanza un evento del catálogo, lo anuncia con un NPC (`npc_say`) y registra cuándo termina.
4. **Ejemplos**: invasión nocturna en la aldea, mercader ambulante con precios especiales, búsqueda del tesoro con pistas que dan los NPCs, recompensas dobles el fin de semana.

## Interacciones (fase 4, idea)

Que el clic derecho sobre un NPC también despierte al director. Easy NPC puede ejecutar comandos al interactuar; si ese comando escribe una marca en el log, `listen` la detecta igual que el chat.

## Costos

- Usa un modelo pequeño (Haiku, Gemini Flash, GPT mini) para las conversaciones de NPCs.
- Más adelante se puede separar: modelo barato para NPCs y uno más capaz para decisiones de economía y eventos.
- Pon un límite de gasto mensual en la consola del proveedor.

## Convenciones del repositorio

- Mensajes de commit en inglés, en imperativo y sin referencias a herramientas de IA.
- Antes de subir cambios: `python -m pytest -q`.
- Nunca subas `.env` ni `npcs.yaml` con datos privados (están en `.gitignore`).
