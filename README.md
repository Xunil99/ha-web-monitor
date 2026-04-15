# Web Monitor for Home Assistant

Browse to any web page, visually select an element, and monitor its value on a schedule.

## Features

- Visual element picker - browse and click to select what to monitor
- JavaScript-rendered pages supported (Playwright/Chromium)
- Login-protected pages - record click sequences including authentication
- Change history with SQLite storage
- Optional screenshot capture
- Session persistence between scraping runs

## Installation

Die Integration besteht aus zwei Teilen: einem **Add-on** (Browser-Service) und einer **Custom Integration**.

### Schritt 1: Add-on installieren

1. In HA: Settings > Add-ons > Add-on Store > drei Punkte > Repositories
2. Repository-URL eingeben: `https://github.com/Xunil99/ha-web-monitor`
3. "Web Monitor Browser" Add-on installieren und starten
4. Das Add-on stellt einen headless Chromium-Browser auf Port 8099 bereit

### Schritt 2: Integration installieren (HACS)

1. In HACS > drei Punkte > "Benutzerdefinierte Repositories"
2. URL `https://github.com/Xunil99/ha-web-monitor` eingeben, Kategorie "Integration"
3. "Web Monitor" suchen und installieren
4. Home Assistant neu starten
5. Settings > Devices & Services > Add Integration > "Web Monitor"

### Schritt 2 alternativ: Manuelle Installation

1. `custom_components/web_monitor/` in dein HA `config/custom_components/` kopieren
2. Home Assistant neu starten
3. Settings > Devices & Services > Add Integration > "Web Monitor"

## Usage

1. Add a new monitor via the config flow (name, interval, etc.)
2. Open the "Web Monitor" panel in the HA sidebar
3. Enter a URL and start a browser session
4. Navigate to the page you want to monitor (login if needed - steps are recorded)
5. Click "Element auswaehlen" and click on the value you want to track
6. Click "Monitor speichern"
7. The integration will now scrape that value at your configured interval

## Services

| Service | Description |
|---------|-------------|
| `web_monitor.refresh` | Force immediate scrape |
| `web_monitor.get_history` | Get change history (returns JSON) |
| `web_monitor.clear_history` | Delete history |

## Architektur

```
HA Add-on (Docker)              Custom Integration
┌─────────────────────┐         ┌──────────────────┐
│ Playwright+Chromium  │◄─HTTP──│ Sensor, Panel,   │
│ FastAPI auf :8099    │        │ Config Flow      │
└─────────────────────┘         └──────────────────┘
```

Das Add-on laeuft als Docker-Container und stellt Playwright/Chromium bereit.
Die Integration kommuniziert per HTTP mit dem Add-on.

## Requirements

- Home Assistant OS 2024.1+ (oder Docker/Core)
- Web Monitor Browser Add-on (wird mitgeliefert)
- ~200-400 MB RAM fuer Chromium im Add-on Container
