---
service: balcony_battery_manager
typ: requirements
version: 1.2
status: current
stand: 2026-06-23
quellen: [README.md (ausführliche Spezifikation), custom_components/balcony_battery_manager, tests]
---

# Anforderungen: Balcony Battery Manager (HA Custom Integration)

> Code-unabhängige Soll-Beschreibung für eine Neuentwicklung von Grund auf (WAS/WARUM).

## 1. Zweck & Kontext
HACS-installierbare Home-Assistant-Integration (Domain `balcony_battery_manager`), die eine **zusätzliche
Balkonkraftwerk-Batterie** (Anker Solix 3 / Solarbank 3, via `thomluther/ha-anker-solix`) **anhand der
Messwerte einer bereits vorhandenen, größeren Dach-PV-Anlage mit Akku** steuert. Ziel: Netzeinspeise-
**Überschuss aufnehmen** (laden) und die **Hauptbatterie beim Entladen entlasten** – bewusst **ohne**
denselben zentralen Leistungsmesser, damit sich die Speicher nicht gegenseitig „ausspielen".
- **Nutzer:** HA-Haushalt mit Dach-PV+Akku und zusätzlicher Anker-Balkonbatterie.
- **Use-Cases:** Überschuss laden; Hauptbatterie entlasten; bei leerer Hauptbatterie Netzbezug decken.

## 2. Geltungsbereich
**In Scope:** zyklische Regelung (Zustandsautomat) aus gelesenen Messwerten, Ansteuerung der Anker-Entitäten
über **Standard-HA-Services**, UI-Konfiguration mit best-effort-Vorbelegung, Robustheit/Persistenz.
**Out of Scope:** direkte Cloud-/Hersteller-API der Anker-Batterie (nur über die anker_solix-Integration),
Steuerung der Hauptanlage, Energie-Forecasting.

## 3. Funktionale Anforderungen
- **FR-1 Eingänge (nur lesen):** Netz-/Hausleistung (vorzeichenbehaftet, Einheit auto/W/kW), Lade-/
  Entladeleistung Hauptbatterie (vorzeichenbehaftet), SOC + Lade-/Entladeleistung Balkonbatterie.
  Der **SOC der Hauptbatterie ist optional** – manche Dachsysteme (z. B. **E3DC via KNX**) exponieren keinen
  SOC-Sensor; fehlt er, wird lediglich die Netz-Unterstützung (FR-4 *grid_support*) stillschweigend übersprungen,
  die übrige Regelung läuft unverändert. Setup darf ohne main_soc nicht blockieren.
- **FR-2 Parameter (Defaults):** Max. Ladeleistung 1100 W, Max. Hauseinspeisung 800 W, Steuerintervall 300 s,
  Lade-Headroom 200 W, Entlade-Aktivierung 400 W / -Deaktivierung 100 W (Hysterese), Anteil Balkon 50 %,
  Sende-Totband 25 W, Fail-safe-Zeit 0, Netzbezug-decken an/SOC-leer 10 %/Aktivierung 50 W/Deaktivierung 20 W.
- **FR-3 Anker-Mapping:** Nutzungsmodus-Select (+ „manuell"-Wert, wird vor jedem Schreiben erzwungen),
  Entlade-/Ausgabe-Preset (W), AC-Lade-Schalter (optional), AC-Ladeleistung (W) – vom Nutzer gewählt.
  Das **AC-Ladeleistungsfeld akzeptiert Number ODER Select**: Geräte ohne AC-Lade-Number (Solarbank 3:
  nur `select.ac_input_limit`, 0…1200 W gestuft) werden unterstützt, indem der berechnete Sollwert auf die
  größte Option ≤ Ziel **abgerundet** wird (0 = aus). Der Schreib-Pfad unterscheidet `number.set_value` vs.
  `select.select_option` (auch `input_*`). **Hinweis:** Das Select begrenzt nur; das AC-Laden wird über den
  MQTT-Schalter `ac_charge` ausgelöst (in anker_solix zu aktivieren + als AC-Lade-Schalter zu mappen).
- **FR-7 Auto-Vorbelegung (best-effort, nur Vorschläge):** Die UI schlägt Eingänge, Steuer-Entitäten,
  **Vorzeichen** und den Manual-Modus-Wert aus drei Quellen in dieser Reihenfolge vor (nur leere Felder):
  (1) HA-Energie-Dashboard, (2) **Vendor-Muster E3DC** (entity_id-Muster `gridpowerconsumption` /
  `batterypowerconsumption`, da E3DC oft via KNX ohne HA-Device/Energy-Eintrag eingebunden ist; setzt
  `grid_export_positive=False`, `main_discharge_positive=False`), (3) **anker_solix** (Solarbank-Gerät mit
  `usage_mode`-Select; SOC nach geordneter Präferenz `state_of_charge` > `main_battery_soc`, nie ein
  Expansion-Pack; `battery_power` → `balcony_discharge_positive=False`; Manual-Wert aus den Select-Optionen).
  Jede Erkennung ist „eindeutig-oder-nichts"; falsche Zuordnungen sind strukturell ausgeschlossen, alles bleibt
  als `suggested_value` korrigierbar.
- **FR-4 Regellogik (Zustandsautomat je Intervall):** Modus-Arbitrierung DISCHARGING > CHARGING > IDLE.
  - **CHARGING:** `S = gemessene_Einspeisung + zuletzt_gesendete_Ladeleistung`;
    `ziel = clamp(S − Headroom, 0, Max_Lade)`; Stopp bei Balkon-SOC 100 %.
  - **DISCHARGING:** größerer Sollwert zweier Fälle, hart auf Max_Hauseinspeisung begrenzt:
    *relief* (Hauptbatterie entlasten, anteilig, Hysterese 400/100 W) und *grid_support* (Hauptbatterie leer +
    Netzbezug decken, Hysterese 50/20 W). Grund im Attribut `discharge_reason` (relief/grid_support/both).
  - **IDLE:** AC-Laden aus, Entlade-Preset 0.
- **FR-5 Entitäten:** `switch.*_enabled` (Master), `sensor.*_mode` (idle/charging/discharging/disabled),
  `sensor.*_target_charge`, `sensor.*_target_discharge`, `sensor.*_computed_surplus`.
- **FR-6 Services:** `enable`, `disable` (+ konfigurierte Deaktivierungs-Aktion), `recalculate_now`.

## 4. Nicht-funktionale Anforderungen
- **NFR-1 Robustheit gegen Anker-Versionen:** Steuerung nur über Standard-HA-Services
  (`number.set_value`, `select.select_option`, `switch.turn_on/off`); keine internen Anker-APIs.
- **NFR-2 Rekonstruktion über internen Zustand:** Berechnungen nutzen den **zuletzt gesendeten Sollwert**,
  nicht den nachhängenden Balkon-Leistungssensor (gegen Takten im 5-Minuten-Zyklus).
- **NFR-3 Fail-safe:** bei unavailable/unknown/None/unplausibel keine Neuberechnung; letzter sicherer Zustand
  bleibt; optional nach Ablauf auf „sicher" (alles 0). Grenzen hart erzwungen (nie > Max, nie negativ).
- **NFR-4 Persistenz/Concurrency:** Modus, zuletzt gesendete Sollwerte, Master-Status via Store; `asyncio.Lock`
  gegen Race-Conditions; Totband verhindert Doppel-Senden.
- **NFR-5 Async/Non-Blocking; HACS/HA-konform.**

## 5. Externe Schnittstellen & Verträge
- **Eingang:** konfigurierte HA-Sensoren (Netz/SOC/Leistungen) inkl. W/kW-Handling (intern immer Watt).
- **Ausgang:** Standard-HA-Services auf die gemappten Anker-Entitäten.
- **HA-Entitäten/Services** s. FR-5/FR-6.

## 6. Datenmodell
- **Konfig:** Eingangs-Entitäten + Einheiten/Vorzeichen, Parameter (s. FR-2), Anker-Mapping, Deaktivierungs-Aktion.
- **Store (Laufzeit):** mode, last_sent_charge, last_sent_discharge, master_enabled.

## 7. Integrationen & Abhängigkeiten
- **ha-anker-solix** (Solarbank-Gerät, anhand `usage_mode`-Select erkannt), HA-Energie-Dashboard und
  **E3DC-Vendor-Muster** (best-effort-Vorbelegung), HACS. Keine externen Server.
- **Referenz-Setup (verifiziert 2026-06-23):** Dach = E3DC via KNX (`sensor.e3dc_gridpowerconsumption`,
  `sensor.e3dc_batterypowerconsumption`, W, vorzeichenbehaftet; **kein** SOC-Sensor). Balkon = Anker Solarbank 3
  E2700 Pro (`sensor.solarbank_3_e2700_pro_state_of_charge` %, `…_battery_power` W neg=Entladung,
  `select.…_usage_mode` [backup|manual], `number.…_system_output_preset` W 0–800).

## 8. Constraints & Rahmenbedingungen
- **C-1:** reine UI-Konfiguration. **C-2:** Steuerintervall ≥ 300 s (Solarbank-Cloud aktualisiert ~5 min).
- **C-3:** Nutzungsmodus „manuell" vor jedem Sollwert erzwingen. **C-4:** intern in Watt rechnen.

## 9. Designentscheidungen (Rationale)
- **Getrennter Messpfad (kein gemeinsamer Zähler):** verhindert gegenseitiges „Ausspielen" der Speicher.
- **Steuerung via Standard-Services:** Versionsrobustheit gegenüber der Anker-Integration.
- **Sollwert-Rekonstruktion + Hysterese + Totband:** stabile Regelung trotz nachhängender/grobgetakteter Sensoren.

## 10. Akzeptanzkriterien
- **A-1:** Ladesollwert = clamp(S − Headroom, 0, Max); Stopp bei Balkon-SOC 100 %.
- **A-2:** relief aktiviert > 400 W, schwingt sich auf 50/50 ein, deaktiviert < 100 W.
- **A-3:** grid_support springt bei leerer Hauptbatterie + Netzbezug ein und drückt Bezug ≈ 0.
- **A-4:** identische Sollwerte werden dank Totband nicht erneut gesendet.
- **A-5:** unavailable-Eingänge lösen keine Neuberechnung aus (Fail-safe); Zustand bleibt nach Neustart erhalten.

## 11. Annahmen & offene Punkte
- Genau eine steuerbare Solarbank; Hauptanlage liefert verlässliche **Leistungs**-Sensoren (SOC optional, s. FR-1).
- Hauptbatterie-SOC fehlt bei E3DC/KNX → *grid_support* in diesem Setup deaktiviert (kein Fehler, nur Funktionsverzicht).

## 12. Änderungshistorie
| Version | Datum | Änderung |
|---|---|---|
| 1.0 | 2026-06-18 | Erstfassung als Clean-Room-requirements-Doc aus README/Code (Code v1.0.0) |
| 1.1 | 2026-06-23 | main_soc optional (FR-1); FR-7 Auto-Vorbelegung mit Vendor-Mustern (E3DC/KNX + anker_solix), Vorzeichen-/Manual-Vorschläge; Referenz-Setup E3DC+Solarbank 3 dokumentiert |
| 1.2 | 2026-06-23 | FR-3: AC-Ladeleistung akzeptiert Number ODER Select (Solarbank-3 `ac_input_limit`, Floor-Mapping); Prefill-Bugfix ac_charge-Switch statt ac_socket; AC-Lade-Trigger via MQTT-`ac_charge`-Switch dokumentiert |
