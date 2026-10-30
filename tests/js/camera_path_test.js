// Aufruf: CHROME_BIN=<chrome-headless-shell> PLAYWRIGHT_CORE=<pfad>/playwright-core node tests/js/camera_path_test.js
// Headless-Test Scanner-Karte 1.6.6: Kamerapfad user/environment, Spiegelung per CSS, Konsolenfehler
const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require(process.env.PLAYWRIGHT_CORE || "playwright-core");

const WWW = path.join(__dirname, "..", "..", "custom_components", "medikamentenplan", "www");
const PAGE = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><body></body>
<script type="module">import "/www/medikamentenplan-scanner.js";</script>`;

const server = http.createServer((req, res) => {
  if (req.url === "/") { res.setHeader("content-type", "text/html"); return res.end(PAGE); }
  const f = path.join(WWW, req.url.replace(/^\/www\//, "").split("?")[0]);
  if (!f.startsWith(WWW) || !fs.existsSync(f)) { res.statusCode = 404; return res.end(); }
  res.setHeader("content-type", f.endsWith(".js") ? "text/javascript" : "application/octet-stream");
  res.end(fs.readFileSync(f));
});

// Stub: Constraints aufzeichnen, je Szenario die ersten N Aufrufe mit NotReadableError scheitern lassen
const STUB = (scenario) => `
  window.__calls = []; window.__errs = [];
  const fakeDevs = ${JSON.stringify(scenario.devices || [])};
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {
    enumerateDevices: async () => fakeDevs,
    getUserMedia: async (c) => {
      window.__calls.push(c);
      if (window.__calls.length <= ${scenario.failFirst || 0}) { const e = new Error("busy"); e.name = "NotReadableError"; throw e; }
      const cv = document.createElement("canvas"); cv.width = 320; cv.height = 240;
      const s = cv.captureStream(5);
      const tr = s.getVideoTracks()[0];
      const label = c && c.deviceId ? "Stub " + c.deviceId.exact : "Stub-Kamera";
      Object.defineProperty(tr, "label", { value: label });
      tr.getSettings = () => ({ facingMode: ${JSON.stringify(scenario.facing || "")} });
      return s;
    } } });
  window.BarcodeDetector = undefined;
`;

async function run(browser, base, scenario) {
  const ctx = await browser.newContext({ viewport: { width: 400, height: 800 } });
  await ctx.addInitScript(STUB(scenario));
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  await page.goto(base + "/", { waitUntil: "load" });
  await page.waitForFunction(() => customElements.get("medikamentenplan-scan-card"));
  const res = await page.evaluate(async (cfg) => {
    const card = document.createElement("medikamentenplan-scan-card");
    card.hass = { callWS: async () => ({ response: {} }), callService: async () => ({}), states: {} };
    card.setConfig(cfg);
    document.body.append(card);
    card.shadowRoot.querySelector("button.main").click();
    // warten bis Stream da ist oder Fehler
    for (let i = 0; i < 100; i++) {
      await new Promise((r) => setTimeout(r, 100));
      const v = card.shadowRoot.querySelector("video");
      if (v && v.srcObject) break;
    }
    await new Promise((r) => setTimeout(r, 400));
    const v = card.shadowRoot.querySelector("video");
    const cs = v ? getComputedStyle(v) : null;
    return {
      calls: window.__calls,
      hasStream: !!(v && v.srcObject),
      mirrorClass: v ? v.classList.contains("mirror") : null,
      transform: cs ? cs.transform : null,
      log: card._logPre ? card._logPre.textContent : "",
    };
  }, scenario.cfg);
  await ctx.close();
  return { name: scenario.name, ...res, errors };
}

(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch({ executablePath: process.env.CHROME_BIN, args: ["--no-sandbox"] });
  const scenarios = [
    { name: "A user, ok beim ersten Versuch", cfg: { camera: "user" }, facing: "user" },
    { name: "B user, ohne camera-Option = environment", cfg: {}, facing: "environment" },
    { name: "C user, 2x busy -> Geraet mit 'Front' im Label", cfg: { camera: "user" }, failFirst: 2, facing: "user",
      devices: [{ kind: "videoinput", label: "Back Camera", deviceId: "b1" }, { kind: "videoinput", label: "Front Camera", deviceId: "f1" }] },
    { name: "D user, camera_label gesetzt", cfg: { camera: "user", camera_label: "webcam" }, failFirst: 2,
      devices: [{ kind: "videoinput", label: "Front Camera", deviceId: "f1" }, { kind: "videoinput", label: "USB Webcam 2", deviceId: "w2" }] },
    { name: "E user, kein Label-Treffer -> video:true", cfg: { camera: "user" }, failFirst: 2,
      devices: [{ kind: "videoinput", label: "Back Camera", deviceId: "b1" }] },
  ];
  let fail = 0;
  for (const s of scenarios) {
    const r = await run(browser, base, s);
    const ok = r.hasStream && r.errors.length === 0;
    const firstFacing = r.calls[0]?.video?.facingMode ?? r.calls[0]?.facingMode ?? r.calls[0];
    console.log("\n== " + r.name + (ok ? "  [OK]" : "  [PRUEFEN]"));
    console.log("calls:", JSON.stringify(r.calls));
    console.log("stream:", r.hasStream, "mirrorClass:", r.mirrorClass, "transform:", r.transform);
    console.log("errors:", JSON.stringify(r.errors));
    console.log("log:\n" + r.log.split("\n").filter((l) => /Kamera|getUserMedia|Versuch|Geraet/.test(l)).join("\n"));
    if (!ok) fail++;
  }
  await browser.close();
  server.close();
  console.log("\nFehlgeschlagen:", fail);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error("TESTFEHLER", e); process.exit(2); });
