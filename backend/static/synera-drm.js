/*! Synera DRM v1.0
 * Hosted-preview enforcement. Polls the Synera API and applies one of three states:
 *   PREVIEW  -> tamper-resistant watermark + copy/inspect deterrents
 *   KILLED   -> page blurred, interaction disabled, payment lock screen
 *   UNLOCKED -> everything removed, script disarmed permanently
 * Usage: <script src="https://YOUR-API/static/synera-drm.js" data-project="prj_xxxx"></script>
 * (data-project falls back to the ?pid= query parameter.)
 * NOTE: client-side enforcement is a deterrent for a hosted preview, not a security boundary.
 * Fail-closed: if the API cannot be reached twice in a row before any state is known, PREVIEW applies.
 */
(function () {
  "use strict";
  if (window.__synera) return;
  var script = document.currentScript;
  var cfg = {
    project: (script && script.getAttribute("data-project")) || new URLSearchParams(location.search).get("pid"),
    api: (script && script.getAttribute("data-api")) ||
      (script && script.src ? new URL(script.src, location.href).origin : ""),
    payUrl: (script && script.getAttribute("data-pay-url")) || "",
    interval: 2000
  };
  if (!cfg.project) { console.warn("[Synera] no project id, protection inactive"); return; }
  window.__synera = true;

  var state = null, info = {}, fails = 0, host = null, shadow = null, wm = null, lock = null;
  var pollTimer = null, guardTimer = null, observer = null, prev = null, armed = true;

  function esc(s) { var d = document.createElement("div"); d.textContent = String(s == null ? "" : s); return d.innerHTML; }
  function inr(n) { try { return "₹" + Number(n).toLocaleString("en-IN"); } catch (e) { return "₹" + n; } }

  function tile() {
    var line2 = info.invoice_number ? "Invoice " + info.invoice_number : "";
    var svg = "<svg xmlns='http://www.w3.org/2000/svg' width='380' height='220'>" +
      "<g transform='rotate(-24 190 110)' font-family='system-ui,sans-serif' font-weight='700' fill='rgba(239,68,68,0.30)'>" +
      "<text x='20' y='105' font-size='19' letter-spacing='2'>ESCROW PREVIEW • UNPAID INVOICE</text>" +
      "<text x='20' y='130' font-size='13' letter-spacing='1'>" + esc(line2) + "</text></g></svg>";
    return "url(\"data:image/svg+xml;utf8," + encodeURIComponent(svg) + "\")";
  }

  function build() {
    host = document.createElement("div");
    host.setAttribute("data-synera", "");
    shadow = host.attachShadow({ mode: "closed" });
    var style = document.createElement("style");
    style.textContent =
      ":host{all:initial}" +
      ".wm{position:fixed;inset:0;z-index:2147483646;pointer-events:none;background-repeat:repeat}" +
      ".lock{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;" +
      "background:rgba(6,8,18,.62);font-family:system-ui,-apple-system,sans-serif;color:#e5e7eb}" +
      ".card{max-width:440px;width:calc(100% - 40px);padding:28px;border-radius:20px;text-align:center;" +
      "background:rgba(17,24,39,.92);border:1px solid rgba(255,255,255,.12);box-shadow:0 20px 80px rgba(0,0,0,.6)}" +
      ".ico{width:56px;height:56px;margin:0 auto 14px;border-radius:50%;display:grid;place-items:center;background:rgba(239,68,68,.15)}" +
      "h1{margin:0 0 8px;font-size:22px}p{margin:0 0 14px;line-height:1.5;color:#9ca3af;font-size:14px}" +
      ".amt{font-size:30px;font-weight:800;color:#fff;margin:6px 0}" +
      ".tag{display:inline-block;font:12px ui-monospace,monospace;padding:4px 10px;border-radius:999px;" +
      "background:rgba(239,68,68,.15);color:#fca5a5;margin-bottom:14px}" +
      "a.pay{display:inline-block;padding:11px 20px;border-radius:12px;background:#6366f1;color:#fff;text-decoration:none;font-weight:600}";
    wm = document.createElement("div"); wm.className = "wm";
    lock = document.createElement("div"); lock.className = "lock";
    shadow.appendChild(style); shadow.appendChild(wm); shadow.appendChild(lock);
    document.documentElement.appendChild(host);
  }

  function ensureHost() { if (!host || !host.isConnected) { build(); } }

  function renderLock() {
    var pay = cfg.payUrl ? "<a class='pay' href='" + esc(cfg.payUrl) + "'>Settle invoice</a>" : "";
    lock.innerHTML = "<div class='card'><div class='ico'><svg width='26' height='26' viewBox='0 0 24 24' fill='none' " +
      "stroke='#f87171' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><rect x='4' y='11' width='16' height='10' rx='2'/>" +
      "<path d='M8 11V7a4 4 0 0 1 8 0v4'/></svg></div><h1>Delivery locked</h1>" +
      "<div class='tag'>ESCROW LOCK • " + esc(info.invoice_number || "") + "</div>" +
      "<div class='amt'>" + inr(info.amount_inr) + "</div>" +
      "<p>" + esc(info.message || "Awaiting escrow settlement.") + "</p>" + pay + "</div>";
  }

  function setBodyLocked(on) {
    var b = document.body; if (!b) return;
    if (on) {
      if (!prev) prev = { filter: b.style.getPropertyValue("filter"), pe: b.style.getPropertyValue("pointer-events"),
        us: b.style.getPropertyValue("user-select"), ov: document.documentElement.style.getPropertyValue("overflow") };
      if (b.style.getPropertyValue("filter") !== "blur(18px)") b.style.setProperty("filter", "blur(18px)", "important");
      if (b.style.getPropertyValue("pointer-events") !== "none") b.style.setProperty("pointer-events", "none", "important");
      b.style.setProperty("user-select", "none", "important");
      document.documentElement.style.setProperty("overflow", "hidden", "important");
    } else if (prev) {
      ["filter", "pointer-events", "user-select"].forEach(function (k, i) {
        var v = [prev.filter, prev.pe, prev.us][i];
        v ? b.style.setProperty(k, v) : b.style.removeProperty(k);
      });
      prev.ov ? document.documentElement.style.setProperty("overflow", prev.ov) : document.documentElement.style.removeProperty("overflow");
      prev = null;
    }
  }

  // ---- deterrents -------------------------------------------------------
  function block(e) { e.preventDefault(); e.stopPropagation(); return false; }
  function keyGuard(e) {
    var k = (e.key || "").toLowerCase(), c = e.ctrlKey || e.metaKey;
    if (e.key === "F12" || (c && e.shiftKey && ["i", "j", "c"].indexOf(k) > -1) ||
        (c && ["u", "s", "c", "p"].indexOf(k) > -1)) return block(e);
  }
  function addGuards() {
    document.addEventListener("contextmenu", block, true);
    document.addEventListener("keydown", keyGuard, true);
    document.addEventListener("copy", block, true);
    document.addEventListener("dragstart", block, true);
  }
  function removeGuards() {
    document.removeEventListener("contextmenu", block, true);
    document.removeEventListener("keydown", keyGuard, true);
    document.removeEventListener("copy", block, true);
    document.removeEventListener("dragstart", block, true);
  }

  // ---- apply ------------------------------------------------------------
  function apply() {
    if (!armed || !state) return;
    if (state === "UNLOCKED") return disarm();
    ensureHost();
    if (state === "PREVIEW") {
      wm.style.display = "block"; wm.style.backgroundImage = tile();
      lock.style.display = "none"; setBodyLocked(false);
    } else if (state === "KILLED") {
      wm.style.display = "block"; wm.style.backgroundImage = tile();
      renderLock(); lock.style.display = "flex"; setBodyLocked(true);
    }
  }

  function disarm() {
    armed = false;
    clearInterval(pollTimer); clearInterval(guardTimer);
    if (observer) observer.disconnect();
    removeGuards(); setBodyLocked(false);
    if (host && host.parentNode) host.parentNode.removeChild(host);
    notify();
  }

  function notify() {
    try { window.parent !== window && window.parent.postMessage({ type: "synera:state", state: state }, "*"); } catch (e) {}
  }

  function setInfo(d) {
    var changed = d.state !== state || d.message !== info.message;
    info = d;
    if (d.state !== state) { state = d.state; notify(); }
    if (changed || state !== "UNLOCKED") apply();
  }

  function poll() {
    fetch(cfg.api + "/api/drm/" + encodeURIComponent(cfg.project), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { fails = 0; setInfo(d); })
      .catch(function () {
        fails++;
        if (fails >= 2 && state === null) { state = "PREVIEW"; info = { invoice_number: "", message: "" }; notify(); apply(); }
      });
  }

  function start() {
    addGuards();
    // Re-add the overlay / body lock if someone removes or edits it from DevTools.
    observer = new MutationObserver(function () { if (armed) apply(); });
    observer.observe(document.documentElement, { childList: true });
    if (document.body) observer.observe(document.body, { attributes: true, attributeFilter: ["style", "class"] });
    guardTimer = setInterval(function () { if (armed) apply(); }, 500);
    poll(); pollTimer = setInterval(poll, cfg.interval);
  }

  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
})();
