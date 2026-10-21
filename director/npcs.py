"""NPC profiles loaded from npcs.yaml (see npcs.example.yaml)."""

import os

import yaml

FIELDS = [("rol", "Rol"), ("personalidad", "Personalidad"), ("sabe", "Sabe"), ("reglas", "Reglas")]


def load(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {str(name): profile or {} for name, profile in data.items()}


def describe(name: str, profile: dict) -> str:
    lines = [f"Ficha del NPC {name}:"]
    for key, label in FIELDS:
        if profile.get(key):
            lines.append(f"- {label}: {' '.join(str(profile[key]).split())}")
    return "\n".join(lines)
