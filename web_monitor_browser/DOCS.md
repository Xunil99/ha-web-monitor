# Web Monitor Browser Add-on

This add-on provides a headless Chromium browser service for the Web Monitor integration.

It runs Playwright inside a Docker container and exposes a REST API on port 8099
that the Web Monitor custom integration uses to browse pages, record steps,
pick elements, and perform periodic scraping.

## Configuration

No configuration needed. Install and start the add-on, then configure monitors
via the Web Monitor integration.
