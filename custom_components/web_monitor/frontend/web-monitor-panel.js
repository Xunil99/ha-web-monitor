import { LitElement, html, css } from "https://unpkg.com/lit-element@3.3.3/lit-element.js?module";

class WebMonitorPanel extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      narrow: { type: Boolean },
      _image: { type: String },
      _url: { type: String },
      _loading: { type: Boolean },
      _pickerActive: { type: Boolean },
      _pickerResult: { type: Object },
      _steps: { type: Array },
      _monitors: { type: Array },
      _selectedMonitor: { type: String },
      _sessionActive: { type: Boolean },
      _extractType: { type: String },
      _extractAttribute: { type: String },
      _error: { type: String },
      _success: { type: String },
      _filterMode: { type: String },
      _filterPattern: { type: String },
      _filterEndPattern: { type: String },
      _filterPreview: { type: String },
      _lastClicked: { type: Object },
      _typeText: { type: String },
    };
  }

  constructor() {
    super();
    this._image = "";
    this._url = "";
    this._loading = false;
    this._pickerActive = false;
    this._pickerResult = null;
    this._steps = [];
    this._monitors = [];
    this._selectedMonitor = "";
    this._sessionActive = false;
    this._extractType = "text_content";
    this._extractAttribute = "";
    this._error = "";
    this._success = "";
    this._filterMode = "none";
    this._filterPattern = "";
    this._filterEndPattern = "";
    this._filterPreview = "";
    this._lastClicked = null;
    this._typeText = "";
    this._msgId = 1;
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadMonitors();
  }

  updated(changedProps) {
    // When hass becomes available (panel mount), load monitors
    if (changedProps.has("hass") && this.hass && this._monitors.length === 0) {
      this._loadMonitors();
    }
  }

  async _loadMonitors() {
    if (!this.hass) return;
    try {
      const entries = await this.hass.callWS({
        type: "config_entries/get",
        domain: "web_monitor",
      });
      this._monitors = entries || [];
      if (this._monitors.length > 0 && !this._selectedMonitor) {
        this._selectedMonitor = this._monitors[0].entry_id;
      }
    } catch (err) {
      console.error("Failed to load monitors:", err);
      // Fallback: try the cached hass.config_entries
      const entries = Object.values(this.hass.config_entries || {})
        .filter(e => e.domain === "web_monitor");
      this._monitors = entries;
      if (entries.length > 0 && !this._selectedMonitor) {
        this._selectedMonitor = entries[0].entry_id;
      }
    }
  }

  async _wsCall(type, data = {}) {
    return this.hass.callWS({ type, ...data });
  }

  _normalizeUrl(url) {
    if (!url) return url;
    if (/^(https?|file|about):/.test(url)) return url;
    return "https://" + url;
  }

  async _startSession() {
    this._loading = true;
    this._error = "";
    this._url = this._normalizeUrl(this._url);
    try {
      await this._wsCall("web_monitor/start_session", { url: this._url || "about:blank" });
      this._sessionActive = true;
      if (this._url) {
        const res = await this._wsCall("web_monitor/screenshot");
        this._image = "data:image/png;base64," + res.image;
      }
    } catch (e) {
      console.error("Start session failed:", e);
      this._error = "Session konnte nicht gestartet werden: " + (e.message || JSON.stringify(e));
    }
    this._loading = false;
  }

  async _navigate() {
    if (!this._url) return;
    this._loading = true;
    this._error = "";
    this._url = this._normalizeUrl(this._url);
    try {
      const res = await this._wsCall("web_monitor/navigate", { url: this._url });
      this._image = "data:image/png;base64," + res.image;
      this._updateSteps();
    } catch (e) {
      console.error("Navigate failed:", e);
      this._error = "Navigation fehlgeschlagen: " + (e.message || JSON.stringify(e));
    }
    this._loading = false;
  }

  async _handleImageClick(e) {
    if (!this._sessionActive) return;
    e.preventDefault();
    const rect = e.target.getBoundingClientRect();
    const scaleX = 1280 / rect.width;
    const scaleY = 720 / rect.height;
    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    this._loading = true;
    this._error = "";
    try {
      if (this._pickerActive) {
        // In picker mode: query element info without clicking
        const pr = await this._wsCall("web_monitor/pick", { x, y });
        if (pr.result) {
          this._pickerResult = pr.result;
          this._pickerActive = false;
          // Reset filter on new selection, set preview to full text
          this._filterMode = "none";
          this._filterPattern = "";
          this._filterEndPattern = "";
          this._filterPreview = pr.result.text || "";
        } else {
          this._error = "Kein Element an dieser Position gefunden.";
        }
      } else {
        // Normal mode: actually click and record the step
        const res = await this._wsCall("web_monitor/click", { x, y });
        this._image = "data:image/png;base64," + res.image;
        if (res.element && res.element.selector) {
          this._lastClicked = res.element;
        }
        this._updateSteps();
      }
    } catch (err) {
      console.error("Click failed:", err);
      this._error = "Klick fehlgeschlagen: " + (err.message || JSON.stringify(err));
    }
    this._loading = false;
  }

  async _handleWheel(e) {
    if (!this._sessionActive) return;
    e.preventDefault();
    // Throttle: only send if not already scrolling
    if (this._scrollPending) return;
    this._scrollPending = true;
    try {
      const res = await this._wsCall("web_monitor/scroll", { delta_y: Math.round(e.deltaY) });
      this._image = "data:image/png;base64," + res.image;
    } catch (err) {
      console.error("Scroll failed:", err);
    } finally {
      this._scrollPending = false;
    }
  }

  async _scrollBy(deltaY) {
    if (!this._sessionActive) return;
    this._loading = true;
    try {
      const res = await this._wsCall("web_monitor/scroll", { delta_y: deltaY });
      this._image = "data:image/png;base64," + res.image;
    } catch (err) {
      console.error("Scroll failed:", err);
      this._error = "Scroll fehlgeschlagen: " + err.message;
    }
    this._loading = false;
  }

  async _sendText() {
    if (!this._typeText) return;
    if (!this._lastClicked || !this._lastClicked.selector) {
      this._error = "Bitte zuerst auf das Eingabefeld klicken, in das der Text eingegeben werden soll.";
      return;
    }
    this._loading = true;
    this._error = "";
    try {
      const res = await this._wsCall("web_monitor/fill", {
        selector: this._lastClicked.selector,
        value: this._typeText,
      });
      this._image = "data:image/png;base64," + res.image;
      this._updateSteps();
      this._typeText = "";
    } catch (err) {
      console.error("Fill failed:", err);
      this._error = "Texteingabe fehlgeschlagen: " + (err.message || JSON.stringify(err));
    }
    this._loading = false;
  }

  async _pressKey(key) {
    if (!this._sessionActive) return;
    this._loading = true;
    try {
      const res = await this._wsCall("web_monitor/key", { key });
      this._image = "data:image/png;base64," + res.image;
    } catch (err) {
      console.error("Key press failed:", err);
    }
    this._loading = false;
  }

  async _activatePicker() {
    try {
      await this._wsCall("web_monitor/activate_picker");
      this._pickerActive = true;
      this._pickerResult = null;
    } catch (e) {
      console.error("Picker activation failed:", e);
    }
  }

  async _updateSteps() {
    try {
      const res = await this._wsCall("web_monitor/get_steps");
      this._steps = res.steps || [];
    } catch (e) {
      console.error("Get steps failed:", e);
    }
  }

  async _updateFilterPreview() {
    if (!this._pickerResult) {
      this._filterPreview = "";
      return;
    }
    if (this._filterMode === "none" || !this._filterPattern) {
      this._filterPreview = this._pickerResult.text || "";
      return;
    }
    try {
      const res = await this._wsCall("web_monitor/filter_test", {
        text: this._pickerResult.text || "",
        mode: this._filterMode,
        pattern: this._filterPattern,
        end_pattern: this._filterEndPattern,
      });
      this._filterPreview = res.result ?? "";
    } catch (err) {
      console.error("Filter test failed:", err);
      this._filterPreview = "(Fehler in Filter)";
    }
  }

  _onFilterChange() {
    // Schedule preview update with small debounce
    if (this._filterDebounce) clearTimeout(this._filterDebounce);
    this._filterDebounce = setTimeout(() => this._updateFilterPreview(), 250);
  }

  async _saveMonitor() {
    if (!this._selectedMonitor) {
      this._error = "Bitte zuerst einen Monitor oben auswaehlen.";
      return;
    }
    if (!this._pickerResult) {
      this._error = "Bitte zuerst ein Element auswaehlen.";
      return;
    }
    this._loading = true;
    this._error = "";
    this._success = "";
    try {
      const data = {
        entry_id: this._selectedMonitor,
        target_selector: this._pickerResult.selector,
        target_extract: this._extractType,
        filter_mode: this._filterMode,
        filter_pattern: this._filterPattern,
        filter_end_pattern: this._filterEndPattern,
      };
      if (this._extractType === "attribute" && this._extractAttribute) {
        data.target_attribute = this._extractAttribute;
      }
      const result = await this._wsCall("web_monitor/save_monitor", data);
      const monitorName = this._monitors.find(m => m.entry_id === this._selectedMonitor)?.title || this._selectedMonitor;
      this._success = `Monitor "${monitorName}" gespeichert (${result.steps_count || 0} Schritte). Der Scraper laeuft mit dem naechsten Intervall.`;
    } catch (e) {
      console.error("Save failed:", e);
      this._error = "Fehler beim Speichern: " + (e.message || JSON.stringify(e));
    }
    this._loading = false;
  }

  async _closeSession() {
    try {
      await this._wsCall("web_monitor/close_session");
    } catch (e) { /* ignore */ }
    this._sessionActive = false;
    this._image = "";
    this._steps = [];
    this._pickerResult = null;
  }

  render() {
    const activeMonitor = this._monitors.find(m => m.entry_id === this._selectedMonitor);
    return html`
      <div class="container">
        <h1>Web Monitor</h1>

        <div class="monitor-bar">
          <label>Bearbeite Monitor:</label>
          <select @change=${e => this._selectedMonitor = e.target.value}>
            ${this._monitors.length === 0 ? html`<option>(noch keiner angelegt)</option>` : ""}
            ${this._monitors.map(m => html`
              <option value=${m.entry_id} ?selected=${m.entry_id === this._selectedMonitor}>
                ${m.title}
              </option>
            `)}
          </select>
          ${activeMonitor ? html`<span class="active-monitor">→ <strong>${activeMonitor.title}</strong> (sensor.${(activeMonitor.title || "").toLowerCase().replace(/[^a-z0-9]/g, "_")})</span>` : ""}
          <button class="reload-btn" @click=${this._loadMonitors} title="Monitor-Liste neu laden">↻</button>
        </div>

        <div class="toolbar">
          ${!this._sessionActive ? html`
            <input type="text" placeholder="URL eingeben..."
              .value=${this._url}
              @input=${e => this._url = e.target.value}
              @keydown=${e => e.key === "Enter" && this._startSession()}
            />
            <button @click=${this._startSession} ?disabled=${this._loading}>
              Session starten
            </button>
          ` : html`
            <input type="text" placeholder="URL..."
              .value=${this._url}
              @input=${e => this._url = e.target.value}
              @keydown=${e => e.key === "Enter" && this._navigate()}
            />
            <button @click=${this._navigate} ?disabled=${this._loading}>Navigieren</button>
            <button @click=${this._activatePicker}
              class=${this._pickerActive ? "active" : ""}
              ?disabled=${this._loading}>
              Element auswaehlen
            </button>
            <button @click=${this._closeSession} class="danger">Session beenden</button>
          `}
        </div>

        ${this._loading ? html`<div class="loading">Laden...</div>` : ""}

        ${this._error ? html`<div class="error">${this._error}</div>` : ""}
        ${this._success ? html`<div class="success">${this._success}</div>` : ""}

        ${this._image ? html`
          <div class="scroll-controls">
            <button @click=${() => this._scrollBy(-720)} title="Eine Seite hoch">↑↑</button>
            <button @click=${() => this._scrollBy(-200)} title="Hoch">↑</button>
            <button @click=${() => this._scrollBy(200)} title="Runter">↓</button>
            <button @click=${() => this._scrollBy(720)} title="Eine Seite runter">↓↓</button>
            <button @click=${() => this._pressKey('PageUp')} title="Page Up">PgUp</button>
            <button @click=${() => this._pressKey('PageDown')} title="Page Down">PgDn</button>
            <button @click=${() => this._pressKey('Home')} title="Anfang">⇱</button>
            <button @click=${() => this._pressKey('End')} title="Ende">⇲</button>
            <button @click=${() => this._pressKey('Enter')} title="Enter">↵ Enter</button>
            <button @click=${() => this._pressKey('Tab')} title="Tab">⇥ Tab</button>
            <span class="hint">Tipp: Mausrad ueber dem Bild scrollt auch</span>
          </div>
          <div class="type-controls">
            <label>Texteingabe:</label>
            <input type="text"
              placeholder=${this._lastClicked ? "Text eingeben und Enter druecken" : "Erst auf ein Eingabefeld klicken"}
              ?disabled=${!this._lastClicked || this._loading}
              .value=${this._typeText}
              @input=${e => this._typeText = e.target.value}
              @keydown=${e => { if (e.key === 'Enter') { e.preventDefault(); this._sendText(); } }}
            />
            <button @click=${this._sendText} ?disabled=${!this._lastClicked || !this._typeText || this._loading}>
              Senden
            </button>
            ${this._lastClicked ? html`<span class="last-clicked">→ <code>${this._lastClicked.selector}</code></span>` : ""}
          </div>
          <div class="browser-view">
            <img src=${this._image}
              draggable="false"
              @dragstart=${(e) => e.preventDefault()}
              @click=${this._handleImageClick}
              @wheel=${this._handleWheel}
              style="cursor: ${this._pickerActive ? 'crosshair' : 'pointer'}; user-select: none; -webkit-user-drag: none;"
            />
          </div>
        ` : html`
          <div class="placeholder">
            Session starten um eine Webseite zu laden
          </div>
        `}

        ${this._pickerResult ? html`
          <div class="picker-result">
            <h3>Ausgewaehltes Element</h3>
            <p><strong>Selektor:</strong> <code>${this._pickerResult.selector}</code></p>
            <p><strong>Text:</strong> ${this._pickerResult.text || "(leer)"}</p>
            <p><strong>Tag:</strong> &lt;${this._pickerResult.tag}&gt;</p>

            <div class="extract-options">
              <label>Extrahieren:</label>
              <select @change=${e => { this._extractType = e.target.value; this._updateFilterPreview(); }}>
                <option value="text_content" selected>Textinhalt</option>
                <option value="inner_html">Inner HTML</option>
                <option value="attribute">Attribut</option>
              </select>
              ${this._extractType === "attribute" ? html`
                <input type="text" placeholder="Attribut-Name (z.B. href)"
                  .value=${this._extractAttribute}
                  @input=${e => this._extractAttribute = e.target.value}
                />
              ` : ""}
            </div>

            <div class="filter-options">
              <label>Textfilter:</label>
              <select @change=${e => { this._filterMode = e.target.value; this._updateFilterPreview(); }}>
                <option value="none" ?selected=${this._filterMode === "none"}>Voller Text</option>
                <option value="regex" ?selected=${this._filterMode === "regex"}>Regex (erste Capture-Gruppe)</option>
                <option value="before" ?selected=${this._filterMode === "before"}>Vor Trennzeichen</option>
                <option value="after" ?selected=${this._filterMode === "after"}>Nach Trennzeichen</option>
                <option value="between" ?selected=${this._filterMode === "between"}>Zwischen zwei Trennzeichen</option>
              </select>
              ${this._filterMode !== "none" ? html`
                <input type="text"
                  placeholder=${this._filterMode === "regex" ? "z.B. (\\d+,\\d+)" : "Trennzeichen"}
                  .value=${this._filterPattern}
                  @input=${e => { this._filterPattern = e.target.value; this._onFilterChange(); }}
                />
              ` : ""}
              ${this._filterMode === "between" ? html`
                <input type="text"
                  placeholder="End-Trennzeichen"
                  .value=${this._filterEndPattern}
                  @input=${e => { this._filterEndPattern = e.target.value; this._onFilterChange(); }}
                />
              ` : ""}
            </div>

            <div class="preview">
              <strong>Sensor-Wert (Vorschau):</strong>
              <code>${this._filterPreview || "(leer)"}</code>
            </div>

            <button @click=${this._saveMonitor} class="save" ?disabled=${this._loading || !this._selectedMonitor}>
              In Monitor "${activeMonitor?.title || "(keiner)"}" speichern
            </button>
          </div>
        ` : ""}

        ${this._steps.length > 0 ? html`
          <div class="steps">
            <h3>Aufgezeichnete Schritte (${this._steps.length})</h3>
            <ol>
              ${this._steps.map(s => html`
                <li>
                  <strong>${s.action}</strong>
                  ${s.url ? html`: <code>${s.url}</code>` : ""}
                  ${s.selector ? html`: <code>${s.selector}</code>` : ""}
                  ${s.value ? html` = "${s.value}"` : ""}
                </li>
              `)}
            </ol>
          </div>
        ` : ""}
      </div>
    `;
  }

  static get styles() {
    return css`
      :host {
        display: block;
        padding: 16px;
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
      }
      .container { max-width: 1400px; margin: 0 auto; }
      h1 { margin: 0 0 16px; font-size: 24px; }
      h3 { margin: 16px 0 8px; font-size: 18px; }
      .toolbar {
        display: flex; gap: 8px; align-items: center;
        flex-wrap: wrap; margin-bottom: 16px;
      }
      .toolbar input[type="text"] {
        flex: 1; min-width: 200px; padding: 8px 12px;
        border: 1px solid var(--divider-color); border-radius: 4px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        font-size: 14px;
      }
      .toolbar select {
        padding: 8px 12px; border: 1px solid var(--divider-color);
        border-radius: 4px; background: var(--card-background-color);
        color: var(--primary-text-color);
      }
      button {
        padding: 8px 16px; border: none; border-radius: 4px;
        background: var(--primary-color); color: white;
        cursor: pointer; font-size: 14px; white-space: nowrap;
      }
      button:hover { opacity: 0.9; }
      button:disabled { opacity: 0.5; cursor: not-allowed; }
      button.active { background: #4285f4; box-shadow: 0 0 0 2px #4285f4; }
      button.danger { background: #d32f2f; }
      button.save { background: #388e3c; margin-top: 8px; }
      .scroll-controls {
        display: flex; gap: 4px; align-items: center;
        flex-wrap: wrap; margin-bottom: 8px;
      }
      .scroll-controls button {
        padding: 4px 12px; font-size: 13px;
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
      }
      .scroll-controls .hint {
        margin-left: 12px; font-size: 12px;
        color: var(--secondary-text-color);
      }
      .type-controls {
        display: flex; gap: 8px; align-items: center;
        flex-wrap: wrap; margin-bottom: 8px;
        padding: 8px; background: var(--secondary-background-color);
        border-radius: 4px;
      }
      .type-controls label { font-weight: 500; min-width: 90px; }
      .type-controls input[type="text"] {
        flex: 1; min-width: 200px; padding: 6px 10px;
        border: 1px solid var(--divider-color); border-radius: 4px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
      }
      .type-controls .last-clicked {
        font-size: 12px; color: var(--secondary-text-color);
        flex-basis: 100%;
      }
      .type-controls .last-clicked code {
        background: transparent; font-size: 11px;
      }
      .browser-view {
        border: 1px solid var(--divider-color); border-radius: 4px;
        overflow: hidden; background: #fff;
      }
      .browser-view img {
        width: 100%; height: auto; display: block;
        image-rendering: auto;
      }
      .placeholder {
        border: 2px dashed var(--divider-color); border-radius: 8px;
        padding: 80px 20px; text-align: center;
        color: var(--secondary-text-color); font-size: 16px;
      }
      .loading {
        text-align: center; padding: 12px;
        color: var(--primary-color); font-weight: bold;
      }
      .error {
        background: #ffebee;
        color: #b71c1c;
        border: 1px solid #ef5350;
        border-radius: 4px;
        padding: 12px;
        margin-bottom: 12px;
        font-size: 14px;
      }
      .success {
        background: #e8f5e9;
        color: #1b5e20;
        border: 1px solid #66bb6a;
        border-radius: 4px;
        padding: 12px;
        margin-bottom: 12px;
        font-size: 14px;
      }
      .monitor-bar {
        display: flex; gap: 8px; align-items: center;
        flex-wrap: wrap; margin-bottom: 12px;
        padding: 12px; background: var(--card-background-color);
        border: 1px solid var(--divider-color); border-radius: 8px;
      }
      .monitor-bar label { font-weight: 500; }
      .monitor-bar select {
        padding: 8px 12px; border: 1px solid var(--divider-color);
        border-radius: 4px; background: var(--card-background-color);
        color: var(--primary-text-color); font-size: 14px;
      }
      .monitor-bar .active-monitor {
        font-size: 13px; color: var(--secondary-text-color);
        margin-left: 8px;
      }
      .monitor-bar .active-monitor strong { color: var(--primary-color); }
      .reload-btn {
        margin-left: auto; padding: 4px 10px;
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        font-size: 16px;
      }
      .picker-result {
        background: var(--card-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px; padding: 16px; margin-top: 16px;
      }
      .picker-result code {
        background: var(--secondary-background-color);
        padding: 2px 6px; border-radius: 3px; font-size: 13px;
      }
      .extract-options, .filter-options {
        display: flex; gap: 8px; align-items: center;
        margin-top: 8px; flex-wrap: wrap;
      }
      .filter-options label, .extract-options label {
        font-weight: 500; min-width: 90px;
      }
      .preview {
        margin-top: 12px; padding: 10px;
        background: var(--secondary-background-color);
        border-left: 3px solid #4caf50;
        border-radius: 4px;
        font-size: 14px;
      }
      .preview code {
        background: transparent;
        padding: 0;
        color: #2e7d32;
        font-weight: bold;
        word-break: break-all;
      }
      .extract-options select, .extract-options input,
      .filter-options select, .filter-options input {
        padding: 6px 10px; border: 1px solid var(--divider-color);
        border-radius: 4px; background: var(--card-background-color);
        color: var(--primary-text-color);
      }
      .steps {
        background: var(--card-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px; padding: 16px; margin-top: 16px;
      }
      .steps ol { margin: 0; padding-left: 24px; }
      .steps li { margin: 4px 0; font-size: 14px; }
      .steps code {
        background: var(--secondary-background-color);
        padding: 1px 4px; border-radius: 3px; font-size: 12px;
      }
    `;
  }
}

customElements.define("web-monitor-panel", WebMonitorPanel);
