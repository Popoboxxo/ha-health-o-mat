"""Freitext-Parser für Getränkeeingaben — reine Logik, unit-testbar.

Grammatik (DE/EN, Reihenfolge frei): ``<typ>? <menge>? [ml|l]?``
Beispiele: „Kaffee 300ml", „0,5 l wasser", „cola", „350", „Ingwertee 400".
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .const import DRINK_LEXICON, NO_TYPE_LABEL

_AMOUNT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(m\s*l|liter|litre|ltr|\bl\b)?", re.IGNORECASE)


@dataclass(slots=True)
class DrinkParse:
    """Ergebnis eines Parser-Durchlaufs."""

    ok: bool
    amount_ml: int | None = None
    drink_type: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "amount_ml": self.amount_ml,
            "drink_type": self.drink_type,
            "error": self.error,
        }


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = text.replace(",", ".")
    text = re.sub(r"\s+", " ", text)
    return text


def parse(text: str) -> DrinkParse:
    """Parst eine Freitexteingabe zu Menge + Getränketyp."""
    if not text or not text.strip():
        return DrinkParse(ok=False, error="Eingabe ist leer")

    cleaned = _normalize(text)
    cleaned = cleaned.replace("milliliter", "ml").replace("millilitre", "ml")

    # Menge + Einheit finden
    amount_ml: int | None = None
    match = _AMOUNT_RE.search(cleaned)
    remaining = cleaned
    if match:
        raw_number = match.group(1)
        unit = (match.group(2) or "").strip()
        value = float(raw_number)
        if unit.startswith(("l", "L")) and not unit.startswith("m"):
            # Liter (auch "l" alleine); "ml" wurde bereits vorher ersetzt
            if unit in ("liter", "litre", "ltr", "l"):
                value *= 1000
        amount_ml = round(value)
        remaining = (cleaned[: match.start()] + " " + cleaned[match.end() :]).strip()

    # Typ aus restlichen Worten bestimmen
    words = [w for w in remaining.split() if w]
    resolved_type: str | None = None
    unknown_words: list[str] = []

    for word in words:
        key = word.rstrip(".!?")
        if key in DRINK_LEXICON:
            canonical, default_ml = DRINK_LEXICON[key]
            resolved_type = canonical
            if amount_ml is None:
                amount_ml = default_ml
            break
        unknown_words.append(word)

    if resolved_type is None and unknown_words:
        # Unbekannter Typ wird wörtlich übernommen (z. B. "Ingwertee")
        resolved_type = " ".join(unknown_words).title()
        if amount_ml is None:
            return DrinkParse(
                ok=False,
                drink_type=resolved_type,
                error="Keine Menge erkannt (z. B. 'Ingwertee 400')",
            )

    if amount_ml is None:
        return DrinkParse(ok=False, error="Weder Getränketyp noch Menge erkannt")

    if amount_ml <= 0:
        return DrinkParse(ok=False, error="Menge muss größer 0 sein")
    if amount_ml > 10000:
        return DrinkParse(ok=False, error="Menge unrealistisch hoch (max. 10.000 ml)")

    if resolved_type is None:
        resolved_type = NO_TYPE_LABEL

    return DrinkParse(ok=True, amount_ml=amount_ml, drink_type=resolved_type)
