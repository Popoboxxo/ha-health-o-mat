> ✅ **Handlungshinweis — Betroffen von `device_slug_ambiguous`?** Update auf
> 0.17.2 + ein HA-Neustart — die Entries stehen noch auf Version 2 und migrieren
> automatisch. Es ist kein Neuaufsetzen, kein Löschen und keine Änderung von
> `unique_id`s nötig.

# v0.17.2 — Migrationspräfix aus den Entities selbst

## Zusammenfassung

Patch-Release: Es behebt den verbliebenen `device_slug_ambiguous`-Fall aus 0.17.0/0.17.1.
Das Geräte-Präfix wird jetzt aus den Entities abgeleitet, die migriert werden sollen
(Sibling-Prefix), statt aus dem Gerätenamen oder einem einzelnen Device-Link. Eine
umbenannte Person, ein umbenanntes Gerät oder ein fremder `device_id` erzeugt nur noch
eine Warnung. Entries, die auf `config entry v2` mit `device_slug_ambiguous` hängen
geblieben sind, migrieren beim nächsten Start.

## Fixed

### Präfix aus den Migrationskandidaten (Sibling-Prefix)

Das Anker-Präfix des Geräts (z. B. `health_o_mat_caro`) wurde bisher aus dem Gerätenamen
bzw. einem einzelnen Device-Link abgeleitet. War die Person oder das Gerät umbenannt —
oder zeigte ein fremder `device_id` auf ein anderes Gerät —, ließ sich das Präfix nicht
mehr auflösen: die Migration brach mit `device_slug_ambiguous` ab und übersprang alle
Quick-Drink-Buttons; der Entry blieb auf Version 2.

Der Fix leitet das Präfix aus den **Sibling-IDs der zu migrierenden Entities** selbst ab
(`_sibling_prefix`). Damit gehört das Präfix konstruktionsbedingt zu den Entities, die
umbenannt werden — kein Gerätename, kein Hint und kein fremder `device_id` kann es
verschieben oder blockieren.

### Katalog-Labor-Sensoren bestätigen und trimmen

Die strukturellen Anker (zuerst die `lab_<key>`-Katalog-Marker) **bestätigen** das aus
den Kandidaten abgeleitete Präfix und **trimmen** es an Wortgrenzen. Eine vollständig
von Hand umbenannte Entity (`button.mein_wasser`) bildet ihre eigene First-Token-Gruppe
und kann das Präfix der Mehrheitsgruppe nicht mehr auslöschen — sie wird als
`custom_entity_id`-Warnung gemeldet. Zwei gleich große Gruppen bleiben echte Ambiguität
statt einer Vermutung. Der ältere Anker-/Hint-Pfad bleibt als Sekundärweg für Entries
ohne brauchbare Sibling-Gruppe erhalten.

### Hint-/Device-Abweichung ist nur eine Warnung

Weicht der Gerätename (`hint_mismatch`) oder der Device-Link (`device_id_mismatch`) vom
abgeleiteten Präfix ab, wird das **einmal** als Warnung protokolliert. Der Durchlauf
läuft weiter: `recoverable` bleibt `True`, es gibt keinen `MIGRATION_ERROR`, und die
betroffenen Entities werden migriert.

## Upgrade

1. Update über HACS installieren.
2. Home Assistant **vollständig neu starten** (ein Reload reicht nicht).
3. Betroffene Entries migrieren automatisch von Version 2 auf Version 3.
4. Im Log prüfen: eine Warnung zur Präfix-Bestätigung (`hint_mismatch` /
   `device_id_mismatch`) ist erwartbar und harmlos — die Migration ist durchgelaufen.
5. Optional: in der **Geräteansicht** prüfen, ob verwaiste Alt-Entities aus 0.17.0
   übrig sind, und diese entfernen — nie durch Ändern der `unique_id`.

## Kompatibilität

- Keine Änderung an `unique_id`s, am Store-Schema oder an Entity-IDs.
- Keine neuen Pflichtschritte für Installationen, die bereits fehlerfrei migriert haben.
- `config entry v2 → v3` bleibt der einzige Migrationsschritt.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.1...v0.17.2

---

> ✅ **Action required — affected by `device_slug_ambiguous`?** Update to 0.17.2 and
> restart Home Assistant — the entries are still on version 2 and migrate
> automatically. No re-setup, no deletion and no `unique_id` change is needed.

# v0.17.2 — Migration prefix derived from the entities themselves

## Summary

Patch release: it fixes the remaining `device_slug_ambiguous` case from 0.17.0/0.17.1.
The device prefix is now derived from the entities that are about to be migrated
(sibling prefix) instead of the device name or a single device link. A renamed person, a
renamed device or a foreign `device_id` only produces a warning. Entries that stayed on
`config entry v2` with `device_slug_ambiguous` migrate on the next start.

## Fixed

### Prefix from the migration candidates (sibling prefix)

The device anchor prefix (e.g. `health_o_mat_caro`) used to be derived from the device
name or a single device link. When the person or the device had been renamed — or a
foreign `device_id` pointed at another device — the prefix could no longer be resolved:
the migration aborted with `device_slug_ambiguous` and skipped every quick-drink button;
the entry stayed on version 2.

The fix derives the prefix from the **sibling ids of the entities being migrated**
themselves (`_sibling_prefix`). The prefix therefore belongs to the entities that are
renamed by construction — no device name, no hint and no foreign `device_id` can move or
block it.

### Catalog lab sensors confirm and trim

The structural anchors (`lab_<key>` catalog markers first) **confirm** the prefix derived
from the candidates and **word-boundary-trim** it. A completely hand-renamed id
(`button.mein_wasser`) forms its own first-token group and can no longer erase the
majority group's prefix — it is reported as a `custom_entity_id` warning. Two equally
large groups remain genuine ambiguity instead of a guess. The older anchor/hint path
stays as the secondary route for entries without a usable sibling group.

### Hint/device deviation is only a warning

If the device name (`hint_mismatch`) or the device link (`device_id_mismatch`) disagrees
with the derived prefix, it is logged **once** as a warning. The pass continues:
`recoverable` stays `True`, there is no `MIGRATION_ERROR`, and the affected entities are
migrated.

## Upgrade

1. Install the update via HACS.
2. **Restart Home Assistant completely** (a reload is not enough).
3. Affected entries migrate from version 2 to version 3 automatically.
4. Check the log: a prefix-confirmation warning (`hint_mismatch` /
   `device_id_mismatch`) is expected and harmless — the migration completed.
5. Optional: check the **device view** for orphaned old entities from 0.17.0 and remove
   them — never by changing `unique_id`s.

## Compatibility

- No change to `unique_id`s, the store schema or entity ids.
- No mandatory extra steps for installations that already migrated without errors.
- `config entry v2 → v3` remains the only migration step.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.1...v0.17.2
