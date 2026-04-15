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

1. Copy `custom_components/web_monitor/` to your HA `config/custom_components/` directory
2. Install Playwright's Chromium browser:
   ```bash
   pip install playwright==1.49.1 aiosqlite==0.20.0
   playwright install chromium --with-deps
   ```
3. Restart Home Assistant
4. Go to Settings > Devices & Services > Add Integration > "Web Monitor"

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

- Home Assistant 2024.1+
- ~200-400 MB RAM for Chromium during scraping
- Playwright + Chromium installed on the HA host
