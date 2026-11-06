// Suit une partie en direct : interroge Firestore (API REST publique, même clé que l'app — publique
// par nature, cf. app/main.py) toutes les POLL_MS, et réinjecte le plan de table reçu dans le même
// template que le récap final (recap_template.html), sans le modifier : on refait exactement ce que
// app/recap.py::build() fait côté Python, mais côté navigateur, à chaque poll.
const PROJECT_ID = "servo-skull-74f0a";
const API_KEY = "AIzaSyDR20oqMz2q6qHS_e109pliJnYQhP6NaeU";
const POLL_MS = 4000;

const statusEl = document.getElementById("status");
const frameEl = document.getElementById("frame");
const emptyEl = document.getElementById("empty");
const code = new URLSearchParams(location.search).get("code");

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = cls || "";
}

if (!code || !/^[0-9a-f]{8}$/.test(code)) {
  setStatus("lien invalide", "err");
  emptyEl.hidden = false;
} else if (typeof DecompressionStream === "undefined") {
  setStatus("navigateur non supporté", "err");
  emptyEl.hidden = false;
  emptyEl.textContent = "Ce navigateur ne supporte pas la décompression nécessaire (DecompressionStream). Essaie une version récente de Chrome, Edge ou Firefox.";
} else {
  start();
}

let templatePromise = null;
function template() {
  if (!templatePromise) templatePromise = fetch("recap_template.html").then(r => r.text());
  return templatePromise;
}

async function gunzipToJson(b64) {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const ds = new DecompressionStream("gzip");
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  const text = await new Response(stream).text();
  return JSON.parse(text);
}

async function poll() {
  const url = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents/live_games/${code}?key=${API_KEY}`;
  let doc;
  try {
    const r = await fetch(url);
    if (r.status === 404) {
      setStatus("en attente de la première capture…");
      emptyEl.hidden = false;
      frameEl.hidden = true;
      return;
    }
    if (!r.ok) throw new Error("http " + r.status);
    doc = await r.json();
  } catch (e) {
    setStatus("connexion perdue, nouvel essai…", "err");
    return;
  }
  const b64 = doc.fields && doc.fields.payload && doc.fields.payload.stringValue;
  if (!b64) {
    setStatus("en attente de la première capture…");
    emptyEl.hidden = false;
    frameEl.hidden = true;
    return;
  }
  let data;
  try {
    data = await gunzipToJson(b64);
  } catch (e) {
    setStatus("données illisibles", "err");
    return;
  }
  const tpl = await template();
  const json = JSON.stringify(data).replace(/</g, "\\u003c");
  frameEl.srcdoc = tpl.replace("/*__DATA__*/null", json);
  frameEl.hidden = false;
  emptyEl.hidden = true;
  setStatus("en direct", "live");
}

function start() {
  poll();
  setInterval(poll, POLL_MS);
}
