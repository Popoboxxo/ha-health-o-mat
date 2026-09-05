"""Tests: Beispiel-Dashboards — Struktur und Entity-Referenzen.

Läuft ohne Home Assistant: parst alle examples/*.yaml und prüft, dass jede
Entity-Referenz dem englischen ID-Schema entspricht und ein bekanntes
Suffix nutzt. So fallen Tippfehler (z. B. bp_warning statt
blood_pressure_warning) schon in CI auf, nicht erst auf der Instanz.
"""
import glob
import os
import re

import yaml

_PERSON_RE = re.compile(r"^[a-z0-9_-]+$")

# Bekannte ID-Suffixe (englisch, aus dem Anzeigenamen erzeugt)
KNOWN_SUFFIXES: dict[str, set[str]] = {
    "sensor": {
        "drinks_today", "daily_goal_progress", "drinks_history", "lifetime_total",
        "blood_pressure_systolic", "blood_pressure_diastolic", "pulse",
        "blood_pressure_history", "wellbeing_last_reported",
    },
    "binary_sensor": {"daily_goal_reached", "blood_pressure_warning"},
    "button": {
        "book_custom_amount", "undo_last_drink", "save_measurement",
        "report_very_bad", "report_bad", "report_okay", "report_good", "report_great",
        "glas_wasser", "flasche_wasser", "tasse_kaffee", "glas_saft",
    },
    "number": {
        "daily_goal", "custom_drink_amount",
        "systolic_warning_threshold", "diastolic_warning_threshold",
        "new_reading_systolic", "new_reading_diastolic", "new_reading_pulse",
    },
    "select": {"wellbeing"},
    "text": {"log_drink_free_text"},
}


def check_entity_id(entity_id: str) -> str | None:
    """Prüfe eine Entity-ID gegen das Schema; None = ok, sonst Fehlermeldung."""
    platform, _, rest = entity_id.partition(".")
    if platform not in KNOWN_SUFFIXES:
        return f"unbekannte Plattform {platform!r}"
    if not rest.startswith("health_o_mat_"):
        return f"Device-Prefix 'health_o_mat_' fehlt: {rest!r}"
    for suffix in KNOWN_SUFFIXES[platform]:
        if rest.endswith("_" + suffix):
            person = rest[len("health_o_mat_"): -(len(suffix) + 1)]
            if person and _PERSON_RE.fullmatch(person):
                return None
            return f"Person-Slug ungültig: {person!r}"
    return "unbekanntes Suffix — falsch geschrieben oder KNOWN_SUFFIXES ergänzen"


def extract_entity_refs(node, out):
    """Sammle alle Entity-Strings aus einem YAML-Baum."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("entity", "entities", "entity_id"):
                if isinstance(value, str):
                    out.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            out.append(item)
                        elif isinstance(item, dict) and isinstance(item.get("entity"), str):
                            out.append(item["entity"])
            extract_entity_refs(value, out)
    elif isinstance(node, list):
        for item in node:
            extract_entity_refs(item, out)


def test_dashboards_valid_yaml_and_known_entity_ids():
    """Alle Beispiel-Dashboards parsen und nur bekannte englische IDs referenzieren."""
    examples = sorted(glob.glob(
        os.path.join(os.path.dirname(__file__), "..", "examples", "*.yaml")
    ))
    assert len(examples) >= 3, f"zu wenige Beispiele gefunden: {examples}"

    for path in examples:
        with open(path) as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data, dict), f"{path}: kein YAML-Dict"

        refs: list[str] = []
        extract_entity_refs(data, refs)
        assert refs, f"{path}: keine Entity-Referenzen gefunden"

        for entity_id in refs:
            problem = check_entity_id(entity_id)
            assert problem is None, f"{path}: {entity_id!r} — {problem}"
