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
    this._msgId = 1;
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadMonitors();
  }

  _loadMonitors() {
    if (!this.hass) return;
    const entries = Object.values(this.hass.config_entries || {})
      .filter(e => e.domain === "web_monitor");
    this._monitors = entries;
    if (entries.length > 0 && !this._selectedMonitor) {
      this._selectedMonitor = entries[0].entry_id;
    }
  }

  async _wsCall(type, data = {}) {
    return this.hass.callWS({ type, ...data });
  }

  async _startSession() {
    this._loading = true;
    try {
      await this._wsCall("web_monitor/start_session", { url: this._url || "about:blank" });
      this._sessionActive = true;
      if (this._url) {
        const res = await this._wsCall("web_monitor/screenshot");
        this._image = "data:image/png;base64," + res.image;
      }
    } catch (e) {
      console.error("Start session failed:", e);
    }
    this._loading = false;
  }

  async _navigate() {
    if (!this._url) return;
    this._loading = true;
    try {
      const res = await this._wsCall("web_monitor/navigate", { url: this._url });
      this._image = "data:image/png;base64," + res.image;
      this._updateSteps();
    } catch (e) {
      console.error("Navigate failed:", e);
    }
    this._loading = false;
  }

  async _handleImageClick(e) {
    if (!this._sessionActive) return;
    const rect = e.target.getBoundingClientRect();
    const scaleX = 1280 / rect.width;
    const scaleY = 720 / rect.height;
    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    this._loading = true;
    try {
      if (this._pickerActive) {
        await this._wsCall("web_monitor/click", { x, y });
        const pr = await this._wsCall("web_monitor/get_picker_result");
        if (pr.result) {
          this._pickerResult = pr.result;
          this._pickerActive = false;
        }
        const res = await this._wsCall("web_monitor/screenshot");
        this._image = "data:image/png;base64," + res.image;
      } else {
        const res = await this._wsCall("web_monitor/click", { x, y });
        this._image = "data:image/png;base64," + res.image;
        this._updateSteps();
      }
    } catch (e) {
      console.error("Click failed:", e);
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

  async _saveMonitor() {
    if (!this._selectedMonitor || !this._pickerResult) return;
    this._loading = true;
    try {
      const data = {
        entry_id: this._selectedMonitor,
        target_selector: this._pickerResult.selector,
        target_extract: this._extractType,
      };
      if (this._extractType === "attribute" && this._extractAttribute) {
        data.target_attribute = this._extractAttribute;
      }
      await this._wsCall("web_monitor/save_monitor", data);
      alert("Monitor gespeichert! Der Scraper beginnt mit dem naechsten Intervall.");
    } catch (e) {
      console.error("Save failed:", e);
      alert("Fehler beim Speichern: " + e.message);
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
    return html`
      <div class="container">
        <h1>Web Monitor</h1>

        <div class="toolbar">
          <select @change=${e => this._selectedMonitor = e.target.value}>
            ${this._monitors.map(m => html`
              <option value=${m.entry_id} ?selected=${m.entry_id === this._selectedMonitor}>
                ${m.title}
              </option>
            `)}
          </select>

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

        ${this._image ? html`
          <div class="browser-view">
            <img src=${this._image}
              @click=${this._handleImageClick}
              style="cursor: ${this._pickerActive ? 'crosshair' : 'pointer'}"
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
              <select @change=${e => this._extractType = e.target.value}>
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

            <button @click=${this._saveMonitor} class="save" ?disabled=${this._loading}>
              Monitor speichern
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
      .picker-result {
        background: var(--card-background-color);
        border: 1px solid var(--divider-color);
        border-radius: 8px; padding: 16px; margin-top: 16px;
      }
      .picker-result code {
        background: var(--secondary-background-color);
        padding: 2px 6px; border-radius: 3px; font-size: 13px;
      }
      .extract-options {
        display: flex; gap: 8px; align-items: center;
        margin-top: 8px;
      }
      .extract-options select, .extract-options input {
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
