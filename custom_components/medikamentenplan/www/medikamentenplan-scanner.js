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

// DOM nur per createElement/textContent: keine dynamischen Werte (Code-Inhalt, Namen, Fehlertexte) in innerHTML
function h(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "text") e.textContent = v;
    else if (k === "onclick") e.onclick = v;
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c) e.append(c);
  return e;
}
const panel = (...kids) => h("div", { class: "panel" }, ...kids);
const row = (...kids) => h("div", { class: "row" }, ...kids);
const fmtDate = (iso) => iso.split("-").reverse().join(".");

class MedikamentenplanScanCard extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; }
  getCardSize() { return 2; }
  static getStubConfig() { return {}; }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    root.replaceChildren(h("style", { text: CSS }), h("button", { class: "main", text: "\u{1F4F7} " + (this._config.name || "Packung scannen"), onclick: () => this._open() }));
  }

  async _ws(service, data, response = true) {
    const r = await this._hass.callWS({ type: "call_service", domain: "medikamentenplan", service, service_data: data, return_response: response });
    return r.response || {};
  }

  _open() {
    this._ov = h("div", { class: "ov" });
    const root = this._ov.attachShadow({ mode: "open" });
    this._box = h("div", { class: "box" });
    root.append(h("style", { text: CSS }), this._box);
    document.body.appendChild(this._ov);
    this._scanView();
  }

  async _close(cancelScan = true) {
    this._stop();
    this._ov?.remove(); this._ov = null;
    if (cancelScan) { try { await this._hass.callService("medikamentenplan", "scan_abbrechen"); } catch (e) { /* egal */ } }
  }

  _stop() { try { this._reader?.reset(); } catch (e) { /* egal */ } this._reader = null; }

  _show(...kids) { this._box.replaceChildren(...kids); }

  async _scanView(msg = "") {
    const video = h("video", { playsinline: true, muted: true });
    video.muted = true;
    const st = h("div", { class: "muted", text: msg || "Den DataMatrix-Code (oder PZN-Strichcode) ruhig ins Bild halten." });
    const man = h("input", { inputmode: "numeric", placeholder: "oder PZN / Code von Hand eingeben" });
    this._show(panel(h("h3", { text: "Packung scannen" }), video, st, man,
      row(h("button", { class: "sec", text: "Eingabe pr\u00fcfen", onclick: () => { const v = man.value.trim(); if (v) this._onCode(v.length <= 8 && /^\d+$/.test(v) ? "-" + v : v); } }),
          h("button", { class: "sec", text: "Abbrechen", onclick: () => this._close() }))));
    if (!navigator.mediaDevices?.getUserMedia) { st.className = "err"; st.textContent = "Kamera nicht verf\u00fcgbar (HTTPS und Kamera-Erlaubnis n\u00f6tig). Eingabe von Hand geht."; return; }
    try {
      await loadZXing();
      const Z = window.ZXing;
      const hints = new Map([[Z.DecodeHintType.POSSIBLE_FORMATS, [Z.BarcodeFormat.DATA_MATRIX, Z.BarcodeFormat.CODE_39, Z.BarcodeFormat.CODE_128, Z.BarcodeFormat.EAN_13, Z.BarcodeFormat.QR_CODE]]]);  // kein TRY_HARDER: scheitert mit mehreren Formaten (getestet)
      this._reader = new Z.BrowserMultiFormatReader(hints, 150);
      let done = false;
      await this._reader.decodeFromConstraints(
        { video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 }, advanced: [{ focusMode: "continuous" }] } },
        video, (res) => { if (res && !done) { done = true; this._stop(); this._onCode(res.getText()); } });
    } catch (e) {
      st.className = "err"; st.textContent = "Kamera-Fehler: " + (e.message || e) + ". Eingabe von Hand geht.";
    }
  }

  async _onCode(code) {
    this._stop();
    this._code = code;
    this._show(panel(h("h3", { text: "Code erkannt" }), h("div", { class: "muted", text: "Pr\u00fcfe\u2026" })));
    let r;
    try { r = await this._ws("scan_code", { code }); }
    catch (e) { return this._msg("Fehler", e.message || String(e), true); }
    const info = [r.pzn && "PZN " + r.pzn, r.charge && "Charge " + r.charge, r.verfall && "Verfall " + fmtDate(r.verfall)].filter(Boolean).join(" \u00b7 ");
    if (r.status === "ungueltig") return this._msg("Code nicht lesbar", r.fehler || "", true, true);
    if (r.status === "doppelt") return this._msg("Schon gebucht", "Diese Packung (Seriennummer) wurde bereits gebucht. " + info, true);
    this._choose(r, info);
  }

  _msg(title, text, bad = false, retry = false) {
    this._show(panel(h("h3", { class: bad ? "err" : "ok", text: title }), h("div", { text }),
      row(h("button", { text: retry ? "Nochmal scannen" : "Weitere Packung scannen", onclick: () => this._scanView() }),
          h("button", { class: "sec", text: "Schlie\u00dfen", onclick: () => this._close(false) }))));
  }

  _choose(r, info) {
    const known = r.status === "bekannt";
    const meds = known ? r.medikamente : r.kandidaten;
    const label = (m) => m.name + (m.plan ? " (" + m.plan + ")" : "");
    let sel = null;
    if (!(known && meds.length === 1)) {
      sel = h("select", {});
      if (!known) sel.append(h("option", { value: "", text: "Medikament w\u00e4hlen\u2026" }));
      meds.forEach((m, i) => sel.append(h("option", { value: String(i), text: label(m) })));
    }
    const gr = h("input", { type: "number", step: "any", min: "0.01", inputmode: "decimal", placeholder: "Packungsgr\u00f6\u00dfe (St\u00fcck), optional" });
    const pick = () => {
      const i = sel ? sel.value : "0";
      if (i === "") { this._msg("Bitte Medikament w\u00e4hlen", "", true, false); setTimeout(() => this._choose(r, info), 1200); return null; }
      return meds[+i];
    };
    const book = async (service) => {
      const m = pick(); if (!m) return;
      const data = { code: this._code, entity_id: m.entity_id };
      const g = parseFloat(gr.value); if (g > 0) data.packungsgroesse = g;
      try {
        const out = await this._ws(service, data);
        const mm = out.medikament || m;
        this._msg("Gebucht", mm.name + ": " + (service === "vorrat_hinzufuegen" ? "auf Vorrat gelegt (jetzt " + mm.vorrat_packungen + " Packung(en))" : "Packung angefangen") + ".");
      } catch (e) { this._msg("Fehler", e.message || String(e), true, true); }
    };
    this._show(panel(
      h("h3", { text: known ? (meds.length === 1 ? label(meds[0]) : "Welches Medikament?") : "Unbekannte Packung" }),
      h("div", { class: "muted", text: info }),
      known && meds.length === 1 ? h("div", { class: "muted", text: "Vorrat: " + meds[0].vorrat_packungen + " Packung(en)" }) : sel,
      known ? null : h("div", { class: "muted", text: "Die PZN wird gemerkt, beim n\u00e4chsten Scan erkennt HA die Packung." }),
      gr,
      row(h("button", { text: "Auf Vorrat legen", onclick: () => book("vorrat_hinzufuegen") }), h("button", { text: "Jetzt anfangen", onclick: () => book("packung_anfangen") })),
      h("button", { class: "sec", text: "Abbrechen", onclick: () => this._close() })));
  }
}
if (!customElements.get("medikamentenplan-scan-card")) customElements.define("medikamentenplan-scan-card", MedikamentenplanScanCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "medikamentenplan-scan-card", name: "Medikamentenplan Scanner", description: "Packungs-Code per Kamera scannen (lokal)" });
