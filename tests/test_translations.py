"""Tests: Übersetzungs-Key-Bäume paritätisch (REQ-HOM-107, Fund N-10).

``strings.json`` ist der Master; ``translations/de.json`` und
``translations/en.json`` sind Ableitungen. REQ-HOM-107(b) verlangt, dass die
verschachtelten Key-Bäume in allen drei Dateien identisch sind — nur die Werte
dürfen sprachlich abweichen (keys-only-Vergleich).

Reiner JSON-Datei-Test: kein Home-Assistant-Import nötig.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "health_o_mat"
_MASTER = _COMPONENT_DIR / "strings.json"
_TRANSLATIONS = {
    "de": _COMPONENT_DIR / "translations" / "de.json",
    "en": _COMPONENT_DIR / "translations" / "en.json",
}

# Sektionen, die REQ-HOM-107 explizit fordert (deckt config/options/services ab).
_REQUIRED_SECTIONS = ("config", "options", "services")


def _load(path: Path) -> dict:
    """JSON-Objekt laden; die Wurzel muss ein Objekt sein."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict), f"{path}: Wurzel ist kein JSON-Objekt"
    return data


def _all_paths(node: object, prefix: str = "") -> set[str]:
    """Alle Pfade (Knoten UND Blätter) als ``a.b.c``-Strings.

    Knoten werden mitgezählt, damit auch ein leeres Objekt (``"x": {}``) gegen
    ein fehlendes ``x`` als Abweichung erkannt wird.
    """
    paths: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{prefix}.{key}" if prefix else key
            paths.add(child)
            paths |= _all_paths(value, child)
    return paths


def _first_divergence(master: dict, other: dict) -> str | None:
    """None wenn die Key-Bäume gleich sind, sonst Meldung mit erstem Pfad."""
    master_paths = _all_paths(master)
    other_paths = _all_paths(other)
    if master_paths == other_paths:
        return None

    missing = sorted(master_paths - other_paths)
    extra = sorted(other_paths - master_paths)
    parts = []
    if missing:
        parts.append("fehlt: " + ", ".join(missing[:5]))
    if extra:
        parts.append("überzählig: " + ", ".join(extra[:5]))
    first = min(missing + extra)
    return f"erste Abweichung bei {first!r} ({'; '.join(parts)})"


@pytest.mark.parametrize("lang", sorted(_TRANSLATIONS))
def test_req_hom_107_key_tree_parity(lang: str) -> None:
    """[REQ-HOM-107] Key-Baum von translations/<lang>.json ≡ strings.json (keys-only)."""
    master = _load(_MASTER)
    other = _load(_TRANSLATIONS[lang])
    divergence = _first_divergence(master, other)
    assert divergence is None, f"translations/{lang}.json weicht von strings.json ab — {divergence}"


@pytest.mark.parametrize("lang", sorted(_TRANSLATIONS))
def test_req_hom_107_required_sections_present(lang: str) -> None:
    """[REQ-HOM-107] config/options/services in strings.json und <lang>.json vorhanden."""
    master = _load(_MASTER)
    other = _load(_TRANSLATIONS[lang])
    for section in _REQUIRED_SECTIONS:
        assert section in master, f"strings.json: Sektion {section!r} fehlt"
        assert section in other, f"translations/{lang}.json: Sektion {section!r} fehlt"


def test_req_hom_107_parity_helper_detects_divergence() -> None:
    """[REQ-HOM-107] Meta: der Paritäts-Helfer erkennt echte Abweichungen.

    Sichert zu, dass der Paritätstest nicht blind grün ist: fehlende,
    überzählige und leere-Objekt-Abweichungen werden alle benannt.
    """
    master = {"services": {"add_drink": {"name": "Add drink"}}}

    assert _first_divergence(master, master) is None

    missing = {"services": {}}
    assert "services.add_drink" in _first_divergence(master, missing)

    extra = {"services": {"add_drink": {"name": "Add drink"}, "bogus": {"name": "x"}}}
    assert "services.bogus" in _first_divergence(master, extra)

    # Leeres Objekt gegen fehlenden Schlüssel (nicht nur Blatt-Pfade).
    assert "a.b" in _first_divergence({"a": {}}, {"a": {"b": {}}})


def test_set_wellbeing_service_documented_in_all_translations() -> None:
    """Der Service `set_wellbeing` ist in Master + beiden Sprachen vollständig."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        data = _load(path)
        block = data["services"]["set_wellbeing"]
        assert block["name"], f"{path}: name fehlt"
        assert block["description"], f"{path}: description fehlt"
        assert set(block["fields"]) == {"person", "status", "score", "ts"}, (
            f"{path}: Felder weichen ab"
        )


def test_req_hom_120_ts_field_documented_for_all_write_services() -> None:
    """[REQ-HOM-120] `ts` ist in Master + beiden Sprachen vollständig beschrieben."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        data = _load(path)
        for service in ("add_drink", "add_blood_pressure", "set_wellbeing"):
            field = data["services"][service]["fields"]["ts"]
            assert field["name"], f"{path}: {service}.ts.name fehlt"
            assert field["description"], f"{path}: {service}.ts.description fehlt"


def test_m2b_void_and_restore_services_documented_in_all_translations() -> None:
    """[M2b] `void_entry`/`restore_entry` sind in Master + beiden Sprachen vollständig."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        data = _load(path)
        for service in ("void_entry", "restore_entry"):
            block = data["services"][service]
            assert block["name"], f"{path}: {service}.name fehlt"
            assert block["description"], f"{path}: {service}.description fehlt"
            assert set(block["fields"]) == {"person", "kind", "id"}, (
                f"{path}: {service}-Felder weichen ab"
            )
        assert set(data["services"]["remove_last_entry"]["fields"]) == {"person", "kind"}


def test_m2c_restore_backup_service_documented_in_all_translations() -> None:
    """[M2c] `restore_backup` ist in Master + beiden Sprachen vollständig."""
    expected_fields = {
        "filename",
        "mode",
        "persons",
        "datasets",
        "from",
        "to",
        "person_map",
        "dry_run",
        "confirm",
        "restore_audit",
    }
    for path in (_MASTER, *_TRANSLATIONS.values()):
        data = _load(path)
        block = data["services"]["restore_backup"]
        assert block["name"], f"{path}: restore_backup.name fehlt"
        assert block["description"], f"{path}: restore_backup.description fehlt"
        assert set(block["fields"]) == expected_fields, f"{path}: Felder weichen ab"
        for field in expected_fields:
            assert block["fields"][field]["name"], f"{path}: {field}.name fehlt"
            assert block["fields"][field]["description"], f"{path}: {field}.description fehlt"


# --- REQ-HOM-117: HA-native UI translations (common) -----------------------

_UI_JS_FILES = (
    "health-o-mat-panel-base.js",
    "health-o-mat-panel-views.js",
    "health-o-mat-panel-admin.js",
    "health-o-mat-panel.js",
    "health-o-mat-card.js",
)
_UI_KEY_LITERAL_RE = re.compile(r"""["'`](ui_[a-z0-9_]+)["'`]""")


def _common(path: Path) -> dict[str, str]:
    common = _load(path).get("common")
    assert isinstance(common, dict), f"{path}: Sektion 'common' fehlt"
    return common


def test_req_hom_117_common_keys_parity_and_non_empty() -> None:
    """[REQ-HOM-117] de/en haben exakt die Master-Keys, alle Werte nicht leer."""
    master = _common(_MASTER)
    assert master, "strings.json: common ist leer"

    for lang, path in sorted(_TRANSLATIONS.items()):
        other = _common(path)
        assert set(other) == set(master), (
            f"translations/{lang}.json: common-Keys weichen ab "
            f"(fehlt: {sorted(set(master) - set(other))[:5]}, "
            f"überzählig: {sorted(set(other) - set(master))[:5]})"
        )
        empty = sorted(key for key, value in other.items() if not str(value).strip())
        assert not empty, f"translations/{lang}.json: leere common-Werte: {empty[:5]}"


def test_req_hom_117_placeholders_match_between_languages() -> None:
    """[REQ-HOM-117] Beide Sprachen nutzen dieselben `{platzhalter}`."""
    placeholder_re = re.compile(r"\{([A-Za-z0-9_]+)\}")
    de = _common(_TRANSLATIONS["de"])
    en = _common(_TRANSLATIONS["en"])
    for key, en_text in en.items():
        assert set(placeholder_re.findall(en_text)) == set(placeholder_re.findall(de[key])), (
            f"{key}: Platzhalter weichen zwischen de und en ab"
        )


def test_req_hom_117_every_js_key_exists_in_both_languages() -> None:
    """[REQ-HOM-117] Jeder in www/*.js referenzierte Key existiert in de UND en."""
    component = Path(__file__).resolve().parent.parent / "custom_components" / "health_o_mat"
    used: set[str] = set()
    for name in _UI_JS_FILES:
        text = (component / "www" / name).read_text(encoding="utf-8")
        for match in _UI_KEY_LITERAL_RE.finditer(text):
            key = match.group(1)
            # Dynamic prefixes like `ui_common_wb_${key}` are not literals.
            if key.endswith("_"):
                continue
            used.add(key)

    assert used, "keine ui_-Keys in den JS-Modulen gefunden"
    de = _common(_TRANSLATIONS["de"])
    en = _common(_TRANSLATIONS["en"])
    missing_de = sorted(used - set(de))
    missing_en = sorted(used - set(en))
    assert not missing_de, f"fehlende de-Keys: {missing_de}"
    assert not missing_en, f"fehlende en-Keys: {missing_en}"


# --- M3d: Erinnerungen/Wochenbericht (REQ-HOM-118) -------------------------

_NOTIFICATION_FIELDS = {
    "reminders_enabled",
    "reminder_time",
    "reminder_days",
    "reminder_notify_service",
    "reminder_quiet_start",
    "reminder_quiet_end",
    "reminder_drink_goal",
    "reminder_no_drink_hours",
    "reminder_bp_days",
    "reminder_wellbeing_days",
    "weekly_report_enabled",
    "weekly_report_day",
    "weekly_report_time",
    "weekly_report_notify_service",
}


def test_m3d_weekly_report_service_documented_in_all_translations() -> None:
    """[REQ-HOM-118] `weekly_report` ist in Master + beiden Sprachen vollständig."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        block = _load(path)["services"]["weekly_report"]
        assert block["name"], f"{path}: weekly_report.name fehlt"
        assert block["description"], f"{path}: weekly_report.description fehlt"
        assert set(block["fields"]) == {"person"}, f"{path}: Felder weichen ab"
        assert block["fields"]["person"]["name"]
        assert block["fields"]["person"]["description"]


def test_m3d_notifications_options_step_documented_in_all_translations() -> None:
    """[REQ-HOM-118] Der Notifications-Schritt ist in allen drei Dateien gleich."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        step = _load(path)["options"]["step"]["notifications"]
        assert step["title"]
        assert step["description"]
        assert set(step["data"]) == _NOTIFICATION_FIELDS, f"{path}: data-Keys weichen ab"
        assert set(step["data_description"]) == _NOTIFICATION_FIELDS, (
            f"{path}: data_description-Keys weichen ab"
        )
        empty = [key for key, value in step["data"].items() if not str(value).strip()]
        assert not empty, f"{path}: leere Labels: {empty}"
