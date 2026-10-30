/* Medikamentenplan: Scanner-Karte. Kamera via getUserMedia, Erkennung native BarcodeDetector, Fallback ZXing (lokal mitgeliefert, kein CDN). */
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
[hidden]{display:none!important}
.box{width:100%;display:flex;flex-direction:column;gap:12px}
.log{font-size:.75em;opacity:.8}.log pre{white-space:pre-wrap;margin:4px 0 0}
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

const LOG = [];  // modulweit: bleibt auch erhalten, wenn HA die Karte neu erzeugt
const RETRY_ERR = ["NotReadableError", "OverconstrainedError", "AbortError"];
class MedikamentenplanScanCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._build();
    this._main.textContent = "\u{1F4F7} " + (this._config.name || "Packung scannen");
  }
  set hass(hass) { this._hass = hass; }  // nur speichern: nie DOM/Stream anfassen
  getCardSize() { return 2; }
  static getStubConfig() { return {}; }
  connectedCallback() {
    clearTimeout(this._dc); if (this._built) this._log("Karte verbunden");
    this._pageHide ||= () => this._stop("Seite verlassen/ausgeblendet");
    this._vis ||= () => { if (document.hidden) this._stop("Seite nicht mehr sichtbar"); };
    window.addEventListener("pagehide", this._pageHide); document.addEventListener("visibilitychange", this._vis);
  }
  disconnectedCallback() {
    window.removeEventListener("pagehide", this._pageHide); document.removeEventListener("visibilitychange", this._vis);
    this._log("Karte getrennt (HA baut Ansicht um?)");
    clearTimeout(this._dc);  // Gnadenfrist: bei sofortigem Wiederanhaengen laeuft der Stream weiter
    this._dc = setTimeout(() => { if (!this.isConnected) this._abort("Karte wurde aus dem Dashboard entfernt"); }, 3000);
  }

  _build() {
    if (this._built) return;
    this._built = true;
    const root = this.attachShadow({ mode: "open" });
    this._main = h("button", { class: "main", onclick: () => this._open() });
    this._box = h("div", { class: "box", hidden: true });
    root.append(h("style", { text: CSS }), this._main, this._box);
  }

  _log(t) {
    LOG.push(new Date().toTimeString().slice(0, 8) + " " + t);
    if (LOG.length > 30) LOG.shift();
    if (this._logPre) this._logPre.textContent = LOG.join("\n");
  }

  _abort(reason) { this._stop(reason); if (this._st) { this._st.className = "err"; this._st.textContent = "Beendet: " + reason; } this._state = "error"; }

  async _ws(service, data, response = true) {
    const r = await this._hass.callWS({ type: "call_service", domain: "medikamentenplan", service, service_data: data, return_response: response });
    return r.response || {};
  }

  _open() {
    this._main.hidden = true; this._box.hidden = false;
    this._scanView();
  }

  async _close(cancelScan = true) {
    this._stop("Abbrechen/Schlie\u00dfen");
    this._box.replaceChildren(); this._box.hidden = true; this._main.hidden = false;
    this._state = "idle";
    if (cancelScan) { try { await this._hass.callService("medikamentenplan", "scan_abbrechen"); } catch (e) { /* egal */ } }
  }

  _stop(reason = "") {
    if (this._tok || this._stream) this._log("Stop: " + (reason || "?"));
    this._tok = null; clearTimeout(this._timer); clearTimeout(this._to);
    if (reason !== "Neustart der Scan-Ansicht") this._restoreMotion(reason);
    try { this._stream?.getTracks().forEach((t) => t.stop()); } catch (e) { /* egal */ }
    this._stream = null;
  }

  // Optional: Fully-Bewegungserkennung (Schalter-Entity) waehrend des Scans pausieren; Sicherheitsnetz in HA stellt sie nach 3 min wieder her
  async _pauseMotion() {
    const ent = this._config?.pause_fully_motion;
    if (!ent || this._paused) return;
    if (this._hass?.states?.[ent]?.state !== "on") return this._log("Bewegungserkennung nicht aktiv (" + (this._hass?.states?.[ent]?.state ?? "unbekannt") + "), kein Pausieren");
    this._paused = ent;  // vor dem await setzen: ein Stop waehrend des Aufrufs stellt wieder her
    try { await this._hass.callService("switch", "turn_off", { entity_id: ent }); this._log("Bewegungserkennung pausiert (" + ent + ")"); }
    catch (e) { this._log("Pausieren fehlgeschlagen: " + (e.message || e)); }
  }

  async _restoreMotion(reason) {
    const ent = this._paused;
    if (!ent) return;
    this._paused = null;
    try { await this._hass.callService("switch", "turn_on", { entity_id: ent }); this._log("Bewegungserkennung wiederhergestellt (" + reason + ")"); }
    catch (e) { this._log("Wiederherstellen fehlgeschlagen: " + (e.message || e)); }
  }

  _show(...kids) { this._box.replaceChildren(...kids); }

  // Erkennung: native BarcodeDetector (Chrome Android) wenn data_matrix unterstuetzt, sonst ZXing (lokal) per Canvas
  async _makeDetect() {
    const want = ["data_matrix", "code_39", "code_128", "ean_13", "qr_code"];
    if (this._config?.detector !== "zxing" && window.BarcodeDetector) {
      try {
        const sup = await window.BarcodeDetector.getSupportedFormats();
        if (sup.includes("data_matrix")) {
          const bd = new window.BarcodeDetector({ formats: want.filter((f) => sup.includes(f)) });
          return { name: "native", run: async (v) => (await bd.detect(v))[0]?.rawValue };
        }
      } catch (e) { /* weiter mit ZXing */ }
    }
    await loadZXing();
    const Z = window.ZXing;
    const rd = new Z.MultiFormatReader();
    rd.setHints(new Map([[Z.DecodeHintType.POSSIBLE_FORMATS, [Z.BarcodeFormat.DATA_MATRIX, Z.BarcodeFormat.CODE_39, Z.BarcodeFormat.CODE_128, Z.BarcodeFormat.EAN_13, Z.BarcodeFormat.QR_CODE]]]));  // kein TRY_HARDER: scheitert mit mehreren Formaten (getestet)
    const cv = document.createElement("canvas");
    const cx = cv.getContext("2d", { willReadFrequently: true });
    return { name: "zxing", run: (v) => {
      const k = Math.min(1, 1280 / v.videoWidth);
      cv.width = Math.round(v.videoWidth * k); cv.height = Math.round(v.videoHeight * k);
      cx.drawImage(v, 0, 0, cv.width, cv.height);
      try { return rd.decode(new Z.BinaryBitmap(new Z.HybridBinarizer(new Z.HTMLCanvasElementLuminanceSource(cv)))).getText(); }
      catch (e) { return null; }  // NotFoundException = kein Code im Bild
    } };
  }

  // Kamera oeffnen; bei NotReadable/Overconstrained/Abort mit gelockerten Constraints erneut (je Versuch ein Log-Eintrag)
  async _openCamera(alive) {
    const md = navigator.mediaDevices;
    const tries = [
      ["environment+1080p", { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }],
      ["environment", { facingMode: { ideal: "environment" } }],
      ["ohne facingMode", {}],
      ["video:true", true],
    ];
    let last, enumerated = false;
    for (let i = 0; i < tries.length || !enumerated; i++) {
      if (i >= tries.length) {  // letzte Stufe: jede videoinput-deviceId einzeln
        enumerated = true;
        let devs = [];
        try { devs = (await md.enumerateDevices()).filter((d) => d.kind === "videoinput"); } catch (e) { this._log("enumerateDevices: " + (e.name || e)); }
        this._log("Kameras: " + (devs.map((d) => d.label || d.deviceId.slice(0, 8)).join(", ") || "keine"));
        devs.forEach((d) => tries.push(["Geraet " + (d.label || d.deviceId.slice(0, 8)), { deviceId: { exact: d.deviceId } }]));
        if (i >= tries.length) break;
      }
      const [name, video] = tries[i];
      this._log("Kamera-Versuch " + (i + 1) + ": " + name);
      let s;
      try { s = await md.getUserMedia({ audio: false, video }); }
      catch (e) {
        last = e;
        this._log("Versuch " + (i + 1) + " fehlgeschlagen: " + (e?.name || "") + " " + (e?.message || e));
        if (!RETRY_ERR.includes(e?.name)) throw e;
        continue;
      }
      if (!alive()) { s.getTracks().forEach((t) => t.stop()); this._log("Stream verworfen (Ansicht wurde ersetzt)"); return null; }
      this._log("getUserMedia ok (" + name + ", " + (s.getVideoTracks()[0]?.label || "?") + ")");
      return s;
    }
    throw last;
  }

  async _scanView(msg = "") {
    const video = h("video", { autoplay: true, playsinline: true, muted: true });
    video.muted = true;
    const st = (this._st = h("div", { class: "muted", text: "Kamera wird gestartet \u2026" }));
    const man = h("input", { inputmode: "numeric", placeholder: "oder PZN / Code von Hand eingeben" });
    const torch = h("button", { class: "sec", text: "\u{1F526} Licht", hidden: true });
    const pre = (this._logPre = h("pre", { text: LOG.join("\n") }));
    // Zustandsmaschine: idle -> starting -> scanning -> found | error; jeder Wechsel setzt einen Statustext
    const status = (state, t, cls = "muted") => { this._state = state; st.className = cls; st.textContent = t; this._log(state + ": " + t); if (state === "error") this._restoreMotion("Fehler"); };
    this._show(panel(h("h3", { text: "Packung scannen" }), video, st, torch, man,
      row(h("button", { class: "sec", text: "Eingabe pr\u00fcfen", onclick: () => { const v = man.value.trim(); if (v) { this._stop("manuelle Eingabe"); this._onCode(v.length <= 8 && /^\d+$/.test(v) ? "-" + v : v); } } }),
          h("button", { class: "sec", text: "Abbrechen", onclick: () => this._close() })),
      h("details", { class: "log" }, h("summary", { text: "Debug-Log" }), pre)));
    this._stop("Neustart der Scan-Ansicht");
    const tok = (this._tok = {});
    const alive = () => this._tok === tok;
    status("starting", msg || "Kamera wird gestartet \u2026");
    if (!navigator.mediaDevices?.getUserMedia) return status("error", "Kamera nicht verf\u00fcgbar (HTTPS und Kamera-Erlaubnis n\u00f6tig). Eingabe von Hand geht.", "err");
    try {
      let stream;
      try {
        if (this._config?.pause_fully_motion) { await this._pauseMotion(); if (!alive()) return; await new Promise((r) => setTimeout(r, 1800)); if (!alive()) return; }
        stream = await this._openCamera(alive);
        if (!stream) return;
      } catch (e) {
        const n = e?.name;
        status("error", n === "NotAllowedError" || n === "SecurityError" ? "Keine Kamera-Berechtigung (Browser/App-Einstellungen pr\u00fcfen). Eingabe von Hand geht."
          : n === "NotFoundError" || n === "OverconstrainedError" ? "Kamera nicht verf\u00fcgbar. Eingabe von Hand geht."
          : "Kamera-Fehler: " + (n || "") + " " + (e?.message || e) + ". Eingabe von Hand geht.", "err");
        if (RETRY_ERR.includes(n)) st.textContent += " Kamera evtl. von anderer App belegt (z. B. Fully-Bewegungserkennung).";
        return;
      }
      if (!alive()) { this._log("Stream verworfen (Ansicht wurde ersetzt)"); stream.getTracks().forEach((t) => t.stop()); return; }
      this._stream = stream;
      video.srcObject = stream;
      const track = stream.getVideoTracks()[0];
      track?.addEventListener("ended", () => { if (alive()) { this._stop("Kamera-Track vom System beendet"); status("error", "Die Kamera wurde vom System beendet (Berechtigung/App im Hintergrund?). Bitte nochmal scannen.", "err"); } });
      const caps = track?.getCapabilities?.() || {};
      if (caps.focusMode?.includes("continuous")) track.applyConstraints({ advanced: [{ focusMode: "continuous" }] }).catch(() => {});
      if (caps.torch) {
        let on = false;
        torch.hidden = false;
        torch.onclick = async () => { try { await track.applyConstraints({ advanced: [{ torch: !on }] }); on = !on; } catch (e) { this._log("Licht-Fehler: " + (e.message || e)); } };
      }
      try { await video.play(); this._log("play ok " + video.videoWidth + "x" + video.videoHeight); }
      catch (e) { this._stop("play() fehlgeschlagen"); return status("error", "Video konnte nicht gestartet werden: " + (e.message || e), "err"); }
      if (!alive()) return;
      status("starting", "Detektor wird geladen \u2026");
      const det = await this._makeDetect();
      if (!alive()) return;
      this._detector = det.name;
      this._log("Detektor: " + det.name);
      this._to = setTimeout(() => { if (alive()) { this._stop("Zeit\u00fcberschreitung"); status("error", "Zeit\u00fcberschreitung ohne Code. Bitte nochmal scannen.", "err"); } }, 120000);
      status("scanning", "Suche Code \u2026 den DataMatrix-Code (oder PZN-Strichcode) ruhig ins Bild halten.");
      const tick = async () => {
        if (!alive()) return;
        let code;
        if (video.readyState >= 2 && video.videoWidth) { try { code = await det.run(video); } catch (e) { /* naechster Frame */ } }
        if (!alive()) return;
        if (code) { status("found", "Code erkannt", "ok"); this._stop("Code erkannt"); this._onCode(code); return; }
        this._timer = setTimeout(tick, 150);
      };
      tick();
    } catch (e) {
      if (alive()) { this._stop("Ausnahme"); status("error", "Kamera-Fehler: " + (e.message || e) + ". Eingabe von Hand geht.", "err"); }
    }
  }

  async _onCode(code) {
    this._stop("Code \u00fcbernommen");
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
