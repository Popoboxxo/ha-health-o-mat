"""Pro-Person Feature-Flächen (REQ-HOM-009, REQ-HOM-122) — HA-freie Auswertung.

Vier getrennte Bereiche können pro Config-Entry (= Person) an- oder
abgeschaltet werden: Trinken, Blutdruck, Wohlbefinden und Laborwerte. Die
Auswahl lebt in ``entry.options["areas"]`` als
``{drink: bool, bp: bool, wellbeing: bool, labs: bool}``.

Semantik (Bindung, REQ-HOM-009 Migrationspfad): ein FEHLENDER Schlüssel — sowohl
``areas`` selbst als auch ein einzelner Unter-Schlüssel — bedeutet „aktiv". Damit
bleiben Alt-Entries ohne ``areas``-Option vollständig aktiv; nur explizit auf
``False`` gesetzte Bereiche werden deaktiviert. Deaktivieren entfernt lediglich
Entities beim Plattform-Setup — ``unique_id`` und Store bleiben unverändert, eine
Reaktivierung erzeugt dieselbe Entity wieder.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

AREA_DRINK = "drink"
AREA_BP = "bp"
AREA_WELLBEING = "wellbeing"
AREA_LABS = "labs"

AREAS: tuple[str, ...] = (AREA_DRINK, AREA_BP, AREA_WELLBEING, AREA_LABS)
OPTION_AREAS = "areas"

DEFAULT_AREAS: dict[str, bool] = {
    AREA_DRINK: True,
    AREA_BP: True,
    AREA_WELLBEING: True,
    AREA_LABS: True,
}


def _normalize(value: Mapping | None) -> dict[str, bool]:
    """Roh-Angabe ``{area: bool}`` auf die bekannten Bereiche normalisieren.

    Startet bei allen Bereichen aktiv. Ist ``value`` ein Mapping, überschreibt
    jeder vorhandene, bekannte Bereich den Default mit ``bool(value[area])``;
    fehlende Unter-Schlüssel bleiben aktiv und unbekannte Schlüssel werden
    ignoriert. Nicht-Mapping-Angaben (None, String, Liste, …) → alle aktiv.
    """
    result = dict(DEFAULT_AREAS)
    if isinstance(value, Mapping):
        for area in AREAS:
            if area in value:
                result[area] = bool(value[area])
    return result


def active_areas(options: Mapping | None) -> dict[str, bool]:
    """Aktive Bereiche aus einem ``entry.options``-Mapping.

    Liefert IMMER ein frisches Dict (keine geteilten Referenzen); ein fehlendes
    oder nicht-Mapping ``options[OPTION_AREAS]`` ergibt alle Bereiche aktiv.
    """
    if isinstance(options, Mapping):
        raw: Any = options.get(OPTION_AREAS)
    else:
        raw = None
    return _normalize(raw if isinstance(raw, Mapping) else None)


def area_enabled(options: Mapping | None, area: str) -> bool:
    """True, wenn der Bereich ``area`` für ``options`` aktiv ist (unbekannt → False)."""
    return active_areas(options).get(area, False)


def areas_equal(a: Mapping | None, b: Mapping | None) -> bool:
    """True, wenn beide Roh-Angaben dieselbe aktive Bereichs-Menge beschreiben.

    Vergleicht normalisiert: ``None``/``{}`` und ``{"drink": True}`` sind gleich
    (fehlende Unter-Schlüssel = aktiv).
    """
    return _normalize(a) == _normalize(b)
