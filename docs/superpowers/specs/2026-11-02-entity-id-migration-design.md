# Spec: Entity-ID-Migration auf sprachunabhängige `object_id`s (MINOR 0.17.0)

- **Status:** APPROVED (2026-11-02) — Review Runde 2 abgeschlossen
- **Datum:** 2026-11-02 · **Angepasst:** 2026-11-02 (§2.3, §3.1–§3.5, §5.3,
  §6.1–§6.2, §7 und §8.2 an den gefixten `device_slug`-Resolver; produktive
  Regression Caro/Daniel)
- **Basis:** `main` @ `d86b247` (manifest `0.16.2`), ConfigFlow `VERSION = 2`
- **Grundlage:** `docs/reviews/entity-id-stability-audit.md` (im Folgenden „Audit")
- **Produktentscheidung (verbindlich):** Variante **B** aus Audit §5 — der Bestand wird
  migriert, damit am Ende alle `object_id`s demselben stabilen, sprachunabhängigen
  Schema folgen. Die `entity_id`-Änderung ist ein Bruch, wird aber bewusst als
  **MINOR** (`0.17.0`) veröffentlicht — Begründung und Konsequenz in §5.4.
  Ausdrückliche Auflage: Die Migration **muss auf dem geteilten Testsystem
  `/home/hermes/ha-test` getestet werden** (Teststrategie §6).
- **Nicht verhandelbar:** `unique_id` wird **nie** geändert; geändert wird ausschließlich
  `entity_id` (`new_entity_id`). Der Verlauf bleibt erhalten.

## 0. Zitat-Abgleich (Audit → Code, Stand `d86b247`)

Alle tragenden Audit-Zitate wurden gegen den Code geprüft. Korrekturen/Präzisierungen:

| Audit-Stelle | Befund | Korrektur in dieser Spec |
|---|---|---|
| §1 „`has_entity_name` zentral (`entity.py:31`)" | tatsächlich `entity.py:32` (`self._attr_has_entity_name = True`) | `entity.py:32` |
| §2 QuickDrinkButton `button.py:64-82` | Klasse 64-71, `__init__` 75-83, `_attr_name` 82, `async_press` 85-86 | `button.py:64-86` |
| §3a „keine vergleichbare Absicherung für `LAB_CATEGORIES`" | doch vorhanden: `tests/test_translations.py:478-501` prüft `lab_warning_<kategorie>` in Master + `de`/`en` inkl. Namensgleichheit | A-3 reduziert sich auf `WELLBEING_STATES` → `report_*` |
| §5 B-1 „Device-Slug aus aktuellem `entity_id`-Präfix bzw. `slugify(device.name)`" | beide Quellen sind unzuverlässig, wenn der Anzeigename der Person nach der Erstregistrierung geändert wurde | deterministischer Vertrag in §2.3 |
| §2/§5 Ziel „`lab_<key>`" | `key` kann bei Fremd-Clients mit explizitem, nicht-slugifiziertem `key` Sonderzeichen enthalten (`logic.py:1014` lowercased nur) | Ziel nur bei slug-sicherem Key, sonst Skip (§3.5) |

Unverändert bestätigt: `entity.py:34-54` (Override), `button.py:76` (`unique_id`
`{entry_id}_button_quick_{index}`, 0-basiert, Schleife `button.py:29`),
`sensor.py:495-520` (`lab_{marker_key}`, Custom-Pfad `_attr_name` 517, `translation_key`
520), `logic.py:994-1044` (`normalize_lab_custom_markers`, Key 1014-1020, Kategorie 1022),
`const.py:57-62` (`DEFAULT_QUICK_DRINKS`, deutsche Labels), `const.py:115-146`
(`WELLBEING_STATES`), `const.py:175-186` (`LAB_CATEGORIES`, `other` enthalten),
`config_flow.py:250` (`VERSION = 2`), `__init__.py:149-174` (`async_migrate_entry`,
Downgrade-Guard 156), `ws_api.py:1874-1883` (Custom-Marker-Normalisierung),
`restore.py:352-368` (Custom-Marker-Merge), `binary_sensor.py:31-41`/`92-103`
(Kategorie-Warnungen), `tests/test_wave_a.py:179-215`, `tests/test_config_flow.py:105`,
`examples/dashboard.yaml`, `examples/dashboard-mini.yaml`,
`examples/dashboard-mushroom.yaml` (harte alte Quick-Drink-IDs),
`tests/test_dashboards.py:19-68` (`KNOWN_SUFFIXES` mit alten IDs),
`manifest.json:22`, `hacs.json:4` (HA-Minimum `2026.8.0`).

---

## 1. Ziel & Nicht-Ziele

### 1.1 Ziel

Nach der Migration gilt für **jede** Entity der Integration:

1. Die `object_id` ist **sprachunabhängig** (wechselt nicht mit der HA-Systemsprache).
2. Die `object_id` folgt einem **einheitlichen, englisch/ASCII-basierten** Schema.
3. Der **Bestand** ist migriert — nicht nur Neuinstallationen. Ein frisch aufgesetztes
   System und ein migriertes System erzeugen für dieselbe Person **dieselben** IDs.
4. `unique_id`, `original_name`, `device_id`, Store-Inhalt und Verlauf bleiben unverändert.

Die 23 bereits konformen Entity-Klassen (Audit §2: 29 Katalog-Marker, 9 Kategorie-
Warnungen, 10 Wellbeing-Buttons, alle übrigen translation-key-Entities) sind am Ziel
und werden **nicht** angefasst. Migriert werden ausschließlich die zwei Abweichungen:

- **F-1** `QuickDrinkButton` (`unique_id` `{entry_id}_button_quick_{index}`)
- **F-2** Custom-Labor-Marker (`unique_id` `{entry_id}_lab_{key}`, `key ∉ LAB_MARKERS`)

### 1.2 Klarstellung: „englisch" ist für Custom-Marker nicht definierbar

Ein Custom-Labor-Marker hat **keinen englischen Quelltext**: Sein Anzeigename ist
Nutzertext („Vitamin D", „Ferritin gesamt", „Hämoglobin"). „Englisch pinnen" ist hier
semantisch leer. Die eigentlich schützenden Eigenschaften sind:

- **sprachunabhängig** — die ID hängt nicht von der Systemsprache ab (ist bei F-1/F-2
  bereits erfüllt), und
- **stabil** — die ID hängt nicht vom Anzeigenamen ab, sondern nur vom persistenten
  `key`.

Deshalb wird das Ziel für Custom-Marker präzisiert als:

> **`object_id` = ASCII-Slug des stabilen `key`.**

Der `key` ist bereits die Identität der Entity (`unique_id = {entry_id}_lab_{key}`),
wird in `entry.options["lab_custom_markers"]` persistiert und durch A-2 gegen
Fremd-Client-Drift gehärtet. Damit gibt es **genau einen** Identifikator pro Marker
(`key`), nicht zwei (Name-Slug vs. `key`).

### 1.3 Schema-Alternativen für Custom-Marker (Trade-offs)

| Variante | Beispiel (Marker „Vitamin D", Key `vitamin_d`) | Vorteile | Nachteile |
|---|---|---|---|
| **A: `lab_<key>` (empfohlen)** | `sensor.…_lab_vitamin_d` | exakt dieselbe Suffix-Konvention wie die `unique_id` (`{entry_id}_lab_{key}`) → ein Identifikator; identisch zum Katalog-Schema `lab_<marker_key>`; Neuregistrierung und Migration erzeugen dasselbe; lesbar in Automationen | `lab` ist eine englische Abkürzung, aber ein Namensraum und keine Übersetzung des Nutzertexts; theoretische Namespace-Kollision mit einem **künftigen** Katalog-Marker (siehe Risiko R-6) |
| B: `lab_custom_<key>` | `sensor.…_lab_custom_vitamin_d` | trennt Custom- und Katalog-Namensraum sichtbar | weicht vom `unique_id`-Suffix ab (zweiter Name für dieselbe Identität); frisch registrierte Entities müssten ebenfalls `lab_custom_` nutzen, sonst Divergenz; kein Kollisionsgewinn, weil `normalize_lab_custom_markers` Katalog-Keys bereits reserviert |
| C: `lab_custom_<n>` | `sensor.…_lab_custom_3` | kurz, kein Nutzertext | instabil: Index hängt an Listenreihenfolge; Löschen/Hinzufügen verschiebt alle folgenden IDs; kein Bezug zu `key`/`unique_id`; erfordert eine zusätzliche Ordnungs- und Migrationsregel |
| D: Hash `lab_<sha1(key)[:8]>` | `sensor.…_lab_9f2c1a7b` | opak, kaum Kollisionen | in Automationen/Dashboards unlesbar; Hash ändert sich mit dem Key (gleiches Problem wie A, nur ohne Lesbarkeit); zusätzliche Implementierung ohne Nutzen |

**Entscheidung: Variante A (`lab_<key>`).** Begründung: Konsistenz zur `unique_id` ist
die stärkste Stabilitätsgarantie — dieselbe Zeichenkette, die HA nie ändert, bestimmt
das ID-Suffix. B erzeugt eine zweite Konvention; C/D brechen die Kopplung an den
stabilen `key`.

### 1.4 Nicht-Ziele

- Keine Änderung von `unique_id` (irgendeiner Entity).
- Keine Datenmigration im Store (`homeassistant.helpers.storage.Store`) und keine
  Änderung von `STORE_SCHEMA_VERSION`.
- Kein Umbenennen bereits konformer IDs (Katalog-Marker, Kategorie-Warnungen,
  Wellbeing-Buttons, translation-key-Entities). Auch kosmetische Katalog-IDs
  (`…_alt_alt_gpt`) bleiben.
- Keine automatische Anpassung von Nutzer-Automationen, Skripten, Dashboards,
  Szenen oder Helfern (technisch nicht möglich; siehe §5/§7).
- Keine Änderung von `original_name` (der Anzeigename bleibt Nutzertext bzw.
  lokalisierter Name).
- Kein automatisches Löschen von Entities: Durch A-1 können Warn-Entities für
  Fremd-Kategorien aus dem Setup verschwinden (Orphans). Deren Entfernung ist
  ausdrücklich **Post-Release-Cleanup** (§5.5 Schritt 8), nicht Teil der Migration.
- Keine Sprachumschaltung auf der Testinstanz und kein `bin/reset`.

---

## 2. Ziel-Schemata

Beide Zielschemata werden **deterministisch aus der `unique_id`** abgeleitet, nie aus
dem Slug des aktuellen Anzeigenamens.

### 2.1 Quick-Drink-Buttons

| Eigenschaft | Wert |
|---|---|
| Quell-`unique_id` | `{entry_id}_button_quick_{index}` (0-basiert, `button.py:29,76`) |
| Ziel-`object_id` (Entity-Teil) | `quick_drink_{index + 1}` |
| Ziel-`entity_id` | `button.{device_slug}_quick_drink_{index + 1}` |
| `original_name` | unverändert (Label, z. B. „Glas Wasser") |

**Indexbasis: 1-basiert.** Begründung:

- Die Ziel-ID ist ein **nutzerseitiger Vertrag** (Automationen, Dashboards, Skripte).
  `quick_drink_0` liest sich wie ein Off-by-one-Fehler und wird in Support-Fällen
  regelmäßig falsch geraten; `quick_drink_1` ist die naheliegende erste Wahl.
- Die 0-basierte `unique_id` ist eine **interne** Kennung und bleibt unverändert.
  Die Abbildung ist eine reine Funktion `display_index = index + 1`, die durch
  Unit-Tests festgenagelt wird (§6.1) — kein Such- oder Rateverfahren.
- Damit ist die Zuordnung für das Standard-Set eindeutig:

| `unique_id` | bisherige ID (Beispiel) | neue ID (Beispiel) |
|---|---|---|
| `{entry}_button_quick_0` | `button.health_o_mat_max_glas_wasser` | `button.health_o_mat_max_quick_drink_1` |
| `{entry}_button_quick_1` | `button.health_o_mat_max_flasche_wasser` | `button.health_o_mat_max_quick_drink_2` |
| `{entry}_button_quick_2` | `button.health_o_mat_max_tasse_kaffee` | `button.health_o_mat_max_quick_drink_3` |
| `{entry}_button_quick_3` | `button.health_o_mat_max_glas_saft` | `button.health_o_mat_max_quick_drink_4` |

Hinweis: Die bisherigen IDs hängen an den **Labels**; nach einer Label-Änderung bleibt
die registrierte ID stehen (Audit: `…_tasse_kaffee` mit `original_name` „Kaffee").
Deshalb darf die Migration den alten Suffix **nicht** aus dem aktuellen Label
rekonstruieren — nur der Index aus der `unique_id` zählt.

### 2.2 Custom-Labor-Marker

| Eigenschaft | Wert |
|---|---|
| Quell-`unique_id` | `{entry_id}_lab_{key}` mit `key ∉ LAB_MARKERS` |
| Ziel-`object_id` (Entity-Teil) | `lab_{key}` (Bedingung: `key` matcht `^[a-z0-9]+(_[a-z0-9]+)*$`) |
| Ziel-`entity_id` | `sensor.{device_slug}_lab_{key}` |
| `original_name` | unverändert (Nutzertext) |

Beispiele: Key `vitamin_d` → `sensor.…_lab_vitamin_d`; Key `ferritin_gesamt` →
`sensor.…_lab_ferritin_gesamt`; Key `h_moglobin` (ASCII-only-Slug von „Hämoglobin",
`logic.py:972-979`) → `sensor.…_lab_h_moglobin`.

Ist der Key **nicht** slug-sicher (z. B. ein Fremd-Client sendet explizit
`"key": "Vitamin D"`; `logic.py:1014` lowercased nur), wird die Entity **nicht**
migriert (`skip`, Grund `invalid_key`). Eine stille Umformung des Keys ist verboten,
weil sie die `unique_id` nicht ändern darf und ein abweichendes ID-Suffix erzeugen
würde.

### 2.3 `device_slug`-Ermittlung (sound, fail-closed bei echter Mehrdeutigkeit)

`{device_slug}` ist das **aktuell für die Entity-Registrierung verwendete object-id-Präfix**
des Personen-Devices — nicht zwingend `slugify(device.name)`: HA >= 2026.9 kann über
`entity_id_parts` ein Area-Segment voranstellen (Default enthält `AREA`), und der
Device-Name kann nach der Erstregistrierung geändert worden sein.

**Quellen (in dieser Reihenfolge):**

1. **Device-Anker:** `dr.async_get(hass).async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)`
   (HA 2026.9.1; das ältere `async_get_device(identifiers=…)` ist **deprecated**) —
   exakt die Verankerung aus `entity.py:26-31`. Fehlt er, wird die **erste nicht-`None`-
   `device_id` über alle Registry-Entities des Entrys** verwendet (nicht nur
   `entries[0].device_id`). `hint = slugify(device.name_by_user or device.name)`.
2. **Translation-Anker:** ausschließlich Entities mit gesetztem `translation_key`.
   Deren object-id-Suffix stammt aus dem englischen Übersetzungstext und ist **nicht
   nutzertextabhängig**; F-1/F-2-Entities (Quick-Drinks, Custom-Marker) sind
   ausgeschlossen.

**Präfix-Ermittlung auf Token-Ebene:**

- Objekt-Teil jedes Ankers an `_` zerlegen. `C` = **längste führende Token-Folge, die
  mindestens zwei Anker teilen** (z. B. `["health", "o", "mat", "max"]`). Maßgeblich ist
  die Mehrfach-Stützung, nicht „alle": ein einzelner Ausreißer (hand-renamed Entity wie
  `sensor.caro_gewicht`, die kein führendes Token mit den übrigen Ankern teilt) kann `C`
  damit nicht leeren. Zwei verschiedene, **gleich lange und gleich stark gestützte**
  Präfixe → **`device_slug_ambiguous`** (echte Mehrdeutigkeit, kein Raten).
- `P` = längste führende Token-Folge von `C`, die die **Mehrheit der relevanten
  Kandidaten** als Boundary-Präfix fortsetzt (`candidate.startswith(P + "_")`).
  Relevant sind nur Kandidaten mit demselben ersten Token wie `C`; hand-renamed
  Kandidaten (anderes oder kein führendes Token) fließen nicht in die Mehrheit ein.
  Damit werden gemeinsame Entity-Namespaces abgeschnitten: Lab-only (`C = …_max_lab`,
  Kandidaten-IDs aber `…_max_<name>`) ergibt `P = …_max`. Bleibt `P` leer, obwohl Anker
  existieren → `device_slug_ambiguous` (Kandidatenmenge und Anker-Präfix passen nicht
  zusammen).
- **Divergenz-Test:** vergleiche das Token direkt nach `P` **ausschließlich über die
  stützenden Anker** (Anker, deren Objekt-Teil `P` ist oder mit `P + "_"` beginnt).
  Für den Test sind mindestens **zwei** Anker nötig; weniger als zwei Translation-Anker
  → `device_slug_unresolved`.
  - **divergiert** (`drinks_today` vs `daily_goal_progress`): `P` ist die Gerätegrenze.
  - **nicht divergiert** (`lab_crp` vs `lab_creatinine` → beide `lab`): `P` ist nicht
    als Gerätegrenze belegt. Ohne Hint → **`device_slug_unresolved`**; mit Hint
    entscheidet die Boundary-Regel.
- **Hint-Auflösung** (Hint hat Vorrang, wenn er in Boundary-Beziehung zu `P` steht):
  - `P == H` → verwende `H`.
  - `P.startswith(H + "_")` → verwende `H` (gemeinsame Entity-Tokens wie `lab`
    werden abgeschnitten).
  - `P.endswith("_" + H)` → verwende `P` (Area-Segment vor dem Device-Segment bleibt
    Teil der IDs).
  - sonst → **`device_slug_ambiguous`**.
- **Akzeptanz:** Ergebnis nicht leer, matcht `^[a-z0-9_]+$`, und wird von **mindestens
  zwei Ankern gestützt** (bzw. vom Hint, wenn dieser die Boundary belegt); alle
  Kandidaten gehören zur selben `device_id` wie der Device-Anker (falls vorhanden).
  Es ist **nicht** mehr gefordert, dass **alle** Registry-Entities mit dem Präfix
  beginnen: ein Kandidat außerhalb des Präfixes ist eine Nutzerentscheidung und wird mit
  dem **nicht blockierenden** Grund `custom_entity_id` übersprungen (§3.1). Bleibt eine
  der Bedingungen verletzt → `device_slug_ambiguous`.

**Ergebnis:** akzeptierter Präfix. Sonst:

- keine Kandidaten, keine verwendbaren Translation-Anker (weniger als zwei) oder
  fehlende Divergenz ohne Hint → **`device_slug_unresolved`**;
- leeres `C`/`P` (kein von mindestens zwei Ankern geteilter Präfix), zwei gleichwertige
  Anker-Cluster, Widerspruch zwischen Hint und Anker-Präfix oder fremde `device_id` →
  **`device_slug_ambiguous`**.

Beide Gründe sind **blockierende** Skip-Gründe; die Version bleibt stehen (fail-closed).
Davon getrennt ist `custom_entity_id` (Kandidat außerhalb des Präfixes) eine
**Warnung ohne Fehlschlag**: Die Version wird gesetzt, der Grund steht in
`NON_BLOCKING_SKIP_REASONS` und ist vom Drift-Check ausgenommen (§3.1, §3.2, §3.3).

Damit ist der frühere, unsounde „gemeinsamer Präfix über alle IDs"-Fallback ersetzt:
Bei vier Labels „Glas Wasser"/„Glas Saft"/„Glas Tee"/„Glas Kaffee" wäre der naive Präfix
`…_glas` (und die Selbstprüfung „alle Kandidaten beginnen damit" per Konstruktion
erfüllt); nach einem Teil-Lauf änderte sich der Präfix erneut. Nutzertext-Suffixe
fließen nicht mehr ein — das Gegenbeispiel ist als Unit-Test festgehalten (§6.1).
Der Lab-only-Fall (nur `lab_<marker>` + `lab_warning_<kategorie>` als Anker) ist
dadurch ebenfalls abgedeckt: mit Hint wird der Hint akzeptiert, ohne Hint
`device_slug_unresolved` — nie ein geratenes `…_lab`.

**Regression (produktiv, 2026-11-02):** Auf der produktiven Instanz hatte ein Nutzer
eine Entity der Person „Caro" manuell in `sensor.caro_gewicht` umbenannt. Nach der
alten Regel (gemeinsamer Präfix über **alle** Anker, Akzeptanz über **jede**
Registry-Entity) teilte dieser Ausreißer kein führendes Token mit den übrigen Ankern;
`C` und damit `P` blieben leer, und alle Quick-Drink-Buttons beider betroffener Entries
(„Caro" und „Daniel") liefen in `device_slug_ambiguous` mit Ziel `None` — beide Entries
blieben auf Version 2, obwohl nur eine einzige Entity betroffen war. Nach dem Fix
stützen mindestens zwei Anker `C` (der Ausreißer zählt nicht), `P` wird über die
Mehrheit der relevanten Kandidaten getrimmt, Divergenz und Akzeptanz prüfen nur
stützende Anker, und die hand-renamed Entity erhält die Warnung `custom_entity_id`;
beide Entries migrieren auf Version 3. Die Regression ist in §6.1/§6.2 als Unit- und
Registry-Test festgehalten.

`device_slug` wird **nur zur Migrationszeit** berechnet. Neu registrierte Entities
brauchen ihn nicht: HA präfixt bei `has_entity_name = True` weiterhin selbst den
Device-Namen.

### 2.4 Pinning für Neuregistrierungen (Voraussetzung, nicht optional)

Die Migration würde sonst nur den Bestand umbenennen, während eine später neu
angelegte Entity (z. B. nach Löschen der Registry-Entity oder auf einer frischen
Installation) wieder die alte, namensbasierte ID bekäme. Deshalb gehören die
folgenden Overrides **in denselben Plan** (Audit A-5):

```python
class QuickDrinkButton(HealthOMatButton):
    def __init__(self, coordinator, entry, store, index: int) -> None:
        ...
        self._index = index  # zusätzlich zu self._label/_ml/_icon

    @property
    def suggested_object_id(self) -> str | None:
        # Nur der Entity-Teil; HA präfixt den Device-Namen (has_entity_name).
        return f"quick_drink_{self._index + 1}"
```

```python
class LabValueSensor(HealthOMatSensor):
    @property
    def suggested_object_id(self) -> str | None:
        if self._marker_def.get("is_custom"):
            return f"lab_{self._marker_key}"
        return super().suggested_object_id  # Katalog: base-Pinning aus entity.py:34-54
```

`_attr_name` bleibt in beiden Klassen unverändert (Anzeige). Der Override liefert
**nur** den Entity-Teil — kein Device-Präfix (sonst Doppelpräfix), keine
`_attr_name`-Ableitung. HA wendet `suggested_object_id` ausschließlich bei der
Erstregistrierung an; bestehende Registry-Einträge bleiben unberührt (deshalb ist
§3 nötig).

### 2.5 Warum Ableitung aus `unique_id` (und nicht aus Slug-Tabellen)

ha-go-gauge (Audit §4) migriert über eine statische `ENTITY_ID_MIGRATION`-Tabelle, die
konkrete `object_id`-Strings ersetzt. Das ist fragil: Sie bricht bei umbenannten
Labels, übersetzten Namen, geänderten Device-Namen und neuen Slots und muss bei jeder
Textänderung gepflegt werden. Hier gilt stattdessen:

- `unique_id` ist die von HA garantierte, unveränderliche Identität.
- `{entry_id}_button_quick_{n}` enthält den Slot-Index; `{entry_id}_lab_{key}` enthält
  den Marker-Key — beides sind **totale Funktionen** auf die Ziel-ID.
- Die Migration ist damit unabhängig von Sprache, Label-Änderungen und
  Transliterationen und auf jedem System reproduzierbar.

---

## 3. Migration (ConfigFlow `VERSION 2 → 3`)

### 3.1 Bausteine

Neu: `custom_components/health_o_mat/migration.py` — **HA-frei** (kein
`homeassistant`-Import), vollständig unit-testbar (Projektregel „Logik in HA-freie
Module", Audit go-gauge-Punkt 4).

Öffentlicher Vertrag:

```python
SKIP_DEVICE_SLUG_UNRESOLVED = "device_slug_unresolved"
SKIP_DEVICE_SLUG_AMBIGUOUS = "device_slug_ambiguous"
SKIP_TARGET_OCCUPIED = "target_occupied"
SKIP_INVALID_KEY = "invalid_key"
# Nutzer hat die entity_id selbst gewählt (Kandidat außerhalb des Anker-Präfixes):
# seine Entscheidung gewinnt, kein Fehlschlag.
SKIP_CUSTOM_ENTITY_ID = "custom_entity_id"

# Gründe, die den Pass NICHT blockieren: die Version wird trotzdem gesetzt.
NON_BLOCKING_SKIP_REASONS = frozenset({SKIP_CUSTOM_ENTITY_ID})

@dataclass(frozen=True)
class DeviceSlugResolution:
    slug: str | None
    reason: str | None   # None = akzeptiert; sonst ein SKIP_DEVICE_SLUG_*-Grund

@dataclass(frozen=True)
class MigrationRename:
    unique_id: str
    source_entity_id: str
    target_entity_id: str

@dataclass(frozen=True)
class MigrationSkip:
    unique_id: str
    source_entity_id: str
    target_entity_id: str | None
    reason: str          # SKIP_*-Grund; in NON_BLOCKING_SKIP_REASONS = kein Fehlschlag

@dataclass(frozen=True)
class MigrationPlan:
    device_slug: str | None        # aufgelöstes object-id-Präfix (None bei Skip)
    renames: tuple[MigrationRename, ...]
    skipped: tuple[MigrationSkip, ...]

def quick_drink_target(device_slug: str, index: int) -> str:
    """Object-ID-Teil ohne Domain: f"{device_slug}_quick_drink_{index + 1}"."""

def custom_lab_target(device_slug: str, key: str) -> str:
    """Object-ID-Teil ohne Domain: f"{device_slug}_lab_{key}"."""

def parse_quick_drink_index(unique_id: str, entry_id: str) -> int | None:
    """None, wenn die unique_id nicht exakt {entry_id}_button_quick_<n> ist."""

def parse_custom_lab_key(
    unique_id: str, entry_id: str, catalog_keys: Collection[str]
) -> str | None:
    """None für Katalog-Keys, fremde Entry-IDs und nicht passende unique_ids."""

def resolve_device_slug(
    candidates: Sequence[Mapping[str, Any]],   # {"entity_id", "device_id"}
    anchors: Sequence[Mapping[str, Any]],      # {"entity_id", "translation_key", "device_id"}
    *,
    hint: str | None,
    device_id: str | None,
) -> DeviceSlugResolution:
    """Vertrag aus §2.3; liest nur Objekt-Teile der Translation-Anker."""

def build_migration_plan(
    entry_id: str,
    entities: Sequence[Mapping[str, Any]],   # entity_id, unique_id, translation_key, device_id
    *,
    device_slug_hint: str | None,
    device_id: str | None,
    catalog_keys: Collection[str],
    occupied_entity_ids: Collection[str],
) -> MigrationPlan:
    """Reine Planung: keine HA-Aufrufe, keine Seiteneffekte, stabile Reihenfolge."""
```

Regeln von `build_migration_plan`:

1. `entities` und `occupied_entity_ids` werden materialisiert (Reihenfolge =
   Eingabereihenfolge, für deterministische Tests).
2. Kandidaten sind Entities, deren `unique_id` `parse_quick_drink_index(...)` oder
   `parse_custom_lab_key(...)` liefert. Translation-Anker sind alle übrigen Entities
   mit nicht-`None` `translation_key`. Alle anderen werden ignoriert (kein Skip).
3. `resolve_device_slug(kandidaten, anker, hint=hint, device_id=device_id)`; bei
   `slug is None` → jeder Kandidat wird `skipped` mit `resolution.reason`
   (`device_slug_unresolved` oder `device_slug_ambiguous`). `MigrationPlan.device_slug`
   trägt den aufgelösten Präfix (oder `None`).
4. **Filter vor der Zielberechnung:** Ein Kandidat, dessen Objekt-Teil nicht mit
   `slug + "_"` beginnt (vom Nutzer manuell umbenannt), wird mit **`custom_entity_id`**
   übersprungen — kein Ziel, kein Rename, kein Fehlschlag. Der Grund steht in
   `NON_BLOCKING_SKIP_REASONS`; er blockiert weder die Versionierung (§3.3) noch den
   Drift-Check (§3.2).
5. Ungültiger Custom-Key (§2.2) → `skipped` mit `invalid_key` (vor der
   Zielberechnung, damit kein unsicheres Ziel entsteht).
6. Ziel bilden; ist `target == source` → **kein Rename und kein Skip** (idempotenter
   Wiederholungslauf).
7. Ist das Ziel in `occupied_entity_ids` → `skipped` mit `target_occupied`.
   Ein eigener `target_duplicate`-Fall existiert nicht: `quick_drink_target` ist über
   den Index und `custom_lab_target` über den (eindeutigen) `key` injektiv, zwei
   Kandidaten können also nie dasselbe Ziel erzeugen. Jede Zielkollision ist per
   Definition `target_occupied`.
8. Sonst `MigrationRename`.

### 3.2 HA-Anbindung in `__init__.py`

```python
# Imports: from homeassistant.helpers import device_registry as dr,
#          entity_registry as er; from homeassistant.util import slugify
#          DOMAIN aus .const; build_migration_plan/parse_custom_lab_key/
#          quick_drink_target/custom_lab_target/NON_BLOCKING_SKIP_REASONS
#          (und MigrationPlan für die Typangabe) aus .migration

async def _async_migrate_entity_ids(hass: HomeAssistant, entry) -> MigrationPlan | None:
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)

    device_registry = dr.async_get(hass)
    # HA 2026.9.1: async_get_device(identifiers=...) ist deprecated.
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    if device is None:
        fallback_id = next((reg.device_id for reg in entries if reg.device_id), None)
        device = device_registry.async_get(fallback_id) if fallback_id else None
    hint = slugify(device.name_by_user or device.name) if device is not None else None

    # Registry ist maßgeblich; der State-Check ist Best-Effort: restored states
    # entstehen erst nach EVENT_HOMEASSISTANT_START und fehlen beim Setup.
    occupied = {reg.entity_id for reg in registry.entities.values()}
    occupied.update(state.entity_id for state in hass.states.async_all())

    plan = build_migration_plan(
        entry.entry_id,
        [
            {
                "entity_id": reg.entity_id,
                "unique_id": reg.unique_id,
                "translation_key": reg.translation_key,
                "device_id": reg.device_id,
            }
            for reg in entries
        ],
        device_slug_hint=hint,
        device_id=device.id if device is not None else None,
        catalog_keys=LAB_MARKERS,
        occupied_entity_ids=occupied,
    )

    known_marker_keys = {
        marker["key"]
        for marker in logic.normalize_lab_custom_markers(
            entry.options.get(OPTION_LAB_CUSTOM_MARKERS)
        )
    }
    for rename in plan.renames:
        key = parse_custom_lab_key(rename.unique_id, entry.entry_id, LAB_MARKERS)
        if key is not None and key not in known_marker_keys:
            _LOGGER.warning(
                "Entity-ID-Migration %s: stale_marker_key %s (%s) — Entity wird "
                "umbenannt, der Key fehlt in den Options",
                entry.title,
                key,
                rename.source_entity_id,
            )

    mapping = {item.source_entity_id: item.target_entity_id for item in plan.renames}
    if mapping:
        try:
            # WICHTIG: async_migrate_entries ist eine Coroutine (HA 2026.8/2026.9)
            await er.async_migrate_entries(
                hass,
                entry.entry_id,
                lambda reg: (
                    {"new_entity_id": mapping[reg.entity_id]}
                    if reg.entity_id in mapping
                    else None
                ),
            )
        except ValueError as err:
            # Race mit einem parallelen Registry-Write: HA würde die Exception
            # in MIGRATION_ERROR wandeln; wir werten sie als fehlgeschlagenen Pass.
            _LOGGER.error("Entity-ID-Migration %s abgebrochen: %s", entry.title, err)
            return None

    # Drift-Diagnose: nach dem Pass prüfen, welche F-1/F-2-Entities nicht am
    # erwarteten Zielschema stehen (statt still zu ignorieren). Geplante Skips
    # sind ausgenommen: sie bleiben absichtlich auf ihrer alten ID und würden
    # sonst doppelt gemeldet.
    planned_skips = {skip.unique_id for skip in plan.skipped}
    drift: list[tuple[str, str]] = []
    if plan.device_slug is not None:
        for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg.unique_id in planned_skips:
                continue
            index = parse_quick_drink_index(reg.unique_id, entry.entry_id)
            key = parse_custom_lab_key(reg.unique_id, entry.entry_id, LAB_MARKERS)
            if index is not None:
                expected = f"button.{quick_drink_target(plan.device_slug, index)}"
            elif key is not None:
                expected = f"sensor.{custom_lab_target(plan.device_slug, key)}"
            else:
                continue
            if reg.entity_id != expected:
                drift.append((reg.entity_id, expected))

    # custom_entity_id ist eine Nutzerentscheidung, kein Fehlschlag: eigene
    # Warnung, genau einmal, ohne Blockade.
    for skip in plan.skipped:
        if skip.reason in NON_BLOCKING_SKIP_REASONS:
            _LOGGER.warning(
                "Entity-ID-Migration %s: %s bleibt unverändert (Grund: %s)",
                entry.title,
                skip.source_entity_id,
                skip.reason,
            )

    blocking = [
        skip for skip in plan.skipped if skip.reason not in NON_BLOCKING_SKIP_REASONS
    ]
    if blocking or drift:
        # Die EINE Zusammenfassung des Fehlerpfads: Zählung plus Paarliste.
        _LOGGER.warning(
            "Entity-ID-Migration %s fehlgeschlagen: %d übersprungen, %d schema_drift — "
            "übersprungen (Quelle, unique_id, Ziel, Grund): %s; "
            "schema_drift (Ist, Soll): %s",
            entry.title,
            len(blocking),
            len(drift),
            [
                (skip.source_entity_id, skip.unique_id, skip.target_entity_id, skip.reason)
                for skip in blocking
            ],
            drift,
        )
        return None
    return plan
```

- **B-1 (Coroutine):** `er.async_migrate_entries` ist in HA 2026.8.0
  (`entity_registry.py:2694`) und HA 2026.9.1 (`entity_registry.py:2721`) eine
  Coroutine und **muss awaited** werden. Der Callback bleibt synchron und liefert
  `dict | None`. Das veraltete Rezept in `AGENTS.md` /
  `.claude/rules/integration-development.md` (dort `@callback`-Variante) ist ein
  **Folge-Issue** außerhalb dieser Spec (O-4) — nicht hier umsetzen.
- Es wird **nur** `new_entity_id` gesetzt. `new_unique_id` und `original_name` kommen
  im Callback-Dict nicht vor. Dadurch bleiben `entity_category`, `labels`, `aliases`,
  `area_id`, `hidden_by` und `disabled_by` der Registry-Einträge erhalten.
- Neue Imports in `__init__.py`: `LAB_MARKERS` aus `.const`, `entity_registry as er`
  und `device_registry as dr` aus `homeassistant.helpers`, `slugify` aus
  `homeassistant.util`, `build_migration_plan`/`parse_custom_lab_key`/
  `quick_drink_target`/`custom_lab_target`/`NON_BLOCKING_SKIP_REASONS` (und
  `MigrationPlan` für die Typangabe) aus `.migration`.
- **Device-Anker:** bevorzugt
  `dr.async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)`
  (HA 2026.9.1; die Verankerung aus `entity.py:26-31`), Fallback ist die erste
  nicht-`None`-`device_id` über **alle** Entries — nie nur `entries[0]`.
  `async_get_device(identifiers=…)` ist deprecated und wird nicht mehr verwendet.
- **State-Check ist Best-Effort:** `hass.states.async_all()` ist beim Setup
  unvollständig (restored states entstehen erst nach
  `EVENT_HOMEASSISTANT_START`). Maßgeblich ist die Registry; der State-Check senkt
  nur das Restrisiko einer Kollision mit einem nicht (mehr) registrierten State.
- **Exception-Vertrag:** Ein `ValueError` aus `async_migrate_entries` (Race mit einem
  parallelen Registry-Write, intern `async_update_entity`) wird abgefangen, geloggt und
  als `None` zurückgegeben. Ohne Catch würde HA daraus `MIGRATION_ERROR` machen
  (Setup-Abbruch, Version bleibt); mit Catch bleibt das Verhalten identisch, aber mit
  klarer Ursache im Log.
- Die Warnung nennt das Paar (Quelle, `unique_id`, Ziel, Grund) als Liste — nicht nur
  eine Zählung (go-gauge-Punkt 1).
- `stale_marker_key` ist eine **Warnung, kein Skip**: Die Registry-Entity existiert,
  die Umbenennung ist safe; fehlt der Key in den Options, wird das protokolliert
  (Ursache für spätere Key-Drift, §3.5).
- **`custom_entity_id` ist nicht blockierend:** Ein Kandidat, dessen `entity_id` der
  Nutzer selbst vergeben hat (Objekt-Teil außerhalb des Anker-Präfixes), bleibt
  unverändert. Die Warnung nennt Quelle und Grund genau einmal; der Grund steht in
  `NON_BLOCKING_SKIP_REASONS`, ist aus dem Drift-Check ausgenommen und verhindert die
  Versionserhöhung **nicht**. Andernfalls bliebe ein Entry mit einer einzigen
  hand-renamed Entity dauerhaft auf der alten Version (produktive Regression §2.3).
- **Drift-Diagnose:** Nach dem Pass wird die Registry erneut gelesen; jede F-1/F-2-
  Entity **ohne geplanten Skip** muss auf ihrer erwarteten Ziel-ID stehen. Abweichungen
  werden als `schema_drift <n>` mit Paarliste gewarnt und lassen den Pass
  **fehlschlagen** (Version bleibt) — so kann ein vergessenes `await` oder ein stiller
  Registry-Fehler nicht als Erfolg durchgehen. Geplante Skips sind ausgenommen, damit
  eine absichtlich unveränderte Entity nicht zusätzlich als Drift gemeldet wird.

### 3.3 `async_migrate_entry` (atomar, idempotent, Downgrade-Guard)

```python
async def async_migrate_entry(hass: HomeAssistant, entry: HealthOMatConfigEntry) -> bool:
    if entry.version > 3:
        # Defensiv: HA ruft den Handler nur für entry.version < flow.VERSION auf.
        # Der Guard schützt direkte Aufrufe/Tests und kostet nichts.
        _LOGGER.error(
            "Config entry %s hat Version %s > 3 — Downgrade nicht unterstützt",
            entry.title, entry.version,
        )
        return False

    data = dict(entry.data)
    options = dict(entry.options)

    if entry.version == 1:
        # bisherige v1-Stufe: quick_drinks data → options (unverändert)
        options.setdefault("quick_drinks", [dict(qd) for qd in DEFAULT_QUICK_DRINKS])
        data = {k: v for k, v in data.items() if k != "quick_drinks"}

    if entry.version < 3:
        plan = await _async_migrate_entity_ids(hass, entry)
        if plan is None:
            # Kein async_update_entry: Version bleibt stehen, HA versucht es beim
            # nächsten Setup erneut. v1-Datenmigration wird ebenfalls nicht
            # teilgeschrieben (alles-oder-nichts).
            return False

        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=3
        )
        _LOGGER.info(
            "Config entry %s: auf Version 3 migriert (renamed=%d skipped=%d)",
            entry.title,
            len(plan.renames),
            len(plan.skipped),
        )
    return True
```

Verträge:

| Aspekt | Vertrag |
|---|---|
| **Version** | `HealthOMatConfigFlow.VERSION = 3` (`config_flow.py:250`). Neue Entries starten auf 3. |
| **Stufen** | `entry.version == 1` → Datenmigration; `entry.version < 3` → Entity-IDs. Beide Stufen können in einem Lauf greifen. |
| **Atomar** | Genau **ein** `async_update_entry` mit `data`, `options`, `version` (go-gauge-Punkt 3). Keine direkte `entry.version`-Zuweisung. |
| **Erfolgskriterium** | Kein **blockierender** Skip (alle Gründe außer denen in `NON_BLOCKING_SKIP_REASONS`) und kein `schema_drift`. `custom_entity_id` blockiert **nicht**: der Kandidat behält seine hand-vergebene ID, die Version wird trotzdem erhöht. |
| **Fehler** | `return False` nur bei blockierenden Gründen bzw. Drift → HA bricht das Setup dieses Entry ab („Migration failed"). Bewusst fail-closed, damit kein halb migrierter Zustand als Erfolg gilt. Behebung: kollidierende Entity umbenennen/entfernen bzw. bei `device_slug_ambiguous` Gerätenamen/Area bereinigen, HA neu starten. Hand-renamed Entities (`custom_entity_id`) sind **kein** Fehlerfall. |
| **Idempotenz** | Zweiter Lauf: `entry.version == 3` → keine Registry-Aufrufe, kein `async_update_entry`. Teil-Migration (einige Renames angewendet, dann Skip): bereits umbenannte Entities haben `target == source` → kein erneuter Rename; nur der offene Rest wird wiederholt. |
| **Downgrade** | `entry.version > 3` → Log + `False`, keine Änderung. Im Handler defensiv (HA prüft die Version vorher); bleibt für direkte Aufrufe/Tests. |
| **HA < 2026.9** | Migration ist versionsunabhängig: `er.async_migrate_entries` existiert, Ziele stammen aus `unique_id`/Registry, nicht aus Translationen. Der `suggested_object_id`-Override fällt ohne `default_language_platform_translations` auf `super()` zurück; HA < 2026.9 erzeugte ohnehin englische IDs (`hacs.json` verlangt `2026.8.0`). |
| **Fehlendes Device** | Device-Anker über `identifiers` fehlt → erste nicht-`None`-`device_id` über alle Entries; ohne Translation-Anker `device_slug_unresolved`, bei Widerspruch `device_slug_ambiguous` (fail-closed). |

### 3.4 Verhalten bei Kollisionen (Negativfall)

Ein Ziel gilt als belegt, wenn es in `occupied_entity_ids` liegt (Registry **oder**
State Machine). Einen separaten Duplikat-Fall gibt es nicht: Die Ziel-Funktionen sind
injektiv (Index bzw. `key`), jede Kollision ist `target_occupied`. Dann:

1. Die betroffene Entity wird **nicht** umbenannt (kein `ValueError`, kein Abbruch des
   Passes).
2. `_async_migrate_entity_ids` liefert `None` (blockierender Skip/Drift);
   `async_migrate_entry` liefert `False`, **ohne** Version/Daten zu schreiben.
   `custom_entity_id` zählt hier **nicht** als Blockade.
3. HA lädt den Entry nicht; das Log nennt Quelle, `unique_id`, Ziel und Grund.
4. Beim nächsten Start läuft die Migration erneut. Sind die bereits umbenannten
   Entities unverändert (`target == source`), wird nur der kollidierende Rest erneut
   versucht.
5. Der `False`-Pfad erzeugt in HA `MIGRATION_ERROR`: Der Entry gilt als nicht
   wiederherstellbar (`state.recoverable = False`), Reload/Unload sind gesperrt —
   **nur ein Neustart** wiederholt die Migration. Das steht so in den Release-Notes
   (§5.3).

Damit ist die Kollision sichtbar und reparierbar, statt still eine falsche ID zu
vergeben oder den Pass dauerhaft zu blockieren.

### 3.5 Randfälle

| Fall | Verhalten |
|---|---|
| Quick-Drink-Slot wurde aus den Options entfernt, Registry-Entity existiert noch | `unique_id` enthält weiter den Index → wird migriert (Ziel-ID bleibt konsistent, falls der Slot zurückkommt). |
| Custom-Key enthält Großbuchstaben/Leerzeichen/Sonderzeichen | `invalid_key` → Skip, Version bleibt (§2.2). |
| Custom-Key ist ein Katalog-Key | `parse_custom_lab_key` liefert `None` → Katalog-Entity wird nicht angefasst (sie ist bereits am Ziel). |
| Zwei Entries erzeugen denselben `device_slug` (Anzeigenamen kollidieren nach Slugify) | Zweiter Entry läuft in `target_occupied` → Skip + Warnung; Nutzer muss einen Anzeigenamen/eine ID entflechten. Bewusst kein automatisches Suffix (wäre nicht deterministisch wiederholbar). |
| Entity wurde vom Nutzer manuell umbenannt (**Kandidat**) | `custom_entity_id` → Warnung, **kein** Fehlschlag: die hand-vergebene ID bleibt unverändert, die Version wird trotzdem gesetzt (in `NON_BLOCKING_SKIP_REASONS`, vom Drift-Check ausgenommen). |
| Manuell umbenannter **Anker** (`translation_key`-Entity, z. B. `sensor.caro_gewicht`) | Teilt kein führendes Token mit den übrigen Ankern → zählt nicht für `C`/Akzeptanz, leert den Präfix aber nicht (mindestens zwei Anker stützen ihn). Kein Skip, kein Fehlschlag; produktive Regression §2.3. |
| Entity ist deaktiviert (`disabled_by`) | Migration ignoriert das Flag; Rename ist auch für deaktivierte Entities erlaubt und gewünscht. |
| Device-Anker fehlt, Anzeigename der Person wurde geändert, oder `entity_id_parts` enthält ein Area-Segment, das nicht zum Hint passt | `device_slug_ambiguous` → Skip, Version bleibt; fail-closed statt Raten. `device_slug` ist das aktuell verwendete Präfix inkl. Area-Segment (§2.3). Hand-renamed **Kandidaten** lösen diesen Fall nicht mehr aus (`custom_entity_id`). |
| Custom-Key existiert in der Registry, fehlt aber in `entry.options["lab_custom_markers"]` | Warnung `stale_marker_key`, Rename läuft weiter (Registry ist maßgeblich); Hinweis auf künftigen Key-Drift. |
| Race: `ValueError` aus `async_migrate_entries` | Wird abgefangen, geloggt, `None` → Version bleibt; `async_migrate_entry` liefert `False`, HA markiert `MIGRATION_ERROR`, Neustart wiederholt. |
| Recorder/Statistik | `er.async_migrate_entries` feuert `entity_registry_updated` (Aktion `update`); HA-Recorder schreibt `states_meta` und `statistics_meta` um — **nicht** die historischen `states`-Zeilen. Verifikation auf der Testinstanz (§6.3). |

---

## 4. Härtungen (nicht-breaking, gehören in denselben Plan)

Diese vier Punkte schließen die im Audit benannten Lücken. Sie ändern keine
`unique_id` und keine bestehende `object_id`.

### A-1 — Kategorie-Validierung in `normalize_lab_custom_markers`

`logic.py:1022` übernimmt `category` unvalidiert. Künftig:

```python
known = {category["key"] for category in LAB_CATEGORIES}
category = str(item.get("category") or "").strip().lower()
if category not in known:
    category = LAB_CATEGORY_OTHER
```

Folgen: F-3 kann keine `LabCategoryWarningEntity` mit unbekanntem
`lab_warning_<kategorie>`-Key mehr erzeugen; damit entfällt auch die lokalisierte
`binary_sensor.…_problem`-ID (Device-Class-Fallback). `other` bleibt wie bisher ohne
Warn-Entity. **Nebenwirkung:** Bereits registrierte Warn-Entities für Fremd-Kategorien
werden beim nächsten Setup nicht mehr angelegt (Orphans) — Post-Release-Cleanup, §5.5
Schritt 8.

### A-2 — Key-Erhalt für eingehende Marker ohne `key`

Neue Signatur (rückwärtskompatibel, `previous=None` = bisheriges Verhalten):

```python
def normalize_lab_custom_markers(raw: Any, previous: Any = None) -> list[dict]:
```

- Aus `previous` wird eine Map `stripped_name → key` gebaut (nur Einträge mit
  nicht-leerem `name` und `key`; erster Treffer gewinnt).
- Hat ein eingehender Eintrag **keinen** `key` (oder nur Whitespace) und entspricht
  sein `name` exakt einem Eintrag aus `previous`, wird dessen `key` als `base_key`
  verwendet — statt Neu-Slug.
- Ein **explizit** mitgesendeter `key` gewinnt weiterhin immer.
- Kollisionsauflösung (`_2`, `_3`, …) bleibt unverändert und läuft **nach** der
  Übernahme; Katalog-Keys bleiben reserviert.
- Ohne `previous` (oder bei nicht-normalisierbaren Daten) bleibt das Verhalten exakt
  wie heute.

Aufrufstellen:

| Datei:Zeile | Änderung |
|---|---|
| `ws_api.py:1874-1883` (`parse_settings_message`) | Signatur `parse_settings_message(msg, *, previous_markers=None)`; Aufruf `normalize_lab_custom_markers(raw_markers, previous_markers)` |
| `ws_api.py:1940` | `parse_settings_message(msg, previous_markers=entry.options.get(OPTION_LAB_CUSTOM_MARKERS))` |
| `restore.py:361-364` (`merge_lab_custom_markers`) | `normalize_lab_custom_markers(incoming, previous=current)` — ein Restore mit keylosen Einträgen erbt vorhandene Keys statt sie zu verschieben |
| `__init__.py:119` (`_lab_options_snapshot`) | unverändert (`previous=None`); die Options enthalten im Normalfall bereits Keys |
| `logic.py:1058` (`effective_lab_markers`) | unverändert; Keys sind dort bereits persistiert |

### A-3 — Drift-Tests für `WELLBEING_STATES` → `report_*`

`tests/test_translations.py:478-501` deckt `LAB_CATEGORIES` bereits vollständig ab
(Audit-Korrektur in §0). Es fehlt die analoge Absicherung für Wellbeing: Für jeden
`key` in `const.WELLBEING_STATES` muss `entity.button.report_<key>.name` in
`strings.json`, `translations/en.json` und `translations/de.json` existieren (nicht
leer; Key-Bäume identisch — letzteres prüft bereits `test_req_hom_107_*`).

### A-4 — E2E-Regression: englische `object_id`s bei Systemsprache `de`

Auf der Testinstanz (Sprache `de`) nach Erstanlage einer Test-Person per
`config/entity_registry/list` prüfen:

- `sensor.<prefix>_drinks_today` (nicht `…_heute_getrunken`)
- `binary_sensor.<prefix>_blood_pressure_warning` (nicht `…_blutdruck_warnung`)
- `button.<prefix>_quick_drink_1` (nicht `…_glas_wasser`)
- **Area-Fall:** Person mit zugewiesener Area bzw. `entity_id_parts` mit `AREA`
  (HA 2026.9.1-Default): Das tatsächlich verwendete Präfix (`<area>_<device>`) muss
  von `resolve_device_slug` erkannt und für `quick_drink_1`/`lab_<key>` verwendet
  werden — `device_slug` ist das **aktuell verwendete object-id-Präfix**, nicht
  `slugify(device.name)` (§2.3).

Der Test fängt einen stillen Bruch des `suggested_object_id`-Overrides durch
HA-Core-Refactors (`platform_data`, `_name_internal`,
`default_language_platform_translations` sind internes API, Audit §1).

---

## 5. Release

### 5.1 Versions- und Cache-Buster-Änderungen

`manifest.json:22`: `"version": "0.16.2"` → **`"version": "0.17.0"`** (bare SemVer, kein
`v`). Tag: **`v0.17.0`**, GitHub-Release **stable** (`gh release create v0.17.0 --latest`,
kein Pre-Release).

Alle Cache-Buster und JS-Versionskonstanten müssen mitziehen (sonst liefert der
Browser alte Module):

| Datei | Stellen |
|---|---|
| `www/health-o-mat-card.js` | `const CARD_VERSION = "0.16.2"` (Zeile 55) |
| `www/health-o-mat-labs-card.js` | `const CARD_VERSION = "0.16.2"` (Zeile 26) |
| `www/health-o-mat-panel.js` | `const PANEL_VERSION` (Zeile 95) sowie die `?v=0.16.2`-Importe (Zeilen 75, 80, 85, 92) |
| `www/health-o-mat-panel-views.js` | `?v=0.16.2` (Zeile 45) |
| `www/health-o-mat-panel-admin.js` | `?v=0.16.2` (Zeile 33) |

`frontend.py:74-75` liest die Version aus dem Manifest — dort ist keine Änderung nötig.

### 5.2 Beispiele und Tests mit alten IDs

| Datei | Änderung |
|---|---|
| `examples/dashboard.yaml:41-47` | `…_glas_wasser` → `…_quick_drink_1` usw. (4 IDs) |
| `examples/dashboard-mini.yaml:37-39` | `…_glas_wasser`, `…_flasche_wasser` → `quick_drink_1/2` |
| `examples/dashboard-mushroom.yaml:43-49` | 4 IDs → `quick_drink_1…4` |
| `tests/test_dashboards.py:19-68` | `KNOWN_SUFFIXES["button"]`: alte Suffixe `glas_wasser`/`flasche_wasser`/`tasse_kaffee`/`glas_saft` entfernen, `quick_drink_1`…`quick_drink_4` ergänzen |
| `tests/test_config_flow.py:102-105` | erwartet `VERSION == 3` |
| `tests/test_wave_a.py:203-215` | „v2 ist no-op" wird „v3 ist no-op"; der v1-Test erwartet `version == 3`; der Downgrade-Test (`:218ff`) verwendet `entry.version = 4` |
| `README.md` | Beispiel `button.…_glas_wasser` (Abschnitt Buttons) auf `…_quick_drink_1` umstellen; **Kasten „Entity-IDs ab 0.17.0"** mit Alt→Neu-Regel und Verweis auf die Migrationshinweise ergänzen |
| `scripts/e2e-live-test.sh` | alte IDs `…_glas_wasser`, `…_flasche_wasser`, `…_tasse_kaffee`, `…_glas_saft` (Zeilen 122-133) auf `…_quick_drink_1…4` umstellen |
| `tests/test_wave_a.py` (weitere `__init__`-Ladepfade) | `hass = MagicMock()` um echte Fakes für `hass.states.async_all()` ergänzen; `er` ist das Fake-Modul `homeassistant.helpers.entity_registry` (nicht `hass`) und braucht `async_get`/Registry-Stub; `async_migrate_entries` **nicht** als MagicMock (siehe §6.2), sondern als `AsyncMock`/Coroutine |

### 5.3 CHANGELOG und Release-Notes (Pflichtinhalt)

`CHANGELOG.md` erhält einen `## [0.17.0]`-Block (Datum = Release-Tag). **An erster
Stelle des Blocks steht der 💥-Migrationshinweis** (nicht als Nebensatz unter
„Changed"). Zusätzlich `docs/RELEASE-NOTES-0.17.0.md` (Projektmuster).

Mindestinhalt der Migrations-Notes:

1. **Was sich ändert** — Tabelle der Standard-Quick-Drinks (alt → neu, §2.1) und die
   Regel für Custom-Marker (`…_<name-slug>` → `…_lab_<key>`, inkl. Hinweis, dass der
   `key` ein ASCII-Slug sein kann, z. B. `h_moglobin`).
2. **Was Nutzer anpassen müssen** — Automationen, Skripte, Dashboards, Szenen,
   Helfer und Template-Sensoren, die alte IDs referenzieren. HA benennt sie **nicht**
   automatisch um.
3. **Was erhalten bleibt** — `unique_id` unverändert, Recorder-Metadaten
   (`states_meta`, `statistics_meta`) werden auf die neue `entity_id` umgeschrieben
   (historische Zustandszeilen selbst bleiben unverändert), Store-/Messdaten
   unberührt, `original_name` unverändert.
4. **Migrationsmechanik** — passiert automatisch beim ersten Start nach dem Update;
   bei einer ID-Kollision wird der Config-Entry nicht geladen und das Log nennt die
   Paare; Auflösung: kollidierende Entity umbenennen/entfernen, neu starten.
   Hand-vergebene Entity-IDs (vom Nutzer manuell umbenannt) bleiben unverändert und
   werden nur als `custom_entity_id`-Warnung protokolliert — sie blockieren die
   Migration nicht.
5. **`MIGRATION_ERROR` ist nicht wiederherstellbar (MINOR-Konsequenz):** Der Entry
   hat dann `state.recoverable = False`; Reload und Unload sind gesperrt, **nur ein
   vollständiger HA-Neustart** wiederholt die Migration. Das muss in den Notes stehen,
   weil der MINOR-Sprung den Bruch nicht erwarten lässt (§5.4).
6. **Post-Release-Cleanup:** Durch A-1 können Warn-Entities für Fremd-Kategorien aus
   dem Setup verschwinden (Orphans). Nach dem Release in der Device-Ansicht prüfen und
   entfernen (§5.5 Schritt 8) — nicht durch Ändern von `unique_id`s.

### 5.4 Bewusste Abweichung von der Release-Regel

> **Bewusste Abweichung, kein Versehen:** Nach der Projektregel (`AGENTS.md`,
> Abschnitt „Rename = Breaking Change"; ferner
> `.claude/rules/integration-development.md` → `hacs-integration-development`) ist
> jede Änderung einer `entity_id` ein **MAJOR**-Release. Der Nutzer hat diese Regel
> für diese Änderung ausdrücklich übersteuert: veröffentlicht wird **MINOR `0.17.0`**
> (von `0.16.2`). Begründung: Die Migration läuft automatisch, verlustfrei und
> betrifft nur zwei Entity-Klassen; der Versionssprung folgt der Nutzerentscheidung,
> nicht der Regel.
>
> **Konsequenz:** Nutzer sehen nur einen Minor-Sprung und rechnen nicht mit einem
> Bruch. Deshalb ist der 💥-Abschnitt in `docs/RELEASE-NOTES-0.17.0.md`
> **verpflichtend** und muss **an erster Stelle** des `CHANGELOG.md`-Blocks
> `[0.17.0]` stehen (Alt→Neu-Tabelle, Anpassungsliste für Automationen/Skripte/
> Dashboards, Hinweis „Verlauf bleibt"). Der Post-Release HACS-Update-Test von
> `0.16.2` bleibt unabhängig davon Pflicht.

### 5.5 Reihenfolge

1. Branch `feat/entity-id-migration`, Implementierung + Unit-/Registry-Tests grün.
2. Live-Migrationstest auf `/home/hermes/ha-test` (§6.3), inkl. Negativprobe.
3. `pytest -q`, `ruff check .`, `ruff format --check .`, `pytest tests_e2e/` grün.
4. Merge nach `main`.
5. Tag `v0.17.0` setzen; `manifest.version` ist bereits `0.17.0`.
6. **Echtes GitHub-Release** `v0.17.0` als **stabiles** Release
   (`gh release create v0.17.0 --latest`, kein Pre-Release) mit den Notes aus §5.3.
7. **Post-Release HACS-Update-Test** auf der Dev-Instanz: 0.16.2 installieren →
   Test-Person mit Quick-Drinks + Custom-Marker anlegen → Update auf 0.17.0 über HACS →
   Neustart → Registry/Verlauf prüfen (HACS liefert nur echte Releases; Tag allein
   genügt nicht).
8. Erst danach: verwaiste Alt-Entities prüfen/entfernen (Device-Ansicht, nicht nur
   Entitäten-Liste). Bei reiner `new_entity_id`-Umbenennung sind keine Orphans zu
   erwarten; **A-1** kann jedoch Warn-Entities für Fremd-Kategorien aus dem Setup
   nehmen (Orphans). `unique_id`s werden nie geändert.

---

## 6. Teststrategie (Schwerpunkt)

### 6.1 Unit-Tests (HA-frei) — `tests/test_entity_id_migration.py`

`migration.py` wird ohne HA-Import getestet (kein Fake-Package nötig).

| Test | Prüft |
|---|---|
| `test_quick_drink_target_is_one_based` | Index 0 → `..._quick_drink_1`, Index 3 → `..._quick_drink_4` |
| `test_parse_quick_drink_index` | `{entry}_button_quick_0` → 0; `…_10` → 10; fremde Entry-ID/`…_quick_`/`…_quick_01`/`…_quick_x` → `None` |
| `test_custom_lab_target_uses_key` | `lab_vitamin_d`, `lab_h_moglobin` |
| `test_parse_custom_lab_key_skips_catalog` | Katalog-Key (`crp`) → `None`; Custom-Key → Key; fremde Entry-ID → `None` |
| `test_resolve_device_slug_accepts_hint_with_matching_anchors` | Hint `health_o_mat_max`; Translation-Anker `…_max_drinks_today`, `…_max_daily_goal_progress`; Kandidaten passen → Hint |
| `test_resolve_device_slug_falls_back_to_translation_anchors` | Hint `None`; Anker `…_dana_drinks_today` + `…_dana_daily_goal_progress` (Suffix-Token divergieren) → `health_o_mat_dana` |
| **`test_resolve_device_slug_ignores_user_labels` (B-2-Gegenbeispiel)** | Nur Kandidaten `…_glas_wasser`, `…_glas_saft`, `…_glas_tee`, `…_glas_kaffee`, keine Translation-Anker → `device_slug_unresolved`; **nie** `…_glas` |
| `test_resolve_device_slug_hint_conflict_is_ambiguous` | Hint `health_o_mat_neu`, Anker `…_alt_*` → `device_slug_ambiguous` |
| `test_resolve_device_slug_area_prefix_matches_hint` | Anker-Präfix `wohnzimmer_health_o_mat_max`, Hint `health_o_mat_max` → **`wohnzimmer_health_o_mat_max`** (Area bleibt Teil der IDs) |
| **`test_resolve_device_slug_lab_only_with_hint_uses_hint`** | Nur Labs-Anker (`…_lab_crp`, `…_lab_creatinine`), Hint `health_o_mat_max` → `health_o_mat_max` (Hint gewinnt, Boundary-Präfix) |
| **`test_resolve_device_slug_lab_only_without_hint_is_unresolved`** | Nur Labs-Anker, Hint `None` → `device_slug_unresolved` (Suffix-Token `lab` divergiert nicht) |
| `test_resolve_device_slug_single_anchor_is_unresolved` | nur ein Translation-Anker → `device_slug_unresolved` |
| `test_resolve_device_slug_candidate_outside_prefix_no_longer_blocks` | Kandidat außerhalb des Anker-Präfixes ändert die Auflösung nicht (kein `device_slug_ambiguous`) |
| **`test_resolve_device_slug_tolerates_one_hand_renamed_anchor` (Produktiv-Regression)** | Ausreißer-Anker `sensor.caro_gewicht` neben regulären Ankern → `C` bleibt gestützt, Präfix wird aufgelöst |
| `test_resolve_device_slug_tolerates_anchor_diverging_after_the_prefix` | Anker mit gemeinsamem Präfix, aber abweichendem Token danach → Präfix bleibt gültig |
| `test_resolve_device_slug_two_equally_supported_prefixes_is_ambiguous` | Zwei gleich lange, gleich stark gestützte Anker-Präfixe → `device_slug_ambiguous` |
| `test_resolve_device_slug_rejects_foreign_device` | Kandidat mit fremder `device_id` → `device_slug_ambiguous` |
| `test_resolve_device_slug_without_candidates_is_unresolved` | Keine Kandidaten → `device_slug_unresolved` |
| `test_plan_renames_only_f1_f2` | Katalog-, Wellbeing-, BP-Entities bleiben unangetastet |
| `test_plan_is_noop_at_target` | Quelle bereits `…_quick_drink_1` → weder Rename noch Skip |
| `test_plan_skips_occupied_target` | Ziel in `occupied_entity_ids` → Skip `target_occupied` (einziger Kollisionsgrund; Ziele sind injektiv) |
| `test_plan_skips_invalid_custom_key` | Key mit Leerzeichen → Skip `invalid_key` |
| **`test_plan_warns_custom_entity_id_instead_of_failing` (Filter-Schritt)** | Hand-renamed Kandidat → Skip `custom_entity_id`, kein Ziel, kein Fehlschlag |
| **`test_plan_migrates_despite_hand_renamed_anchor` (Produktiv-Regression)** | Ausreißer-Anker blockiert den Plan nicht; alle übrigen Ziele werden gebildet |
| `test_plan_propagates_device_slug_reasons` | `unresolved` bzw. `ambiguous` aus dem Resolver wird als Skip-Grund übernommen |
| `test_plan_deterministic_order` | gleiche Eingabe → gleiche Plan-Reihenfolge |

Zusätzlich in `tests/test_logic.py`:

| Test | Prüft |
|---|---|
| `test_req_hom_130_normalize_rejects_unknown_category` | A-1: `"vitamins"` → `other`; bekannte Kategorie bleibt; `""` → `other` |
| `test_req_hom_130_normalize_keeps_key_for_previous_name` | A-2: keyloser Eintrag „Vitamin D" erbt `vitamin_d` aus `previous` |
| `test_req_hom_130_normalize_explicit_key_wins` | expliziter Key schlägt Namens-Match |
| `test_req_hom_130_normalize_new_name_gets_new_key` | keyloser, unbekannter Name → neuer Slug (kein willkürliches Erben) |
| `test_req_hom_130_normalize_without_previous_unchanged` | Altverhalten ohne `previous` |

### 6.2 Registry-Tests (Fake-Registry, `tests/test_entry_migration.py`)

Laden von `__init__.py` wie in `tests/test_wave_a.py:166-176`. Fake-Objekte:

- `er.async_get` → Registry-Mock mit `async_get`, `entities` (Dict),
  `async_entries_for_config_entry` und **`async_migrate_entries = AsyncMock()`**.
  **Kein `MagicMock`** dafür: Ein MagicMock schluckt die Coroutine ohne `await` und
  würde genau den B-1-Fehler maskieren.
- Der Test zieht den Callback aus `mock.call_args.args[2]` und ruft ihn **selbst** mit
  Registry-Entries auf; nur so wird das Mapping geprüft, nicht bloß das Await.
- `dr.async_get` → Device-Registry-Mock mit
  `async_get_device_by_identifier((DOMAIN, entry_id), entry_id)` und
  `async_get(device_id)`.
- `hass.states.async_all` → Liste (echter Fake), `hass.states.async_available` wird
  nicht benötigt.

Die Fake-Modul-Liste in `tests/conftest.py` ist um
`homeassistant.helpers.entity_registry` und `homeassistant.helpers.device_registry`
zu erweitern, sobald `__init__.py` diese Submodule importiert.

| Test | Prüft |
|---|---|
| `test_migrates_quick_and_custom_only` | Callback aus `mock.call_args.args[2]` ziehen und selbst aufrufen: Mapping enthält genau die erwarteten Quellen; `new_entity_id` korrekt; andere Registry-Entities unberührt |
| `test_unique_id_and_original_name_untouched` | `async_migrate_entries`-Callback-Dict hat **nur** `new_entity_id` |
| **`test_awaits_async_migrate_entries` (B-1-Regression)** | `async_migrate_entries.assert_awaited_once()` bzw. `await_count == 1`; ein nicht-awaiteter Aufruf lässt den Test fehlschlagen (Coroutine-Fake warnt/asserted) |
| `test_bumps_to_version_3_on_success` | genau ein `async_update_entry` mit `data`, `options`, `version=3` |
| `test_collision_skips_and_keeps_version` | Ziel belegt → Rückgabe `False`, **kein** `async_update_entry`, Warnung mit Paarliste |
| `test_collision_retry_after_fix` | erster Lauf: A umbenannt, B Skip → Version bleibt; zweiter Lauf nach Freigabe: A no-op, B umbenannt, Version 3 |
| `test_value_error_fails_closed` | `async_migrate_entries` wirft `ValueError` → `False`, keine Version, Log-Eintrag (kein ungefangener `MIGRATION_ERROR`-Traceback) |
| `test_stale_marker_key_warns_but_renames` | Custom-Key fehlt in den Options → Warnung `stale_marker_key`, Rename bleibt im Plan |
| **`test_hand_renamed_anchor_does_not_block_migration` (Produktiv-Regression)** | Anker `sensor.caro_gewicht` in der Registry → `async_migrate_entry` liefert `True`, Version 3, alle Ziele gesetzt, die hand-renamed ID bleibt unverändert |
| **`test_custom_entity_id_warns_and_still_bumps_version`** | Kandidat hand-renamed → Warnung `custom_entity_id`, **keine** Meldung `fehlgeschlagen`/`schema_drift`, genau ein `async_update_entry` mit `version=3` |
| **`test_schema_drift_warns_and_fails`** | Nach dem Pass steht eine F-1/F-2-Entity **ohne geplanten Skip** nicht auf der Ziel-ID → Warnung `schema_drift` und `None`/`False` (Version bleibt); geplante Skips lösen keine Drift aus |
| `test_second_run_is_noop` | `entry.version == 3` → `async_migrate_entries`/`async_update_entry` nicht aufgerufen |
| `test_downgrade_guard_v4` | `version == 4` → `False`, keine Änderung |
| `test_v1_entry_is_migrated_to_v3_in_one_update` | `quick_drinks` data→options **und** Entity-Renames, ein `async_update_entry` mit `version=3` |
| `test_v1_entity_failure_does_not_write_data` | Rename-Fehler → kein `async_update_entry` (kein Teil-Schreiben) |
| `test_no_entities_still_bumps_version` | leere Registry → `True`, Version 3 |
| `test_state_machine_target_counts_as_occupied` | Ziel nur als State vorhanden → Skip |

### 6.3 Migrationstest auf `/home/hermes/ha-test` (verbindlich)

Etikette: nur die eigene Domain syncen (`/home/hermes/ha-test/bin/sync <repo>`),
**kein** `bin/reset`, **keine** Sprachumschaltung, `unique_id`s nie ändern, keine
fremden Domains/Entries anfassen. Snapshots ausschließlich **lesend** kopieren (nach
`.tmp/`, nicht committen).

#### Phase 0 — Baseline mit 0.16.2, zwei Test-Personen

1. Sicherstellen, dass die Instanz `0.16.2` läuft:
   `docker exec ha-test cat /config/custom_components/health_o_mat/manifest.json` →
   `"version": "0.16.2"`. Falls nicht: Baseline ohne Eingriff in den Arbeitsbaum
   erzeugen (`git archive d86b247 | tar -x -C .tmp/baseline-0162`) und
   `bin/sync .tmp/baseline-0162` ausführen — kein `git checkout`/`stash` nötig.
2. Zwei dedizierte Test-Personen über den echten Config-Flow anlegen (nicht die
   E2E-Fixture-Personen verändern):
   `POST /api/config/config_entries/flow {"handler":"health_o_mat"}` →
   `POST …/flow/<flow_id> {"person":"Migrationstest"}` (Entry **A**, Positivfall)
   und `{"person":"Migrationstest-Kollision"}` (Entry **B**, Negativfall).
   Beide Entry-IDs notieren.
3. **A** konfigurieren (WS `health_o_mat/set_settings`, z. B. via
   `scripts.e2e_bootstrap._ws_command`):
   - vier Quick-Drink-Slots mit („Glas Wasser", „Grüner Tee", „Tasse Kaffee",
     „Glas Saft") — enthält Nicht-ASCII und ein Label, das später von der ID abweicht;
   - Custom-Marker `[{"name":"Vitamin D","unit":"ng/mL","category":"other"},
     {"name":"Ferritin gesamt","unit":"µg/L","category":"other"},
     {"name":"Hämoglobin","unit":"g/dL","category":"blood_count"}]` — ohne `key`
     (der Server slugt und persistiert).
4. **A**-Verlauf erzeugen: `health_o_mat.add_drink` (2×) und
   `health_o_mat.add_lab_value` für `vitamin_d` und `ferritin_gesamt`.
5. **B** konfigurieren: Default-Quick-Drinks (4) belassen und **einen** Custom-Marker
   `{"name":"Vitamin D","unit":"ng/mL","category":"other"}` anlegen (erzeugt
   `sensor.<prefixB>_vitamin_d` und ist das Lab-Kollisionsziel).
6. Snapshot **konsistent** ziehen (`/config` ist Bind-Mount:
   `/home/hermes/ha-test/config`):
   - mindestens 10 s nach der letzten Options-/Entity-Änderung warten (`SAVE_DELAY`)
     und die Entity-Anzahl gegen `config/entity_registry/list` abgleichen;
   - dann per Host-`cp` (HA darf laufen):
     `cp /home/hermes/ha-test/config/.storage/core.entity_registry .tmp/registry.before.json`
     `cp /home/hermes/ha-test/config/.storage/core.device_registry .tmp/device_registry.before.json`
     `cp /home/hermes/ha-test/config/.storage/core.config_entries .tmp/config_entries.before.json`
     `cp /home/hermes/ha-test/config/.storage/health_o_mat .tmp/health_o_mat_store.before.json`
   - Mapping `unique_id → entity_id`, `original_name`, `device_id` extrahieren.
7. Erwartete alte IDs für **A** dokumentieren: `button.…_glas_wasser`,
   `…_gruner_tee` (HA-`slugify` transliteriert `ü` → `u`), `…_tasse_kaffee`,
   `…_glas_saft`, `sensor.…_vitamin_d`, `…_ferritin_gesamt`,
   `…_hamoglobin` (HA transliteriert „Hämoglobin"); die **neue** ID nutzt dagegen
   den `key` `h_moglobin` aus der ASCII-only-Normalisierung in `logic.py`.

#### Phase 0b — Kollisionen präparieren (nur Entry B)

8. **Quick-Kollision:** per WS `config/entity_registry/update`
   `button.<prefixB>_book_custom_amount` → `button.<prefixB>_quick_drink_1`.
   Die Entity behält ihre `unique_id` `{entryB}_button_book_custom` und wird von der
   Migration nicht angefasst — sie belegt aber das Ziel von Quick-Slot 0.
9. **Lab-Kollision:** per WS `config/entity_registry/update`
   `sensor.<prefixB>_crp` (Katalog-CRP, englischer Name „CRP", `unique_id`
   `{entryB}_lab_crp`) → `sensor.<prefixB>_lab_vitamin_d`. Sie belegt das Ziel des
   Custom-Markers `vitamin_d` aus Schritt 5.

#### Phase 0c — Isolation des Erstlaufs

- Alle übrigen `health_o_mat`-Entries vor dem ersten Migrationslauf dokumentieren
  (Entry-ID, Person, Version, Entity-Anzahl).
- Für den **Erstlauf** diese Entries über
  `DELETE /api/config/config_entries/entry/<entry_id>` entfernen, sodass ausschließlich
  **A** und **B** migrieren. **Achtung:** `DELETE` entfernt Config-Entry, Registry-
  Entities und Device, **nicht** die Store-Daten; eine Wiederanlage erzeugt neue
  `entry_id`s, wodurch die Historie nicht mehr zugeordnet ist. Historie ist daher nur
  über die Snapshot-Route (Phase 4) wiederherstellbar, nicht über „neu anlegen".
  Die E2E-Fixture-Personen werden erst **nach** dem Release mit
  `scripts/e2e_bootstrap.py` (`VERSION = 3`) neu angelegt. Fremde Domains bleiben
  unberührt; die Entfernung ist mit anderen Agenten auf der geteilten Instanz
  abzustimmen (kurzes Wartungsfenster).
- Ohne Isolation wäre der Erstlauf kein kontrollierter Zwei-Entry-Test; die entfernten
  Test-Entries lassen sich aus den Snapshots bzw. per Bootstrap wiederherstellen.
- Entries **ohne `device_id`** werden live nicht erzeugt (Projekt-Invariante); dieser
  Pfad ist ausschließlich durch die Unit-Tests in §6.1 abgedeckt („nur Unit").

#### Phase 1 — Migration

10. Branch mit der Implementierung syncen
    (`/home/hermes/ha-test/bin/sync /home/hermes/repos/ha-health-o-mat`).
    Der Neustart löst `async_migrate_entry` für **A** und **B** aus (Multi-Entry-Test);
    weitere `health_o_mat`-Entries existieren im Erstlauf nicht (Phase 0c).
11. Log prüfen: `docker compose logs --since 5m | grep -iE "migrat|Entity-ID|error"`.
    Erwartung im ersten Lauf:
    - **A**: Info-Zeile „auf Version 3 migriert", keine Warnung.
    - **B**: genau zwei Warnungen mit Paarliste (`target_occupied` für
      `…_quick_drink_1` und `…_lab_vitamin_d`); `core.config_entries` zeigt für **B**
      weiter `version: 2`; **B** ist nicht geladen (kein stiller Teil-Erfolg).
    - Bereits mögliche, nicht kollidierende Renames von **B** (Quick-Slots 2-4) dürfen
      angewendet sein — das ist der definierte Teil-Zustand für den Retry.

#### Phase 2 — Verifikation Entry A (Soll/Ist)

| Prüfung | Erwartung |
|---|---|
| Neue IDs vorhanden | `button.<prefixA>_quick_drink_1…4`, `sensor.<prefixA>_lab_vitamin_d`, `…_lab_ferritin_gesamt`, `…_lab_h_moglobin` |
| Alte IDs weg | obige alte IDs nicht mehr in Registry, `GET /api/states/<alte_id>` → 404 |
| `unique_id` unverändert | Mengendifferenz der `unique_id`s vor/nach = **leer**; pro Entity identisch |
| `original_name` unverändert | Diff leer (Labels/Nutzertexte bleiben) |
| `device_id`/Registry-Anzahl | unverändert, keine neuen/doppelten Einträge |
| Registry-Metadaten | `entity_category`, `labels`, `aliases`, `area_id`, `hidden_by`, `disabled_by` unverändert (nur `new_entity_id` gesetzt) |
| Config-Entry-Version | **A** = `3`; **B** = `2` (Negativfall) |
| Store/Historie | Store-Datei unverändert; Summen/Laborwerte identisch. Recorder: `states_meta`/`statistics_meta` sind auf die neue `entity_id` umgeschrieben; **Statistik unter der neuen `statistic_id`/Entity-ID vorhanden** und `history/history_during_period` liefert die alten Zustände über die neue ID. Historische `states`-Zeilen selbst werden **nicht** umgeschrieben (kein Rewrite der Rohzeilen). |
| States | neue IDs liefern Werte (`GET /api/states`), keine `unavailable`-Häufung |
| Multi-Entry | **A** und **B** laufen im selben Pass; A migriert, B bleibt kollisionsbedingt auf Version 2 — keine Vermischung der Präfixe. Die E2E-Personen werden erst nach dem Release neu angelegt (Phase 0c). |
| Idempotenz | zweiter Neustart (erneut `bin/sync`): Registry-Diff für **A** leer, Version bleibt 3 |

#### Phase 3 — Negativprobe auflösen (Retry, verbindlich)

12. **Quick-Kollision** von **B** auflösen (Registry-Update zurück auf
    `button.<prefixB>_book_custom_amount`), neu starten. Erwartung: **B** scheitert
    weiterhin, aber **nur** wegen der Lab-Kollision (eine Warnung); die Quick-Slots
    1-4 sind jetzt umbenannt (Retry hat den offenen Rest nachgeholt); Version bleibt 2.
13. **Lab-Kollision** auflösen (Registry-Update zurück auf
    `sensor.<prefixB>_crp`), neu starten. Erwartung: **B** migriert vollständig,
    Version 3, `sensor.<prefixB>_lab_vitamin_d` vorhanden, alle `unique_id`s stabil.
14. Noch ein Neustart (`bin/sync`): kein Registry-Diff, Version bleibt 3 — die
    Migration ist idempotent, auch nach einem Teil-Lauf.

#### Phase 4 — Aufräumen und Rollback-Pfad

15. Beide Test-Personen über
    `DELETE /api/config/config_entries/entry/<entry_id>` entfernen; prüfen, dass ihre
    Registry-Entities/Devices verschwinden und **fremde** Entries unberührt sind.
16. **Snapshots bis nach dem Release aufbewahren** (mindestens bis der Post-Release-
    HACS-Update-Test abgeschlossen ist): `.tmp/registry.before.json`,
    `.tmp/device_registry.before.json`, `.tmp/config_entries.before.json`,
    `.tmp/health_o_mat_store.before.json`. Erst danach löschen — nie committen.
17. **Restore-Prozedur (nur bei Bedarf, Testinstanz):**
    1. HA stoppen: `/home/hermes/ha-test/bin/down` (`docker compose down` entfernt den
       Container; die Daten liegen im Bind-Mount `/home/hermes/ha-test/config`).
    2. **Immer alle drei Dateien gemeinsam** zurückholen — sonst steht der Entry auf
       Version 3 bei alten IDs, und der Handler läuft nie wieder (`version < VERSION`
       ist dann falsch):
       `cp .tmp/registry.before.json /home/hermes/ha-test/config/.storage/core.entity_registry`
       `cp .tmp/device_registry.before.json /home/hermes/ha-test/config/.storage/core.device_registry`
       `cp .tmp/config_entries.before.json /home/hermes/ha-test/config/.storage/core.config_entries`
    3. Die `health_o_mat`-Store-Datei nur zurückspielen, wenn Daten beschädigt wurden
       (die Migration ändert sie nicht).
    4. HA starten: `/home/hermes/ha-test/bin/up`
    5. **Acceptance nach Restore:** `version == 2` für **A** und **B**,
       `unique_id`-Menge == Snapshot, Registry-Anzahl == Snapshot.
    Der Restore überschreibt alle Änderungen seit dem Snapshot — nur auf der
    Testinstanz und nur für die eigene Domain anwenden.
18. Kein `bin/reset`; fremde Domains/Entries bleiben unberührt.

### 6.4 E2E-Suite

`tests_e2e/` enthält **keine** hartkodierten alten Quick-Drink-/Custom-Marker-IDs
(Volltextsuche über `tests_e2e/`: keine Treffer für `glas_wasser`, `tasse_kaffee`,
`vitamin_d`). Die Labor-E2E lesen die `entity_id` über die `unique_id` aus der
Registry (`test_lab_values_e2e.py:193-225,400-404`) und prüfen nur `sensor.` +
`unique_id` — sie bleiben nach der Migration grün. Ergänzung: dort zusätzlich
asserten, dass die Custom-Marker-`entity_id` auf `_lab_<key>` endet (verschärft die
Aussage, ohne neue Kopplung an Labels).

Ablauf: Nach §6.3 die Suite gegen die migrierte Instanz laufen lassen
(`HASS_BASE_URL=http://127.0.0.1:8123 pytest tests_e2e/ -v`); die Fixture-Personen
werden beim Bootstrap ggf. neu angelegt (dann direkt mit `VERSION = 3`) — beide Pfade
(migriert und frisch) müssen grün sein.

### 6.5 Akzeptanzkriterien

1. Kein Datenverlust: Store-Inhalt, Summen und Laborwerte vor/nach identisch.
2. Keine doppelten/verwaisten Entities: Registry-Anzahl unverändert, jede migrierte
   Entity hat genau einen Eintrag, keine Neuanlage.
3. `unique_id`, `original_name`, `device_id` unverändert (Mengen-Diff leer).
4. Migration idempotent (zweiter Lauf no-op) und fail-closed bei Kollision
   (Version bleibt, Retry beim nächsten Start, Warnung mit Paarliste).
5. Recorder-Metadaten (`states_meta`, `statistics_meta`) sind auf die neue `entity_id`
   umgeschrieben; Statistik unter der neuen `statistic_id` sichtbar.
6. `pytest -q`, `ruff check .`, `ruff format --check .`, `pytest tests_e2e/` grün.
7. Registry-Felder `entity_category`, `labels`, `aliases`, `area_id`, `hidden_by` und
   `disabled_by` sind vor/nach der Migration identisch (nur `new_entity_id` wird
   gesetzt).
8. Ein hand-renamed **Kandidat** blockiert die Migration nicht: er bleibt unverändert
   (`custom_entity_id`, Warnung) und die Version wird gesetzt. Ein hand-renamed
   **Anker** leert das Anker-Präfix nicht, solange mindestens zwei Anker es stützen
   (Produktiv-Regression Caro/Daniel, §2.3).

---

## 7. Risiken

| ID | Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|---|
| R-1 | Nutzer-Automationen/Skripte/Dashboards referenzieren alte IDs | Brüche nach dem Update, obwohl nur ein MINOR-Sprung erscheint | MINOR `0.17.0` mit **prominenter** 💥-Migrations-Notiz (§5.3/§5.4): Alt→Neu-Tabelle, Anpassungsliste, Beispiele im Repo aktualisiert; keine Auto-Reparatur möglich |
| R-2 | `suggested_object_id` nutzt internes HA-API (`platform_data`, `_name_internal`) | stiller Bruch nach HA-Refactor: Neuregistrierungen wieder lokalisiert | A-4-Regressionstest gegen die Dev-Instanz; Migration selbst ist davon unabhängig (keine Translation-Ableitung) |
| R-3 | Ziel belegt (`target_occupied`) oder nicht auflösbarer `device_slug` | Entry wird nicht geladen (fail-closed, `MIGRATION_ERROR`) | Skip + Warnung mit Paarliste (`target_occupied`, `device_slug_ambiguous`/`_unresolved`), Version bleibt, Retry; Negativprobe §6.3; Release-Hinweis zur Auflösung. `custom_entity_id` blockiert **nicht** (§3.1/§3.3) |
| R-4 | Mehrere Entries laufen gleichzeitig durch die Migration | falsche Präfixe/Kollisionen | Plan wird pro Entry aus dessen eigenen Entities gebildet; Kollisionsprüfung global über Registry+States; Multi-Entry-Test §6.3 |
| R-5 | Custom-Marker-Key-Drift (Fremd-Client ohne `key`, Löschen eines Duplikats, Katalog-Wachstum) | `unique_id`-Wechsel → neue Entity, alte verwaist | A-2 (Key-Erhalt per Namens-Match); Katalog-Wachstum bleibt Restrisiko (R-6) |
| R-6 | Künftiger Katalog-Marker kollidiert mit bestehendem Custom-Key | `normalize` suffixiert den Custom-Key → `unique_id` ändert sich (Alt-Entity verwaist) | vorbestehendes Verhalten, nicht durch diese Migration verursacht; im Plan als bekannte Grenze dokumentieren (kein Fix in diesem Scope) |
| R-7 | Recorder schreibt `states_meta`/`statistics_meta` nicht wie erwartet um | Statistik/Verlauf unter alter ID nicht mehr auffindbar | Live-Verifikation §6.3 (Statistik unter neuer `statistic_id`); HA-Core behandelt `entity_registry_updated`; falls nicht, Folge-Issue + manuelle Statistik-Migration |
| R-8 | Nutzer hat eine Entity manuell umbenannt | **Kandidat:** bleibt unverändert (`custom_entity_id`, Warnung, kein Fehlschlag); **Anker:** wird toleriert, solange mindestens zwei Anker den Präfix stützen | Nutzerentscheidung gewinnt; kein Breaking-Risiko. Release-Hinweis: hand-vergebene IDs bleiben, die Migration erzwingt keine Uniformität |
| R-9 | HA < 2026.9 | Override-Fallback, andere ID-Generierung | Migration ist versionsunabhängig; `hacs.json` verlangt `2026.8.0`; Unit-Tests decken fehlenden Hint/Anker ab |
| R-10 | Pre-Pinning-Installationen mit lokalisierten **Katalog**-IDs (falls vorhanden) | bleiben lokalisiert, weil nicht `unique_id`-ableitbar | bewusst außerhalb des Scopes (§1.4); offener Punkt O-2 |
| R-11 | `device_slug` nicht eindeutig (umbenannter Device-Name, Area-Segment in `entity_id_parts`, zwei gleichwertige Anker-Cluster) oder **kein Hint + geteilte englische Ankersegmente** (Lab-only: `lab_crp`/`lab_creatinine`, Suffix-Token `lab` divergiert nicht) | Migration blockiert (fail-closed, `MIGRATION_ERROR`) | `device_slug_ambiguous`/`_unresolved` mit Paarliste; ein einzelner hand-renamed Anker wird toleriert (Mehrfach-Stützung), hand-renamed Kandidaten sind `custom_entity_id` und blockieren nie; Lab-only-mit-Hint wird akzeptiert, Lab-only-ohne-Hint bewusst nicht geraten; Unit-Gegenbeispiel (Nutzerlabels) + Lab-only-/Area-/Regressionstests (§6.1/§6.2); A-4; Nutzer kann Gerätenamen/Area bereinigen und neu starten |
| R-12 | `async_migrate_entries` nicht awaited (Coroutine) oder Race-`ValueError` | Renames laufen nie / `MIGRATION_ERROR` | B-1 `await` + expliziter Await-Test mit `AsyncMock` (§6.2); `ValueError` wird geloggt und fail-closed behandelt |

---

## 8. Auswirkungen + REQ-Vorschlag

### 8.1 Betroffene Dateien (Plan-Umfang)

| Bereich | Dateien |
|---|---|
| Neu | `custom_components/health_o_mat/migration.py`, `tests/test_entity_id_migration.py`, `tests/test_entry_migration.py`, `docs/RELEASE-NOTES-0.17.0.md` |
| Migration/Flow | `custom_components/health_o_mat/__init__.py`, `config_flow.py`, `logic.py`, `ws_api.py`, `restore.py` |
| Entities | `custom_components/health_o_mat/button.py`, `sensor.py` |
| Tests | `tests/conftest.py`, `tests/test_logic.py`, `tests/test_config_flow.py`, `tests/test_wave_a.py`, `tests/test_translations.py`, `tests/test_dashboards.py`, `tests_e2e/test_lab_values_e2e.py`, `scripts/e2e-live-test.sh` |
| Release | `manifest.json`, `www/health-o-mat-card.js`, `www/health-o-mat-labs-card.js`, `www/health-o-mat-panel.js`, `www/health-o-mat-panel-views.js`, `www/health-o-mat-panel-admin.js`, `CHANGELOG.md` |
| Beispiele | `examples/dashboard.yaml`, `examples/dashboard-mini.yaml`, `examples/dashboard-mushroom.yaml` |
| README | `README.md` (Button-Beispiel `…_glas_wasser`, Kasten „Entity-IDs ab 0.17.0", Migrations-/Cleanup-Hinweis) |

Nicht betroffen: Store-Schema, Backup-Format, CSV-Spalten, Services/WS-Verträge,
Diagnostics, `unique_id`s.

### 8.2 REQ-Vorschlag (für `docs/REQUIREMENTS.md`, nicht Teil dieser Spec-Änderung)

> **REQ-HOM-130 — Entity-ID-Migration auf sprachunabhängige, einheitliche `object_id`s**
> **Priorität:** P1 · **Aufwand:** L · **Typ:** Breaking Entity-IDs, bewusst als
> MINOR `0.17.0` veröffentlicht (§5.4)
>
> **Problem:** Zwei Entity-Klassen erzeugen `object_id`s aus Nutzertext/ deutschen
> Default-Labels (`QuickDrinkButton` → `…_glas_wasser`, Custom-`LabValueSensor` →
> `…_vitamin_d`). Sie sind sprachunabhängig und stabil, aber nicht englisch/ASCII und
> damit inkonsistent zu den 23 konformen Klassen (Audit F-1/F-2).
>
> **Ziel:** Nach dem Update folgen alle `object_id`s einem einheitlichen,
> sprachunabhängigen Schema: Quick-Drinks `{device_slug}_quick_drink_<n>` (1-basiert),
> Custom-Marker `{device_slug}_lab_<key>`. Der Bestand wird über einen
> `async_migrate_entry`-Pass (`VERSION 2 → 3`) migriert; `unique_id`, `original_name`,
> `device_id`, Store und Verlauf bleiben unverändert. Kollisionen führen zu einem
> sichtbaren, wiederholbaren Fehlschlag (Version bleibt, Warnung mit Paarliste);
> hand-renamed Kandidaten (`custom_entity_id`) bleiben unverändert — Warnung, **kein**
> Fehlschlag.
> Zusätzlich: Kategorie-Validierung (A-1), Key-Erhalt (A-2), Drift-Test
> `WELLBEING_STATES` (A-3), E2E-Regression für englische IDs (A-4).
>
> **Akzeptanzkriterien:**
> 1. Nach Migration sind die IDs der Standard-Quick-Drinks `…_quick_drink_1…4` und
>    Custom-Marker `…_lab_<key>`; alte IDs existieren nicht mehr.
> 2. `unique_id`s sind vor/nach identisch; `original_name` und `device_id` unverändert.
> 3. Verlauf/Statistik ist unter der neuen `entity_id` verfügbar; Store-Inhalt
>    unverändert.
> 4. Zweiter Start ändert nichts (Idempotenz); Kollision oder nicht eindeutiger
>    `device_slug` → Version bleibt, Warnung mit Paarliste, Retry beim nächsten Start,
>    Entry wird nicht halb migriert geladen. Ein hand-renamed Kandidat
>    (`custom_entity_id`) sowie ein einzelner hand-renamed Anker blockieren die
>    Migration nicht.
> 5. `LAB_CATEGORIES`-Fremdwerte fallen auf `other`; keylose Marker erben bei
>    Namensgleichheit den bestehenden `key`.
> 6. `pytest -q`, `ruff`, `pytest tests_e2e/` grün; Live-Migration auf `ha-test`
>    inkl. Negativprobe dokumentiert.
>
> **Bezug:** Audit `docs/reviews/entity-id-stability-audit.md` §5 B-1; baut auf
> REQ-HOM-101 (Config-Entry-Migration v1→v2) auf; Release 0.17.0.

---

## 9. Offene Punkte

Die in der Aufgabe genannten Fragen sind **entschieden** und daher keine offenen
Punkte: Custom-Marker-Schema = `lab_<key>` (§1.3), Indexbasis = 1-basiert (§2.1).

Echt offen (blockieren die Implementierung nicht):

1. **O-1 — Kommunikation über das Log hinaus.** Der Vertrag nutzt heute
   `_LOGGER.warning`. Offen: (a) eine HA-Repair-Integration
   (`ir.async_create_issue`) für den Kollisions-/`device_slug_ambiguous`-Fall, damit
   nicht-technische Nutzer den blockierten Entry sehen; (b) eine
   `persistent_notification` **nach erfolgreicher Migration** („Entity-IDs geändert,
   Automationen/Dashboards prüfen") — gerade weil der MINOR-Sprung den Bruch nicht
   erwarten lässt. Aufwand/i18n müssten mitgeplant werden. Empfehlung: in 0.17.0
   log-only (fail-closed ist sichtbar genug), Repair-Issue + Erfolgs-Notification als
   Folge-REQ.
2. **O-2 — Pre-Pinning-Bestand bei Katalog-Entities.** Falls Support-Fälle auftauchen,
   in denen Katalog-/Wellbeing-Entities noch lokalisierte IDs tragen (registriert vor
   Einführung des Overrides), wäre ein zweiter, translation-abhängiger Pass nötig.
   Das würde eine Slug-Tabelle oder Zugriff auf die englischen Namen erfordern — genau
   die fragile Konstruktion, die §2.5 vermeidet. Entscheidung erst bei belegtem Bedarf.
3. **O-3 — Übersetzbare Default-Quick-Drink-Labels (Audit A-6).** Die IDs sind nach
   der Migration sprachunabhängig, die **Anzeigenamen** der Defaults bleiben aber
   deutsch („Glas Wasser" auch bei englischer Systemsprache). Das ist ein
   Produkt-/i18n-Thema außerhalb dieser Migration; beeinflusst keine IDs.
4. **O-4 — Folge-Issue: veraltetes Migrations-Rezept in der Doku.** `AGENTS.md` bzw.
   `.claude/rules/integration-development.md` zeigen `er.async_migrate_entries` in der
   `@callback`-Variante ohne `await`. Das ist in HA 2026.8/2026.9 falsch (Coroutine,
   B-1). Die Doku-Korrektur ist ein separates Folge-Issue, **nicht** Teil dieser Spec.
