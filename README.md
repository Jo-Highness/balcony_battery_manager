# Balcony Battery Manager

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Eine Home-Assistant-Custom-Integration, die eine **zusätzliche Balkonkraftwerk-Batterie**
(Anker Solix 3 / Solarbank 3 E2700, eingebunden über
[`thomluther/ha-anker-solix`](https://github.com/thomluther/ha-anker-solix))
anhand der Messwerte einer **bereits vorhandenen, größeren Dach-PV-Anlage mit Akku**
steuert.

Ziel: Die Balkonbatterie nimmt **Netzeinspeise-Überschuss** auf (laden) und **entlastet die
Hauptbatterie** beim Entladen (anteilig mitversorgen) – **ohne** denselben zentralen
Leistungsmesser zu benutzen, damit sich die beiden Speicher nicht gegenseitig „ausspielen“.

> **English (short):** This integration steers an additional Anker Solix balcony battery
> from the measurements of an existing larger roof-PV + battery system. It absorbs grid
> export surplus and helps the main battery discharge, deliberately **without** sharing the
> central power meter so the two storages don't fight each other. All control is done through
> standard HA services (`number.set_value`, `select.select_option`, `switch.turn_on/off`), so
> the plugin stays robust against Anker-integration version changes.

---

## Installation

### HACS (empfohlen)
1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories*.
2. Repository `https://github.com/Jo-Highness/balcony_battery_manager`, Kategorie *Integration*.
3. „Balcony Battery Manager“ installieren, Home Assistant neu starten.

### Manuell
`custom_components/balcony_battery_manager/` nach `<config>/custom_components/` kopieren und HA neu starten.

Danach: **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Balcony Battery Manager“**.

---

## Konfiguration

Die gesamte Konfiguration läuft über die UI (Config-Flow), nachträglich jederzeit über
**Konfigurieren** (Options-Flow) änderbar. Es gibt **kein YAML-Setup**.

> [!TIP]
> **Automatische Vorbelegung (best effort).** Beim **erstmaligen** Einrichten versucht das
> Plugin, sinnvolle Sensoren/Entitäten vorzuschlagen — du musst jeden Vorschlag aber
> bestätigen oder überschreiben:
> - **Netz- und Hauptbatterie-Felder** aus dem **HA-Energie-Dashboard**: Über die dort
>   hinterlegten Energie-Statistiken (kWh) wird das jeweilige Gerät aufgelöst und am selben
>   Gerät der passende **Leistungs-** (W/kW) bzw. **SoC-Sensor** (%) gesucht. Eine kWh-Entität
>   wird **nie** in ein Leistungsfeld geschrieben.
> - **E3DC** (Dachsystem) per **Muster**, falls es – wie häufig über KNX/RSCP – **kein** HA-Gerät
>   und keinen Energie-Dashboard-Eintrag hat: erkannt werden `sensor.*gridpowerconsumption` →
>   Netzleistung und `sensor.*batterypowerconsumption` → Hauptbatterie-Leistung. Die
>   **Vorzeichen** werden gleich passend gesetzt (E3DC-Konvention: Netz positiv = Bezug,
>   Batterie positiv = Laden → beide „positiv = Einspeisung/Entladung“-Schalter **aus**).
> - **Balkon- und Anker-Steuer-Felder** aus der `anker_solix`-Integration (Solarbank-Gerät, am
>   `usage_mode`-Select erkannt). SOC nach Präferenz `state_of_charge` > `main_battery_soc`
>   (nie ein Expansion-Pack); `battery_power` (negativ = Entladung → Schalter aus); der
>   Manual-Modus-Wert wird aus den Select-Optionen abgeleitet. Zuordnung über
>   `translation_key`/`unique_id`-Suffixe, nicht über lokalisierte Namen.
>
> Vorgeschlagen wird nur, wenn die Zuordnung **eindeutig** ist; sonst bleibt das Feld leer
> (kein Fehler). Auch **Vorzeichen** und **Manual-Wert** sind nur Vorschläge und korrigierbar.
> Im Options-Flow wird **nicht** vorbelegt. Hinweis: Viele Anker-Steuer-Entitäten (z. B.
> *System output*, *AC input limit*) sind in `anker_solix` standardmäßig **deaktiviert** und
> werden erst nach dem Aktivieren vorgeschlagen.

> [!NOTE]
> **Referenz-Setup (out-of-the-box getestet): E3DC-Dachanlage + Anker Solarbank 3.** Mit dieser
> Kombination werden die Pflichtfelder automatisch vorbelegt – du musst die Vorschläge nur
> bestätigen:
>
> | Konfig-Feld | vorgeschlagene Entität |
> |-------------|------------------------|
> | Netzleistung | `sensor.e3dc_gridpowerconsumption` (W) · Einspeisung=positiv **aus** |
> | Hauptbatterie-Leistung | `sensor.e3dc_batterypowerconsumption` (W) · Entladung=positiv **aus** |
> | SOC Hauptbatterie | *(E3DC liefert keinen SOC → leer lassen; nur Netz-Unterstützung entfällt)* |
> | SOC Balkon | `sensor.solarbank_3_e2700_pro_state_of_charge` (%) |
> | Balkon-Leistung | `sensor.solarbank_3_e2700_pro_battery_power` (W) · Entladung=positiv **aus** |
> | Nutzungsmodus-Select + Wert | `select.solarbank_3_e2700_pro_usage_mode` → `manual` |
> | Entlade-/Ausgabe-Preset | `number.solarbank_3_e2700_pro_system_output_preset` (W, 0–800) |
> | AC-Lade-Schalter / -Number | *(in diesem Setup nicht zwingend – optional leer)* |

### 1. Eingangs-Messwerte (nur lesen)
| Feld | Bedeutung |
|------|-----------|
| Netz-/Hausleistungssensor | Leistung am Netzübergabepunkt der Hauptanlage |
| Einheit der Netzleistung | `auto` / `W` / `kW` (siehe *W/kW-Handling* unten, Default: `auto`) |
| Positiver Wert = Einspeisung | Vorzeichen-Konvention (Default: an). Bei umgekehrter Zählung deaktivieren. |
| SOC Hauptbatterie (%) | Ladestand des Dach-Akkus – **optional**; nur nötig für die *Netz-Unterstützung*. Fehlt der Sensor (z. B. E3DC via KNX), Feld einfach leer lassen. |
| Lade-/Entladeleistung Hauptbatterie | + Einheit + „Entladung = positiv“ (Default: an) |
| SOC Balkonkraftwerk-Batterie (%) | Ladestand der Anker-Batterie |
| Lade-/Entladeleistung Balkonkraftwerk | + Einheit + „Entladung = positiv“ (Default: an) |

> **W/kW-Handling.** Jeder Leistungssensor hat ein Einheiten-Dropdown (`auto`/`W`/`kW`).
> Bei `auto` wird die Einheit des Sensors gelesen: `kW` wird intern mit 1000 multipliziert,
> `W` unverändert übernommen, eine unbekannte/fehlende Einheit als W behandelt (mit einmaliger
> Warnung im Log). `W`/`kW` erzwingen die Umrechnung unabhängig von der Sensoreinheit. Intern
> rechnet die Steuerung **immer in Watt**. Bestehende Konfigurationen laufen dank Default
> `auto` ohne Migration weiter.

### 2. Grenzwerte / Parameter
| Parameter | Default | Bedeutung |
|-----------|--------:|-----------|
| Max. Ladeleistung Balkon (W) | 1100 | harte Obergrenze Laden |
| Max. Hauseinspeisung Balkon (W) | 800 | harte Obergrenze Entladen |
| Steuerintervall (s) | 300 | siehe *Solarbank-5-Minuten-Zyklus* |
| Lade-Headroom (W) | 200 | Puffer, der weiter ins Netz eingespeist wird (gegen Takten) |
| Entlade-Aktivierungsschwelle (W) | 400 | ab dieser Hauptbatterie-Entladung wird zugeschaltet |
| Entlade-Deaktivierungsschwelle (W) | 100 | darunter zurück auf 0 (Hysterese) |
| Anteil Balkon an Gesamt-Entladung (%) | 50 | Lastaufteilung Haupt ↔ Balkon |
| Sende-Totband (W) | 25 | neuer Sollwert nur, wenn Änderung > Totband |
| Fail-safe nach Datenausfall (s) | 0 | 0 = letzten Zustand unbegrenzt halten; >0 = danach auf „sicher“ (alles 0) |
| Netzbezug decken, wenn Hauptbatterie leer | an | aktiviert den zweiten Entlade-Fall (siehe unten) |
| Hauptbatterie gilt als leer ab/unter (%) | 10 | SOC-Schwelle, ab der die Hauptbatterie als leer gilt |
| Aktivierungsschwelle Netz-Unterstützung (W) | 50 | Netzbezug, ab dem der Balkon einspringt |
| Deaktivierungsschwelle Netz-Unterstützung (W) | 20 | Netzbezug, unter dem wieder gestoppt wird (Hysterese) |

> **Warum kein Intervall < 300 s?** Die Solarbank 2/3 aktualisiert ihre Cloud-Werte nur
> ca. alle 5 Minuten. Gesendete Steuerbefehle wirken zwar sofort, sind in den Sensoren aber
> erst nach bis zu ~6 Minuten sichtbar. Schnellere Zyklen erzeugen daher nur unnötige
> Cloud-Last und verrauschen die Regelung – ohne Mehrwert.

### 3. Anker-Steuer-Entitäten (Mapping)

> [!IMPORTANT]
> **Welche Anker-Entitäten sind hier gemeint?** Die `ha-anker-solix`-Integration steuert
> die Solarbank **nicht** über einen direkten Wattbefehl, sondern über mehrere Entitäten,
> deren genaue IDs je nach Geräte-/Integrationsversion variieren. Deshalb wählst **du** die
> Entitäten aus; das Plugin schreibt nur über Standard-HA-Services.
>
> | Konfig-Feld | typische Anker-Entität |
> |-------------|------------------------|
> | Nutzungsmodus-Select (optional) + „manueller“-Optionswert | `select.*_usage_mode` → Wert **„manuell“ / „Custom“**. Wird vor jedem Sollwert-Schreiben erzwungen, sonst überschreibt Ankers eigene Automatik die Werte. |
> | Number Entlade-/Ausgabe-Preset (W) | `number.*_home_load_preset` / `*_output_power` (W) für die **Entladung** |
> | AC-Lade-Schalter (optional) | `switch.*_ac_charge` |
> | Number AC-Ladeleistung/-limit (W) | `number.*_ac_charging_power` (W) für die **Ladung** |
>
> **Verhalten bei Deaktivierung** des Plugins: *„alles auf 0 / sicher“* (Default) **oder**
> *„Anker-Modus wiederherstellen“* (dann zusätzlich den wiederherzustellenden Modus-Wert
> angeben, z. B. `Smart`/`Auto`).

---

## Regellogik (Zustandsautomat)

Ausgewertet wird im konfigurierten Intervall. **Wichtig:** Für alle Rekonstruktionen wird der
**vom Plugin zuletzt gesendete Sollwert** (interner Zustand) benutzt, **nicht** der
nachhängende Balkon-Leistungssensor.

**Modus-Arbitrierung pro Intervall** (Priorität):
1. **DISCHARGING**, wenn die Entladelogik aktiv sein soll.
2. sonst **CHARGING**, wenn echter Einspeise-Überschuss vorhanden ist und Balkon-SOC < 100 %.
3. sonst **IDLE**.

### Laden (CHARGING)
Die eigene Ladung senkt den gemessenen Export, daher wird der wahre Überschuss rekonstruiert:

```
S                 = gemessene_Einspeisung + zuletzt_gesendete_Ladeleistung
ziel_ladeleistung = clamp(S − Lade_Headroom, 0, Max_Ladeleistung)
```

Ohne diese Rekonstruktion würde der Wert über die 5-Minuten-Zyklen takten. Bei Balkon-SOC =
100 % wird das Laden gestoppt; Wiederaufnahme erst, wenn SOC < 100 % **und** wieder Überschuss.

Es gibt **zwei** Auslöser für das Entladen; pro Intervall wird der **größere** der beiden
Sollwerte gefahren (hart auf `Max_Hauseinspeisung` begrenzt). Welcher Grund gerade greift,
steht im Attribut `discharge_reason` des Mode-Sensors (`relief` / `grid_support` / `both`).

**Fall 1 – Hauptbatterie entlasten (`relief`) – mit Hysterese**
- **Aktivierung:** Hauptbatterie-Entladung > *Aktivierungsschwelle* (Default 400 W).
- **Sollwert je Intervall:**
  ```
  gesamt              = Hauptbatterie_Entladung + zuletzt_gesendete_Entladeleistung
  ziel_entladeleistung = clamp(gesamt × Anteil, 0, Max_Hauseinspeisung)
  ```
  Beispiel (Anteil 50 %): Haupt liefert anfangs 400 W → Ziel 200 W; eingeschwungen 200 W
  Haupt + 200 W Balkon, stabil.
- **Deaktivierung:** Hauptbatterie-Entladung < *Deaktivierungsschwelle* (Default 100 W) →
  Balkon sofort auf 0, Zustand → IDLE.

**Fall 2 – Hauptbatterie leer, Netzbezug decken (`grid_support`)**
Wenn die **Hauptbatterie leer** ist (SOC ≤ *Hauptbatterie-leer-Schwelle*, Default 10 %),
**Leistung aus dem Netz** bezogen wird und die **Balkonbatterie noch Ladung** hat, springt
der Balkon ein und stellt Energie bis zum Hausverbrauch bereit (drückt den Netzbezug
Richtung 0). Auch hier wird über den zuletzt gesendeten Wert rekonstruiert, weil die eigene
Einspeisung den gemessenen Netzbezug verringert:
```
netz_defizit          = zuletzt_gesendete_Entladeleistung − gemessene_Netzleistung
ziel_entladeleistung  = clamp(netz_defizit, 0, Max_Hauseinspeisung)
```
(`gemessene_Netzleistung` ist vorzeichenbehaftet: positiv = Einspeisung, negativ = Bezug;
bei 300 W Bezug ist `netz_defizit = B + 300`.) Aktivierung ab *Aktivierungsschwelle
Netz-Unterstützung* (Default 50 W Bezug), Deaktivierung unter *Deaktivierungsschwelle*
(Default 20 W) – Hysterese gegen Pendeln. Über den Schalter *„Netzbezug decken …“*
abschaltbar. Beispiel: Hauptbatterie 5 %, Haus zieht 300 W aus dem Netz → Balkon entlädt
300 W, Netzbezug ≈ 0.

### IDLE
AC-Laden aus, Entlade-Preset 0. Dank Totband werden identische Sollwerte **nicht**
wiederholt gesendet.

### Robustheit
- **Fail-safe:** Ist ein benötigter Eingang `unavailable`/`unknown`/`None` oder
  offensichtlich falsch (z. B. SOC < 0), wird **nichts** neu berechnet – der letzte sichere
  Zustand bleibt erhalten und es wird gewarnt. Optional nach längerem Ausfall auf „sicher“.
- **Grenzen** werden hart erzwungen (nie > Max, nie negativ).
- **HA-Neustart:** Modus, zuletzt gesendete Sollwerte und Master-Schalter-Status werden über
  `Store` persistiert und wiederhergestellt.
- **Race-Conditions** zwischen Timer und Aktionen sind über `asyncio.Lock` abgesichert.

---

## Erzeugte Entitäten
| Entity | Beschreibung |
|--------|--------------|
| `switch.balcony_battery_manager_enabled` | Master-Schalter (Steuerung aktiv/inaktiv) |
| `sensor.balcony_battery_manager_mode` | aktueller Zustand: `idle` / `charging` / `discharging` / `disabled` |
| `sensor.balcony_battery_manager_target_charge` | aktueller Lade-Sollwert (W) |
| `sensor.balcony_battery_manager_target_discharge` | aktueller Entlade-Sollwert (W) |
| `sensor.balcony_battery_manager_computed_surplus` | berechneter Überschuss *S* (W, Transparenz/Debug) |

> Hinweis: Bei deutscher HA-Oberfläche können die **angezeigten Namen** lokalisiert sein; die
> Entity-IDs oben gelten für die englische Standard-Benennung.

## Dienste
| Service | Wirkung |
|---------|---------|
| `balcony_battery_manager.enable` | Steuerung einschalten (mit sofortiger Neuberechnung) |
| `balcony_battery_manager.disable` | Steuerung ausschalten + konfigurierte Deaktivierungs-Aktion |
| `balcony_battery_manager.recalculate_now` | sofortige Neuberechnung außerhalb des Intervalls |

---

## Beispiel-Dashboard

```yaml
type: entities
title: Balkon-Batterie-Manager
entities:
  - entity: switch.balcony_battery_manager_enabled
    name: Steuerung
  - entity: sensor.balcony_battery_manager_mode
    name: Zustand
  - entity: sensor.balcony_battery_manager_target_charge
    name: Lade-Sollwert
  - entity: sensor.balcony_battery_manager_target_discharge
    name: Entlade-Sollwert
  - entity: sensor.balcony_battery_manager_computed_surplus
    name: Berechneter Überschuss
```

---

## Tests

```bash
pip install -r requirements_test.txt
pytest
```

Abgedeckt: Lade-Sollwert inkl. Überschuss-Rekonstruktion & Headroom, Stopp bei SOC 100 %,
Entlade-Aktivierung > 400 W, eingeschwungene 50/50-Aufteilung, Deaktivierung < 100 W
(Hysterese), Totband (kein Doppel-Senden), Fail-safe bei unavailable-Eingängen, Persistenz
über Neustart sowie Setup/Unload.

## Lizenz
MIT – siehe [LICENSE](LICENSE).
