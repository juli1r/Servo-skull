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
const liveBarEl = document.getElementById("livebar");
const liveLabelEl = document.getElementById("liveLabel");
const code = new URLSearchParams(location.search).get("code");

// Spectateur distant : atterrit sur le plan de table plein écran avec une barre de contrôle à
// nous (◀ lecture ▶, "revenir en direct"), sans le panneau d'analyse post-partie (récit, unités,
// outils de dessin, barre de rounds). recap_template.html n'est pas modifié (partagé avec le vrai
// récap) : on masque/pilote son contenu depuis l'extérieur, une fois le contenu injecté
// (re)chargé dans l'iframe. Les boutons #bPrev/#bPlay/#bNext du template restent dans le DOM
// malgré leur conteneur masqué et répondent toujours à un .click() programmatique : on les
// déclenche depuis notre barre plutôt que de réimplémenter la lecture automatique.
let liveRefreshTimer = null, playing = false;

function refreshLiveLabel() {
  const doc = frameEl.contentDocument;
  if (!doc) return;
  const title = doc.querySelector(".ptitle");
  const phase = doc.querySelector(".pts button.pt.on");
  liveLabelEl.textContent = title ? title.textContent : "";
  if (phase) liveLabelEl.textContent += " · " + phase.textContent;
}

function setPlaying(on) {
  playing = on;
  document.getElementById("bLivePlay").textContent = on ? "❚❚" : "▶";
  clearInterval(liveRefreshTimer);
  liveRefreshTimer = on ? setInterval(refreshLiveLabel, 400) : null;
}

document.getElementById("bLivePrev").onclick = () => {
  frameEl.contentWindow.step(-1);
  refreshLiveLabel();
};
document.getElementById("bLiveNext").onclick = () => {
  frameEl.contentWindow.step(1);
  refreshLiveLabel();
};
document.getElementById("bLivePlay").onclick = () => {
  frameEl.contentDocument.getElementById("bPlay").click();
  setPlaying(!playing);
  refreshLiveLabel();
};
document.getElementById("bLiveNow").onclick = () => {
  frameEl.contentWindow.step(1e9);
  setPlaying(false);
  refreshLiveLabel();
};

frameEl.addEventListener("load", () => {
  const win = frameEl.contentWindow, doc = frameEl.contentDocument;
  if (!win || !doc) return;
  if (typeof win.setView === "function") win.setView("game");
  // let/const du template ne deviennent pas des propriétés de `win` (contrairement aux
  // déclarations de fonction) : step() avec un grand nombre se clampe à la dernière phase connue.
  if (typeof win.step === "function") win.step(1e9);
  const header = doc.querySelector("header");
  if (header) header.style.display = "none";
  ["tabs", "rail", "panel"].forEach(id => { const el = doc.getElementById(id); if (el) el.style.display = "none"; });
  const work = doc.getElementById("work");
  if (work) work.style.gridTemplateColumns = "1fr";
  setPlaying(false);
  refreshLiveLabel();
});

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = cls || "";
}

if (!code || !(/^[0-9a-f]{8}$/.test(code) || code === "local")) {
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
  // "local" : échappatoire de test sans Firestore, cf. app/gen_local_live_payload.py.
  const url = code === "local"
    ? "local-payload.json"
    : `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents/live_games/${code}?key=${API_KEY}`;
  let doc;
  try {
    const r = await fetch(url);
    if (r.status === 404) {
      setStatus("en attente de la première capture…");
      emptyEl.hidden = false;
      frameEl.hidden = true;
      liveBarEl.hidden = true;
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
    liveBarEl.hidden = true;
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
  liveBarEl.hidden = false;
  emptyEl.hidden = true;
  setStatus("en direct", "live");
}

function start() {
  poll();
  setInterval(poll, POLL_MS);
}
