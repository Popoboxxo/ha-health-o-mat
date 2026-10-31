"""Tests: Übersetzungs-Key-Bäume paritätisch (REQ-HOM-107, Fund N-10).

``strings.json`` ist der Master; ``translations/de.json`` und
``translations/en.json`` sind Ableitungen. REQ-HOM-107(b) verlangt, dass die
verschachtelten Key-Bäume in allen drei Dateien identisch sind — nur die Werte
dürfen sprachlich abweichen (keys-only-Vergleich).

Reiner JSON-Datei-Test: kein Home-Assistant-Import nötig.
"""

from __future__ import annotations

import importlib.util
import json
import re
import types
from pathlib import Path

import pytest
import yaml

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
        assert set(step["data"]) == _NOTIFICATION_FIELDS | {"skip"}, f"{path}: data-Keys weichen ab"
        assert set(step["data_description"]) == _NOTIFICATION_FIELDS, (
            f"{path}: data_description-Keys weichen ab"
        )
        empty = [key for key, value in step["data"].items() if not str(value).strip()]
        assert not empty, f"{path}: leere Labels: {empty}"


# --- M3e: Options-Menü (REQ-HOM-119) ---------------------------------------

_OPTIONS_MENU_STEPS = (
    "basics",
    "drinks",
    "wellbeing",
    "notifications",
    "defaults",
    "summary",
)
_OPTIONS_SECTIONS_WITH_SKIP = ("basics", "drinks", "wellbeing", "notifications")


def test_m3e_options_menu_steps_documented_in_all_translations() -> None:
    """[REQ-HOM-119] Menü-Labels und Schritt-Titel sind in allen Dateien vorhanden."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        steps = _load(path)["options"]["step"]
        missing = [step for step in _OPTIONS_MENU_STEPS if not steps.get(step, {}).get("title")]
        assert not missing, f"{path}: Titel fehlen für {missing}"
        menu_labels = steps["init"].get("menu_options", {})
        assert set(menu_labels) == set(_OPTIONS_MENU_STEPS), f"{path}: menu_options weichen ab"
        empty = [step for step, label in menu_labels.items() if not str(label).strip()]
        assert not empty, f"{path}: leere Menü-Labels: {empty}"


def test_m3e_skip_documented_for_optional_sections() -> None:
    """[REQ-HOM-119] Alle optionalen Abschnitte dokumentieren den `skip`-Schalter."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        steps = _load(path)["options"]["step"]
        for step_id in _OPTIONS_SECTIONS_WITH_SKIP:
            label = steps[step_id]["data"].get("skip")
            assert label and str(label).strip(), f"{path}: {step_id}.skip fehlt"


def test_m3e_summary_documents_changes_placeholder() -> None:
    """[REQ-HOM-119] Die Zusammenfassung zeigt `{changes}` in allen drei Dateien."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        description = _load(path)["options"]["step"]["summary"]["description"]
        assert "{changes}" in description, f"{path}: summary.description ohne {{changes}}"


def test_m3e_defaults_step_has_description_in_all_translations() -> None:
    """[REQ-HOM-119] „Defaults übernehmen" ist in allen drei Dateien beschrieben."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        description = _load(path)["options"]["step"]["defaults"]["description"]
        assert description and str(description).strip(), f"{path}: defaults.description fehlt"


# --- Placeholder-Hygiene (0.14.1) ------------------------------------------

_PLACEHOLDER = re.compile(r"\{[^}]*\}")
_VALID_PLACEHOLDER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _flatten_strings(node: object, prefix: str = "") -> dict[str, str]:
    """Alle String-Blätter als ``pfad -> wert`` (nur Strings)."""
    out: dict[str, str] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str):
                out[child] = value
            elif isinstance(value, dict):
                out.update(_flatten_strings(value, child))
    return out


def _placeholders(value: str) -> set[str]:
    """Menge der `{...}`-Inhalte (auch ungültige, z. B. ``{Quelle: …}``)."""
    return {match.group(0)[1:-1] for match in _PLACEHOLDER.finditer(value)}


def test_all_translation_placeholders_are_valid_identifiers() -> None:
    """HA erlaubt in Übersetzungen nur `{identifier}`-Platzhalter.

    Fängt insbesondere versehentliche Doku-Klammern wie `{Quelle: Ziel-ID}` ab,
    die HA als Platzhalter interpretiert und die Validierung brechen lässt.
    """
    for path in (_MASTER, *_TRANSLATIONS.values()):
        for key, value in _flatten_strings(_load(path)).items():
            for placeholder in _placeholders(value):
                assert _VALID_PLACEHOLDER.fullmatch(placeholder), (
                    f"{path}: ungültiger Platzhalter {{{placeholder}}} bei {key!r}"
                )


def test_translation_placeholders_match_across_languages() -> None:
    """Lokalisierte Strings müssen dieselben Platzhalter wie der Master nutzen.

    HA validiert die Platzhalter der Übersetzung gegen den englischen Master;
    eine Abweichung (z. B. `{Quelle}` vs. `{source}`) erzeugt Laufzeitfehler.
    """
    master = _flatten_strings(_load(_MASTER))
    for lang, path in _TRANSLATIONS.items():
        other = _flatten_strings(_load(path))
        for key, value in other.items():
            expected = _placeholders(master.get(key, ""))
            actual = _placeholders(value)
            assert actual == expected, (
                f"translations/{lang}.json: Platzhalter bei {key!r} weichen ab: "
                f"{sorted(actual)} != {sorted(expected)}"
            )


# --- Laborwerte (REQ-HOM-122) ----------------------------------------------

_LAB_SERVICE_FIELDS = {
    "add_lab_value": {"person", "marker", "value", "unit", "ts", "report_ref"},
    "add_lab_report": {"person", "values", "ts", "report_ref"},
    "remove_last_lab_value": {"person", "marker"},
    "remove_lab_report": {"person", "ts", "report_ref"},
}

# Minimal-Override-Konvention (wie `add_blood_pressure`): in den JSON-Dateien
# stehen nur die Felder, deren Text übersetzt wird — nicht zwingend alle
# Felder aus `services.yaml`.
_LAB_TRANSLATED_FIELDS = {
    "add_lab_value": {"marker", "unit", "ts", "report_ref"},
    "add_lab_report": {"values", "ts", "report_ref"},
    "remove_last_lab_value": {"marker"},
    "remove_lab_report": {"ts", "report_ref"},
}


def test_req_hom_122_lab_services_have_translation_parity() -> None:
    """[REQ-HOM-122] Laborwert-Services sind in services.yaml + allen Übersetzungen."""
    services_yaml = yaml.safe_load((_COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8"))

    for service, expected_fields in _LAB_SERVICE_FIELDS.items():
        assert service in services_yaml, f"services.yaml: {service} fehlt"
        assert set(services_yaml[service]["fields"]) == expected_fields, (
            f"services.yaml: {service}-Felder weichen ab"
        )

    for path in (_MASTER, *_TRANSLATIONS.values()):
        data = _load(path)
        for service, translated_fields in _LAB_TRANSLATED_FIELDS.items():
            block = data["services"][service]
            assert block["name"], f"{path}: {service}.name fehlt"
            assert block["description"], f"{path}: {service}.description fehlt"
            assert set(block["fields"]) == translated_fields, f"{path}: {service}-Felder weichen ab"
            for field, meta in block["fields"].items():
                assert meta["name"], f"{path}: {service}.{field}.name fehlt"
                assert meta["description"], f"{path}: {service}.{field}.description fehlt"


# --- Laborwert-Entity-Namen (REQ-HOM-122) ----------------------------------

# Master + en.json sind englisch, de.json deutsch. `const.py` hat keine
# Home-Assistant-Abhängigkeit und wird deshalb direkt aus der Datei geladen.
_LAB_NAME_FIELDS = (
    (_MASTER, "name_en"),
    (_TRANSLATIONS["en"], "name_en"),
    (_TRANSLATIONS["de"], "name_de"),
)


def _load_const() -> types.ModuleType:
    """`const.py` ohne Paket-Import laden (bleibt HA-frei)."""
    spec = importlib.util.spec_from_file_location(
        "_hom_const_translations", _COMPONENT_DIR / "const.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_req_hom_122_lab_sensor_names_cover_every_catalog_marker() -> None:
    """[REQ-HOM-122] Jeder Katalog-Marker hat seinen Sensor-Namen in allen Dateien.

    Die Texte stammen verbindlich aus ``LAB_MARKERS[*]["name_de"/"name_en"]``;
    der Test fängt sowohl fehlende/überzählige Keys als auch Abweichungen von
    der Single Source of Truth ab.
    """
    const = _load_const()
    expected = {f"lab_{marker_key}" for marker_key in const.LAB_MARKERS}

    for path, name_field in _LAB_NAME_FIELDS:
        sensor = _load(path)["entity"]["sensor"]
        actual = {key for key in sensor if key.startswith("lab_")}
        assert actual == expected, (
            f"{path}: Sensor-Keys weichen vom Katalog ab "
            f"(fehlt: {sorted(expected - actual)}, überzählig: {sorted(actual - expected)})"
        )
        for marker_key, marker_def in const.LAB_MARKERS.items():
            key = f"lab_{marker_key}"
            assert sensor[key]["name"] == marker_def[name_field], (
                f"{path}: {key}.name != LAB_MARKERS[{marker_key!r}][{name_field!r}]"
            )


def test_req_hom_122_lab_warnings_cover_every_non_other_category() -> None:
    """[REQ-HOM-122] Je Nicht-``other``-Kategorie existiert die Warn-Entity.

    ``other`` bleibt bewusst ohne binary_sensor (dort liegen nur
    nutzerdefinierte Marker), deshalb prüft die Key-Menge auf Abwesenheit.
    """
    const = _load_const()
    warnings = [category for category in const.LAB_CATEGORIES if category["key"] != "other"]
    expected = {f"lab_warning_{category['key']}" for category in warnings}

    for path, name_field in _LAB_NAME_FIELDS:
        binary_sensor = _load(path)["entity"]["binary_sensor"]
        actual = {key for key in binary_sensor if key.startswith("lab_warning_")}
        assert actual == expected, (
            f"{path}: Warn-Keys weichen von den Kategorien ab "
            f"(fehlt: {sorted(expected - actual)}, überzählig: {sorted(actual - expected)})"
        )
        for category in warnings:
            key = f"lab_warning_{category['key']}"
            suffix = "-Warnung" if name_field == "name_de" else " warning"
            expected_name = f"{category[name_field]}{suffix}"
            assert binary_sensor[key]["name"] == expected_name, (
                f"{path}: {key}.name != '{expected_name}'"
            )


# --- Laborwert-UI-Texte im Web-Panel (REQ-HOM-122) -------------------------

# Statische Liste der in `www/health-o-mat-panel-*.js` per `t("<key>", …)`
# referenzierten Laborwert-Texte. Der dynamische Test
# `test_req_hom_117_every_js_key_exists_in_both_languages` prüft zusätzlich,
# dass kein weiterer Key verwendet wird, ohne übersetzt zu sein.
_REQ_HOM_122_UI_KEYS = (
    "ui_admin_lab_title",
    "ui_admin_lab_ref_title",
    "ui_admin_lab_category",
    "ui_admin_lab_marker",
    "ui_admin_lab_unit",
    "ui_admin_lab_range",
    "ui_admin_lab_reset",
    "ui_admin_lab_hide_title",
    "ui_admin_lab_custom_title",
    "ui_admin_lab_custom_name",
    "ui_admin_lab_custom_unit",
    "ui_admin_lab_custom_category",
    "ui_admin_lab_custom_range",
    "ui_admin_lab_custom_alt_unit",
    "ui_admin_lab_custom_alt_unit_name",
    "ui_admin_lab_custom_alt_factor",
    "ui_admin_lab_custom_submit",
    "ui_admin_lab_feedback",
    "ui_panel_lab_reported_as",
    "ui_panel_chart_lab_empty",
    "ui_panel_tab_labs",
    "ui_panel_lab_prev",
    "ui_panel_lab_next",
    "ui_panel_lab_no_categories",
    "ui_panel_lab_add_value",
    "ui_panel_lab_marker",
    "ui_panel_lab_value_field",
    "ui_panel_lab_unit_field",
    "ui_panel_lab_report_ref",
    "ui_panel_lab_save",
    "ui_panel_tile_lab_warning",
    "ui_panel_tile_lab_ok",
    "ui_panel_lab_threshold_title",
    "ui_panel_val_lab_value",
)


def test_req_hom_122_common_ui_keys_exist_in_all_three_files() -> None:
    """[REQ-HOM-122] Laborwert-UI-Texte stehen in Master, de und en."""
    for path in (_MASTER, *_TRANSLATIONS.values()):
        common = _common(path)
        missing = [key for key in _REQ_HOM_122_UI_KEYS if key not in common]
        assert not missing, f"{path}: fehlende Laborwert-UI-Keys: {missing}"
        empty = [key for key in _REQ_HOM_122_UI_KEYS if not str(common[key]).strip()]
        assert not empty, f"{path}: leere Laborwert-UI-Werte: {empty}"


def test_req_hom_122_labs_area_label_translated() -> None:
    """[REQ-HOM-122] Die vierte Fläche hat ein eigenes Label in Master + de + en."""
    expected = {
        "strings.json": "Lab values",
        "de.json": "Laborwerte",
        "en.json": "Lab values",
    }
    for filename, value in expected.items():
        path = _MASTER if filename == "strings.json" else _TRANSLATIONS[filename[:2]]
        common = _common(path)
        assert common.get("ui_common_area_labs") == value, (
            f"{filename}: ui_common_area_labs fehlt oder ist falsch"
        )
