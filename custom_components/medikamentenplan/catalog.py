"""Mitgelieferte Startliste/Herstellerliste (eigene Zusammenstellung, keine PZN/Preise)."""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent / "catalog"


@cache
def startliste() -> dict[str, dict]:
    data = json.loads((_DIR / "startliste.json").read_text(encoding="utf-8"))
    return {e["wirkstoff"]: e for e in data["eintraege"]}


@cache
def hersteller() -> list[str]:
    return json.loads((_DIR / "hersteller.json").read_text(encoding="utf-8"))["hersteller"]


def fmt(n: float) -> str:
    return f"{n:g}"
