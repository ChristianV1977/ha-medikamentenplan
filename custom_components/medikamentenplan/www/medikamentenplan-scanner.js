/* Medikamentenplan: Scanner-Karte. Kamera via getUserMedia, Dekodierung lokal (ZXing, mitgeliefert, kein CDN). */
const BASE = new URL(".", import.meta.url).href;
let zxingPromise;
function loadZXing() {
  if (window.ZXing) return Promise.resolve();
  zxingPromise ||= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = BASE + "zxing-library.min.js?v=0.21.3";
    s.onload = ok; s.onerror = () => fail(new Error("Decoder konnte nicht geladen werden"));
    document.head.appendChild(s);
  });
  return zxingPromise;
}

const CSS = `
:host{display:block}
button{font:inherit;cursor:pointer;border:0;border-radius:12px;padding:14px 16px;background:var(--primary-color);color:var(--text-primary-color,#fff);font-weight:600}
button.sec{background:var(--secondary-background-color);color:var(--primary-text-color)}
button.warn{background:var(--error-color,#c62828)}
.main{width:100%;display:flex;align-items:center;justify-content:center;gap:10px;font-size:1.1em;padding:18px}
.ov{position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.92);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;color:#fff;font-family:var(--paper-font-body1_-_font-family,sans-serif)}
.box{width:min(520px,100%);display:flex;flex-direction:column;gap:12px}
.panel{background:var(--card-background-color,#222);color:var(--primary-text-color,#fff);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:12px}
video{width:100%;max-height:55vh;border-radius:14px;background:#000;object-fit:cover}
.row{display:flex;gap:10px;flex-wrap:wrap}.row>button{flex:1;min-width:130px}
input,select{font:inherit;padding:12px;border-radius:10px;border:1px solid var(--divider-color,#666);background:var(--secondary-background-color,#333);color:var(--primary-text-color,#fff);width:100%;box-sizing:border-box}
h3{margin:0}.muted{opacity:.7;font-size:.9em}.err{color:var(--error-color,#ff8a80)}.ok{color:var(--success-color,#81c784)}
`;

class MedikamentenplanScanCard extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(h) { this._hass = h; }
  getCardSize() { return 2; }
  static getStubConfig() { return {}; }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${CSS}</style><button class="main" id="go">📷 ${this._config.name || "Packung scannen"}</button>`;
    this.shadowRoot.getElementById("go").onclick = () => this._open();
  }

  async _ws(service, data, response = true) {
    const r = await this._hass.callWS({ type: "call_service", domain: "medikamentenplan", service, service_data: data, return_response: response });
    return r.response || {};
  }

  _open() {
    this._ov = document.createElement("div");
    this._ov.className = "ov";
    const root = this._ov.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${CSS}</style><div class="box" id="box"></div>`;
    this._box = root.getElementById("box");
    document.body.appendChild(this._ov);
    this._scanView();
  }

  async _close(cancelScan = true) {
    this._stop();
    this._ov?.remove(); this._ov = null;
    if (cancelScan) { try { await this._hass.callService("medikamentenplan", "scan_abbrechen"); } catch (e) { /* egal */ } }
  }

  _stop() { try { this._reader?.reset(); } catch (e) { /* egal */ } this._reader = null; }

  _set(html) { this._box.innerHTML = html; return (id) => this._box.querySelector("#" + id); }

  async _scanView(msg = "") {
    const $ = this._set(`<div class="panel"><h3>Packung scannen</h3>
      <video id="v" playsinline muted></video>
      <div class="muted" id="st">${msg || "Den DataMatrix-Code (oder PZN-Strichcode) ruhig ins Bild halten."}</div>
      <input id="man" inputmode="numeric" placeholder="oder PZN / Code von Hand eingeben">
      <div class="row"><button class="sec" id="manok">Eingabe prüfen</button><button class="sec" id="x">Abbrechen</button></div></div>`);
    $("x").onclick = () => this._close();
    $("manok").onclick = () => { const v = $("man").value.trim(); if (v) this._onCode(v.length <= 8 && /^\d+$/.test(v) ? "-" + v : v); };
    if (!navigator.mediaDevices?.getUserMedia) { $("st").innerHTML = '<span class="err">Kamera nicht verfügbar (HTTPS und Kamera-Erlaubnis nötig). Eingabe von Hand geht.</span>'; return; }
    try {
      await loadZXing();
      const Z = window.ZXing;
      const hints = new Map([[Z.DecodeHintType.POSSIBLE_FORMATS, [Z.BarcodeFormat.DATA_MATRIX, Z.BarcodeFormat.CODE_39, Z.BarcodeFormat.CODE_128, Z.BarcodeFormat.EAN_13, Z.BarcodeFormat.QR_CODE]]]);  // kein TRY_HARDER: scheitert mit mehreren Formaten (getestet)
      this._reader = new Z.BrowserMultiFormatReader(hints, 150);
      let done = false;
      await this._reader.decodeFromConstraints(
        { video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 }, advanced: [{ focusMode: "continuous" }] } },
        $("v"), (res) => { if (res && !done) { done = true; this._stop(); this._onCode(res.getText()); } });
    } catch (e) {
      $("st").innerHTML = `<span class="err">Kamera-Fehler: ${e.message || e}. Eingabe von Hand geht.</span>`;
    }
  }

  async _onCode(code) {
    this._stop();
    this._code = code;
    this._set(`<div class="panel"><h3>Code erkannt</h3><div class="muted">Prüfe…</div></div>`);
    let r;
    try { r = await this._ws("scan_code", { code }); }
    catch (e) { return this._msg("Fehler", e.message || String(e), true); }
    this._res = r;
    const info = [r.pzn && "PZN " + r.pzn, r.charge && "Charge " + r.charge, r.verfall && "Verfall " + r.verfall.split("-").reverse().join(".")].filter(Boolean).join(" · ");
    if (r.status === "ungueltig") return this._msg("Code nicht lesbar", r.fehler || "", true, true);
    if (r.status === "doppelt") return this._msg("Schon gebucht", "Diese Packung (Seriennummer) wurde bereits gebucht. " + info, true);
    this._choose(r, info);
  }

  _msg(title, text, bad = false, retry = false) {
    const $ = this._set(`<div class="panel"><h3 class="${bad ? "err" : "ok"}">${title}</h3><div>${text}</div>
      <div class="row">${retry ? '<button id="again">Nochmal scannen</button>' : '<button id="again">Weitere Packung scannen</button>'}<button class="sec" id="x">Schließen</button></div></div>`);
    $("again").onclick = () => this._scanView(); $("x").onclick = () => this._close(false);
  }

  _choose(r, info) {
    const known = r.status === "bekannt";
    const meds = known ? r.medikamente : r.kandidaten;
    const label = (m) => `${m.name}${m.plan ? " (" + m.plan + ")" : ""}`;
    const opts = meds.map((m, i) => `<option value="${i}">${label(m)}</option>`).join("");
    const $ = this._set(`<div class="panel"><h3>${known ? (meds.length === 1 ? label(meds[0]) : "Welches Medikament?") : "Unbekannte Packung"}</h3>
      <div class="muted">${info}</div>
      ${known && meds.length === 1 ? `<div class="muted">Vorrat: ${meds[0].vorrat_packungen} Packung(en)</div>` : `<select id="sel">${known ? "" : '<option value="">Medikament wählen…</option>'}${opts}</select>`}
      ${known ? "" : '<div class="muted">Die PZN wird gemerkt, beim nächsten Scan erkennt HA die Packung.</div>'}
      <input id="gr" type="number" step="any" min="0.01" inputmode="decimal" placeholder="Packungsgröße (Stück), optional">
      <div class="row"><button id="vor">Auf Vorrat legen</button><button id="anf">Jetzt anfangen</button></div>
      <button class="sec" id="x">Abbrechen</button></div>`);
    $("x").onclick = () => this._close();
    const pick = () => {
      const s = $("sel"); const i = s ? s.value : "0";
      if (i === "") { this._msg("Bitte Medikament wählen", "", true, false); setTimeout(() => this._choose(r, info), 1200); return null; }
      return meds[+i];
    };
    const book = async (service) => {
      const m = pick(); if (!m) return;
      const data = { code: this._code, entity_id: m.entity_id };
      const g = parseFloat($("gr").value); if (g > 0) data.packungsgroesse = g;
      try {
        const out = await this._ws(service, data);
        const mm = out.medikament || m;
        this._msg("Gebucht", `${mm.name}: ${service === "vorrat_hinzufuegen" ? "auf Vorrat gelegt (jetzt " + mm.vorrat_packungen + " Packung(en))" : "Packung angefangen"}.`);
      } catch (e) { this._msg("Fehler", e.message || String(e), true, true); }
    };
    $("vor").onclick = () => book("vorrat_hinzufuegen");
    $("anf").onclick = () => book("packung_anfangen");
  }
}
if (!customElements.get("medikamentenplan-scan-card")) customElements.define("medikamentenplan-scan-card", MedikamentenplanScanCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "medikamentenplan-scan-card", name: "Medikamentenplan Scanner", description: "Packungs-Code per Kamera scannen (lokal)" });
