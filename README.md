# Web Monitor for Home Assistant

Browse to any web page, visually select an element, and monitor its value on a schedule.

## Features

- Visual element picker - browse and click to select what to monitor
- JavaScript-rendered pages supported (Playwright/Chromium)
- Login-protected pages - record click sequences including authentication
- Change history with SQLite storage
- Optional screenshot capture
- Session persistence between scraping runs

## Installation via HACS

1. In HACS auf die drei Punkte oben rechts klicken > "Benutzerdefinierte Repositories"
2. URL `https://github.com/Xunil99/ha-web-monitor` eingeben, Kategorie "Integration"
3. "Web Monitor" suchen und installieren
4. Home Assistant neu starten
5. Settings > Devices & Services > Add Integration > "Web Monitor"

## Installation (manuell)

1. `custom_components/web_monitor/` in dein HA `config/custom_components/` Verzeichnis kopieren
   (z.B. via Samba-Share, SSH Add-on, oder File Editor Add-on)
2. Home Assistant neu starten
3. Settings > Devices & Services > Add Integration > "Web Monitor"

Python-Pakete (`playwright`, `aiosqlite`) und der Chromium-Browser werden beim ersten Start **automatisch** installiert. Der erste Start kann 1-2 Minuten dauern (~150MB Chromium-Download).

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

## Requirements

- Home Assistant OS 2024.1+ (oder Docker/Core)
- ~200-400 MB RAM for Chromium during scraping
- ~150 MB Festplattenspeicher fuer Chromium (wird automatisch installiert)
