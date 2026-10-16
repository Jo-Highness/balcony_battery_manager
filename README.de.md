# Balcony Battery Manager

**Lokale Home-Assistant-Steuerung für eine Anker SOLIX Solarbank 4 (E5000 Pro):** Sie speist ein, wenn das Haus viel aus dem Hauptakku zieht, lädt aus PV-Überschuss, wenn PV allein die Solarbank bis Sonnenuntergang nicht füllt, und versorgt das Haus, wenn der Hauptakku leer ist.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Validate](https://github.com/Jo-Highness/balcony_battery_manager/actions/workflows/validate.yml/badge.svg)](https://github.com/Jo-Highness/balcony_battery_manager/actions/workflows/validate.yml)
[![Tests](https://github.com/Jo-Highness/balcony_battery_manager/actions/workflows/test.yml/badge.svg)](https://github.com/Jo-Highness/balcony_battery_manager/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Home Assistant 2025.2+](https://img.shields.io/badge/Home%20Assistant-2025.2%2B-41BDF5.svg)](https://www.home-assistant.io)

🇬🇧 [English version](README.md)

> **Diese Integration steuert echte Hardware.** In jedem Regelzyklus schreibt sie
> einen Leistungssollwert und eine Lade-/Entladerichtung an deine Solarbank.
> Lies [Sicherheit](#sicherheit), bevor du sie einschaltest.

## Schnellstart

1. **Solarbank vorbereiten.** Installiere eine Anker-Solix-Integration, die die
   *Third-Party-Control*-Entitäten der Solarbank 4 bereitstellt (z. B.
   `anker_solix_official`), und stelle die Solarbank dort auf **Third-Party
   Control**. Du brauchst zwei Stellglieder: ein Flussrichtungs-**Select**
   (Laden / Entladen) und eine **Number** für die Soll-Netzleistung (W).
2. **Installieren** über HACS:
   [![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Jo-Highness&repository=balcony_battery_manager&category=integration)
   → **Balcony Battery Manager** installieren → Home Assistant neu starten.
3. **Integration hinzufügen** (Einstellungen → Geräte & Dienste → Integration
   hinzufügen → *Balcony Battery Manager*) und **5 Sensoren** (Hauptakku-Leistung,
   Netzleistung, Solarbank-Ausgang, Solarbank-SoC, Solarbank-PV-Leistung) sowie
   die **2 Stellglieder** wählen. Eindeutige Solarbank-Entitäten sind vorbelegt.
4. **Vorzeichen prüfen** unter *Entwicklerwerkzeuge → Zustände*: Zieht das Haus
   aus dem Hauptakku, muss *Korrigierter Bedarf* **positiv** sein; bei
   Einspeisung muss *Überschuss* **positiv** sein. Sonst den passenden
   Schalter *Positiv = …* in den Optionen umstellen.
5. **Beobachten:** Der Sensor **Modus** zeigt `idle`, `discharge`, `charge`,
   `grid_support`, `failsafe` oder `disabled` (in der Oberfläche übersetzt),
   das Attribut `reason` nennt den Grund. Die [Dashboard-Karte](#dashboard)
   unten hilft dabei.

---

## Inhalt

- [Sicherheit](#sicherheit)
- [Funktionsweise](#funktionsweise)
- [Konfiguration](#konfiguration)
- [Entitäten](#entitäten)
- [Aktionen](#aktionen)
- [Dashboard](#dashboard)
- [Automationsbeispiele](#automationsbeispiele)
- [Fehlersuche / FAQ](#fehlersuche--faq)
- [Upgrade-Hinweise](#upgrade-hinweise)
- [Anforderungsdokument](docs/requirements.md) · [Changelog](CHANGELOG.md)

## Sicherheit

- **Steuerung an die Anker-App zurückgeben.** Schalter **Aktiviert** aus (oder
  Aktion `balcony_battery_manager.disable`). Der Regler setzt die Sollleistung
  auf **0 W**. Flussrichtungs-Select und Betriebsmodus der Solarbank bleiben
  unverändert – außer du konfigurierst das optionale **Betriebsmodus-Select**
  mit einem **Modus beim Deaktivieren** (z. B. den eigenen Modus der Anker-App);
  dann wird dieser automatisch wiederhergestellt. Ohne diese Einstellung stellst
  du die Solarbank selbst in der Anker-App/-Integration zurück.
- **Entfernen / Neuladen** der Integration hinterlässt die Solarbank ebenfalls
  bei 0 W.
- **Minimaler SoC.** Bei oder unter *Minimaler Solarbank-SoC* (Standard 10 %)
  läuft keine Entladung (weder Stufen noch Netz-Unterstützung). Die eigenen
  Grenzen der Solarbank gelten zusätzlich.
- **Kein Laden aus dem Netz.** Das Laden ist ein Regelkreis auf die *gemessene
  Einspeisung*: Es nimmt nur Einspeisung oberhalb der *Einspeise-Reserve* auf
  und zieht nie absichtlich aus Netz oder Hauptakku. Kurze Überschwinger nach
  plötzlichen Laständerungen werden im nächsten Zyklus korrigiert.
- **800 W Einspeisung.** Bei der Solarbank 4 ist die Third-Party-Soll-
  Netzleistung zum Entladen auf etwa **800 W** begrenzt (Geräte-/Firmware-Grenze
  und die übliche Grenze für Balkonkraftwerke in Deutschland). Alle Sollwerte
  werden ohnehin auf Min/Max der Number-Entität begrenzt.
- **Fail-safe.** Ist ein Pflichtsensor nicht verfügbar oder liefert er eine
  nicht unterstützte Einheit, oder schlägt ein Schreibvorgang fehl bzw. läuft
  in ein Timeout, schreibt der Regler **0 W**.
- **Richtungswechsel** laufen immer *Leistung 0 W → Richtung umschalten → neuer
  Sollwert*.
- **Ein Regler pro Solarbank.** Ein zweiter Eintrag für dieselben Stellglieder
  wird abgelehnt.

## Funktionsweise

In jedem Zyklus (Standard: alle 30 s) liest der Regler die Sensoren, entscheidet
**genau einen** Modus und schreibt den Sollwert:

| Modus | Wann | Sollwert |
|---|---|---|
| `grid_support` | Hauptakku-SoC bei/unter *leer* (optionaler Sensor gesetzt) und Solarbank über ihrem Minimal-SoC | Deckt Hauptakku-Entladung + Netzbezug bis auf einen kleinen *Rest-Netzbezug*, bis zur *max. Einspeisung* |
| `discharge` | *Korrigierter Bedarf* liegt die volle *Verweilzeit* über Schwelle 1 / 2 | Einspeisung Stufe 1 / 2 |
| `charge` | Rest-PV bis Sonnenuntergang reicht nicht für den *Ziel-SoC* und es wird eingespeist | Regelkreis: Einspeisung oberhalb der *Reserve* |
| `idle` | Nichts zu tun | 0 W |
| `failsafe` | Pflichtsensor fehlt/ungültig | 0 W |
| `disabled` | Hauptschalter aus | 0 W |

**Korrigierter Bedarf** = Hauptakku-Entladung + aktueller Solarbank-Ausgang. Der
Zähler des Hauptakkus sieht nur, was die Solarbank *nicht* deckt; addiert man den
Solarbank-Ausgang wieder hinzu, erhält man den echten Bedarf – unabhängig vom
eigenen Sollwert.

**Rest-PV** wird aus der aktuellen Solarbank-PV-Leistung geschätzt, gekappt auf
die PV-Nennleistung und ab der *Nachmittagsgrenze* auf Nennleistung ×
*Nachmittagsfaktor*, aufsummiert bis zum nächsten Sonnenuntergang. Dieser kommt
aus `sun.sun`; ohne die Entität wird er aus dem Home-Assistant-Standort berechnet
(notfalls 21:00 Ortszeit).

## Konfiguration

Alles wird in der Oberfläche eingestellt und lässt sich später über
**Konfigurieren** ändern (der Eintrag lädt neu). Das Formular ist in Abschnitte
gegliedert; jedes Feld hat einen Hilfetext. Mit *Beispiel* markierte Zahlen
stammen aus einem Setup mit mehreren Akkus – passe sie an deins an.

**Messwerte** – Leistungssensoren dürfen W, kW oder MW liefern; SoC muss in % sein.

| Feld | Pflicht | Hinweis |
|---|---|---|
| Hauptakku-Leistung | ja | Vorzeichen-Schalter *Positiv = Entladung ins Haus* (aus z. B. bei E3DC, das Entladung negativ meldet). |
| Netzleistung | ja | Vorzeichen-Schalter *Positiv = Einspeisung ins Netz*. |
| Solarbank-Ausgang ins Haus | ja | AC-Ausgang der Solarbank. |
| Solarbank-Ladezustand | ja | % |
| Solarbank-PV-Leistung | ja | |
| Sonnen-Entität | nein | Standard `sun.sun`. |

**Solarbank-Stellglieder**

| Feld | Pflicht | Hinweis |
|---|---|---|
| Flussrichtung (Select) | ja | |
| Option für „Entladen“ / „Laden“ | ja | Exakte Optionswerte dieses Selects (wird geprüft). |
| Sollwert Netzleistung (Number) | ja | W oder kW; Werte werden auf Min/Max begrenzt. |
| Betriebsmodus-Select | nein | Nur nötig, um Modi automatisch umzuschalten. |
| Modus während der Regelung | nein | Wird gesetzt, bevor Leistung vorgegeben wird (z. B. Third-Party Control). |
| Modus beim Deaktivieren | nein | Wird beim Deaktivieren wiederhergestellt. |

**Entlade-Stufen**: Schwelle 1 / 2 (800 / 1600 W, Schwelle 1 muss kleiner sein),
Einspeisung Stufe 1 / 2 (350 / 800 W), Verweilzeit (10 min), Hysterese (100 W),
minimaler Solarbank-SoC (10 %).

**Vorausschauendes PV-Laden**: maximale Ladeleistung (2500 W, *Beispiel*;
zusätzlich auf das Maximum der Number begrenzt), Einspeise-Reserve (100 W),
Ziel-SoC (100 %), nutzbare Kapazität (15,5 kWh, *Beispiel* – trage deine
Solarbank inkl. Erweiterungsakkus ein), PV-Nennleistung (2000 W),
Nachmittagsgrenze (13 Uhr), Nachmittagsfaktor (0,33).

**Netz-Unterstützung**: an/aus (an), Hauptakku-SoC-Sensor (optional – leer
schaltet die Netz-Unterstützung ab), leer bei (10 %), Freigabe-Hysterese (3 %),
Rest-Netzbezug (100 W), maximale Einspeisung (800 W).

**Allgemein**: Regelintervall (30 s, 5–600 s), Totband (25 W – kleinere
Sollwertänderungen werden nicht geschrieben).

## Entitäten

Ein Dienst-Gerät **Balcony Battery Manager** mit:

| Entität | Beispiel-Entity-ID | Details |
|---|---|---|
| Modus | `sensor.balcony_battery_manager_mode` | Enum: `idle`, `discharge`, `charge`, `grid_support`, `failsafe`, `disabled`. Attribute: `grid_flow`, `applied_power`, `charge_release`, `need_wh`, `rest_pv_wh`, `reason`. |
| Sollleistung | `sensor.balcony_battery_manager_target_power` | Entschiedener Sollwert in W. |
| Korrigierter Bedarf | `sensor.balcony_battery_manager_corrected_demand` | W |
| Überschuss | `sensor.balcony_battery_manager_surplus` | Aktuelle Einspeisung in W (negativ = Netzbezug; 0 im Fail-safe). |
| Aktiviert | `switch.balcony_battery_manager_enabled` | Hauptschalter; der Zustand übersteht Neustarts. |

Die Entity-IDs entstehen aus dem englischen Gerätenamen; bei deutscher
Oberfläche können sie abweichen – prüfe sie unter *Einstellungen → Entitäten*.
Diagnosedaten lassen sich auf der Integrationsseite herunterladen.

## Aktionen

| Aktion | Beschreibung |
|---|---|
| `balcony_battery_manager.enable` | Regelung aktivieren und sofort einen Zyklus ausführen. |
| `balcony_battery_manager.disable` | Regelung deaktivieren: 0 W und, falls eingestellt, Anker-Betriebsmodus wiederherstellen. |
| `balcony_battery_manager.recalculate_now` | Sofort einen Zyklus ausführen. |

Alle akzeptieren optional `config_entry_id`; ohne gilt die Aktion für alle Einträge.

## Dashboard

```yaml
type: entities
title: Balkonakku
entities:
  - entity: switch.balcony_battery_manager_enabled
  - entity: sensor.balcony_battery_manager_mode
  - type: attribute
    entity: sensor.balcony_battery_manager_mode
    attribute: reason
    name: Grund
  - entity: sensor.balcony_battery_manager_target_power
  - entity: sensor.balcony_battery_manager_corrected_demand
  - entity: sensor.balcony_battery_manager_surplus
```

## Automationsbeispiele

Benachrichtigung, wenn der Regler in den Fail-safe geht:

```yaml
alias: Balkonakku – Fail-safe melden
triggers:
  - trigger: state
    entity_id: sensor.balcony_battery_manager_mode
    to: "failsafe"
    for: "00:02:00"
actions:
  - action: persistent_notification.create
    data:
      title: Balcony Battery Manager
      message: >-
        Fail-safe: {{ state_attr('sensor.balcony_battery_manager_mode', 'reason') }}.
        Die Solarbank wurde auf 0 W gesetzt.
mode: single
```

Steuerung an die Anker-App abgeben, solange ein Helfer an ist (z. B. bei
Wartung), und danach zurückholen:

```yaml
alias: Balkonakku – Handbetrieb
triggers:
  - trigger: state
    entity_id: input_boolean.solarbank_manual
actions:
  - if:
      - condition: state
        entity_id: input_boolean.solarbank_manual
        state: "on"
    then:
      - action: balcony_battery_manager.disable
    else:
      - action: balcony_battery_manager.enable
mode: queued
```

> Den Regler nicht „nachts ausschalten“: Gerade dann ist die Netz-Unterstützung
> bei leerem Hauptakku am nützlichsten.

## Fehlersuche / FAQ

**Die Solarbank speist bei hoher Last nie ein.** Vorzeichen-Schalter prüfen
(Schnellstart Schritt 4) und ob die Solarbank über dem Minimal-SoC liegt.

**Modus bleibt `failsafe`.** Einer der fünf Pflichtsensoren ist nicht verfügbar
oder nutzt eine nicht unterstützte Einheit; das Log nennt ihn.

**Netz-Unterstützung startet nie.** Sie braucht den optionalen
Hauptakku-SoC-Sensor, *Netz-Unterstützung* an, Hauptakku-SoC bei/unter *leer
bei* und eine Solarbank über ihrem Minimal-SoC.

**Sollwerte werden ignoriert.** Die Solarbank muss in *Third-Party Control* sein
(optional über das Betriebsmodus-Select erzwingen).

**Debug-Logging**

```yaml
logger:
  logs:
    custom_components.balcony_battery_manager: debug
```

## Upgrade-Hinweise

- **2.2.0** benötigt Home Assistant **2025.2** oder neuer. Bestehende Einträge
  werden automatisch migriert (Einstellungen wandern in die Optionen). Der
  Schalter *Aktiviert* ist keine Konfigurations-Entität mehr. Leistungssensoren
  in kW werden jetzt korrekt gelesen – falls du das alte Verhalten ausgeglichen
  hast, nimm das zurück.
- **2.0.0** war eine Neuentwicklung für die Solarbank **4**; Einträge für die
  Solarbank 3 (v1) lassen sich nicht migrieren – Integration entfernen und neu
  hinzufügen.

## Screenshots

> Aus einer Demo-Installation mit fiktiven Daten (Version 2.1).

| Einrichtung | Entitäten | Dashboard | Integrationen |
|---|---|---|---|
| ![Einrichtungsformular](images/config-flow.png) | ![Gerät und Entitäten](images/entities.png) | ![Dashboard-Karte](images/dashboard.png) | ![Integrationsübersicht](images/integrations-overview.png) |

## Mitwirken · Lizenz · Dank

Issues und Pull Requests sind willkommen – siehe [CONTRIBUTING.md](CONTRIBUTING.md).
Veröffentlicht unter der [MIT-Lizenz](LICENSE). Dank an die Anker-Solix-Community
für die Third-Party-Control-Entitäten und an das
[Home-Assistant](https://www.home-assistant.io)-Projekt.
