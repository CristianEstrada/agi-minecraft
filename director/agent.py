"""Model-agnostic agent loop. The model is any LiteLLM model string, e.g.
'anthropic/claude-sonnet-5-5', 'openai/gpt-5', 'gemini/gemini-2.5-pro',
'ollama/llama3.1'."""

import litellm

from .tools import ToolRunner

SYSTEM_PROMPT = """Eres el director de un servidor de Minecraft (NeoForge 1.21.1).
Controlas NPCs y el servidor ejecutando comandos con la herramienta run_command.
- Si no conoces la sintaxis de un comando, consulta primero 'help <comando>'.
- Los NPCs se gestionan con el mod Easy NPC (comando raíz: easy_npc).
- Haz el mínimo de comandos necesarios y explica brevemente lo que hiciste.
- Nunca ejecutes subcomandos de prueba o depuración (como 'easy_npc test') ni comandos
  que afecten a muchas entidades o jugadores a la vez. Si no estás seguro de qué hace un
  comando, detente y pregunta en vez de probarlo.
"""

ECONOMY_PROMPT = """- La economía usa monedas virtuales. Para dinero usa siempre las herramientas economy_* y
  shop_sell, nunca comandos de scoreboard. Sé prudente: no regales monedas sin motivo y
  mantén precios coherentes entre NPCs. Si un jugador quiere comprar a un NPC que vende,
  cobra y entrega con shop_sell usando los precios de su ficha.
"""


class Agent:
    def __init__(self, model: str, tools: ToolRunner, max_steps: int = 12, system_prompt: str = SYSTEM_PROMPT):
        self.model = model
        self.tools = tools
        self.max_steps = max_steps
        if tools.economy:
            system_prompt += ECONOMY_PROMPT
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]

    def ask(self, text: str, on_tool=None) -> str:
        self.messages.append({"role": "user", "content": text})
        for _ in range(self.max_steps):
            response = litellm.completion(model=self.model, messages=self.messages, tools=self.tools.tools)
            message = response.choices[0].message
            self.messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                return message.content or ""
            for call in message.tool_calls:
                result = self.tools.run(call.function.name, call.function.arguments)
                if on_tool:
                    on_tool(call.function.arguments, result)
                self.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        return "(se alcanzó el límite de pasos sin respuesta final)"
