"""Scripts Lua envoyés à TTS à la demande (rien n'est installé dans la table).

Calés sur la table LCT / Hutber 10e : on passe par les variables globales du mod
(`startMenu_GUID`, `scoresheet_GUID`, compteurs…) plutôt que par des GUID en dur,
pour survivre aux mises à jour du mod. Tout est en lecture seule, sauf
`camera()` (bouge uniquement TA caméra) et `restore()` (explicite, avec confirmation).
"""
from __future__ import annotations

import json

_HELPERS = r"""
local function gobj(var)
  local g = Global.getVar(var)
  if g == nil then return nil end
  return getObjectFromGUID(g)
end
local function cval(o)
  -- compteur natif TTS (anciennes tables) ou jeton-compteur scripté (LCT 11e : getValue / script_state)
  if o == nil then return nil end
  if o.Counter ~= nil then
    local ok, v = pcall(function() return o.Counter.getValue() end)
    if ok and v ~= nil then return v end
  end
  local ok, v = pcall(function() return o.call("getValue") end)
  if ok and type(v) == "number" then return v end
  local ok2, st = pcall(function() return o.script_state end)
  if ok2 and st ~= nil and st ~= "" then
    local ok3, t = pcall(function() return JSON.decode(st) end)
    if ok3 and type(t) == "table" and type(t.value) == "number" then return t.value end
  end
  return nil
end
local function counter(var) return cval(gobj(var)) end
local function v3(v) return {x = v.x, y = v.y, z = v.z} end
local function zoneCards(var)
  local z = gobj(var)
  local names = {}
  if z == nil then return names end
  for _, o in ipairs(z.getObjects()) do
    local n = o.getName()
    if n ~= nil and n ~= "" then table.insert(names, n) end
  end
  return names
end
local function state(full)
  if full == nil then full = true end
  local r = {}
  local sm = gobj("startMenu_GUID")
  r.round = counter("gameTurnCounter_GUID")
  if sm ~= nil then
    r.turn = sm.getVar("currentTurn")
    r.phase = sm.getVar("currentPhase")
    r.inGame = sm.getVar("inGame")
    r.deployMode = sm.getVar("deployMode")
    local ph = sm.getTable("phases")
    if ph ~= nil and r.phase ~= nil then r.phaseName = ph[r.phase] end
  end
  r.turns = {Red = counter("redTurnCounter_GUID"), Blue = counter("blueTurnCounter_GUID")}
  if not full then return r end
  r.full = true
  r.vp = {Red = counter("redVPCounter_GUID"), Blue = counter("blueVPCounter_GUID")}
  -- feuille de score : données brutes + indices/plafonds du mod (le calcul se fait côté Python)
  local ss = gobj("scoresheet_GUID") or gobj("scoreSheet_GUID")
  if ss ~= nil then
    local sh = {scores = ss.getTable("scores"), eob = ss.getTable("endOfBattle")}
    for _, k in ipairs({"BOARD_PRIMARY_K", "BOARD_SECONDARY_K", "BTN_K_IX_PRIMARY", "BTN_K_IX_SECONDARY",
                        "BTN_K_IX_SECONDARY_1", "BTN_K_IX_SECONDARY_2", "BTN_K_IX_CHALLENGER",
                        "GAME_PRIMARY_CAP", "GAME_SECONDARY_CAP", "GAME_BASE_POINTS", "GAME_TOTAL_CAP"}) do
      sh[k] = ss.getVar(k)
    end
    r.sheet = sh
    r.scoresheetDesc = ss.getDescription()
  end
  r.cp = {Red = counter("redCPCounter_GUID"), Blue = counter("blueCPCounter_GUID")}
  r.players = {}
  for _, c in ipairs({"Red", "Blue"}) do
    local p = Player[c]
    if p ~= nil and p.seated then r.players[c] = p.steam_name end
  end
  return r
end
"""

UNIT_PATTERN = "^%[%x%x%x%x%x%x%]%d+/%d+%[%-%]"


def poll() -> str:
    """Lecture complète, autonome (1er contact, invité, tests)."""
    return _HELPERS + "\nreturn state(true)\n"


def poll_install() -> str:
    """Installe une fois la fonction de lecture dans l'environnement Lua de la partie
    (en mémoire seulement, rien n'est écrit dans la sauvegarde). Les lectures suivantes
    n'envoient plus qu'une ligne : TTS n'a plus à recompiler 3 Ko de Lua toutes les 2 s."""
    return _HELPERS + "\nSERVO_SKULL_STATE = state\nreturn state(true)\n"


def poll_fast(full: bool) -> str:
    return ("if SERVO_SKULL_STATE == nil then return {undef = true} end\n"
            f"return SERVO_SKULL_STATE({'true' if full else 'false'})\n")


def capture(known_unit_guids: list[str], my_color: str | None = None, light: bool = False) -> str:
    """Instantané complet : état, score détaillé, cartes, objets sur la table.
    Le JSON de spawn n'est renvoyé que pour les unités jamais vues (pour pouvoir
    les refaire apparaître lors d'une restauration)."""
    known = json.dumps({g: True for g in known_unit_guids}) if known_unit_guids else "{}"
    return (_HELPERS + r"""
local known = JSON.decode([==[""" + known + r"""]==]) or {}
-- capture légère (fin de phase) : seulement les figurines, et pour celles déjà connues
-- seulement position / rotation / PV ; décors et détails restent ceux de la dernière capture complète
local light = __LIGHT__
local __clk = (os ~= nil and os.clock) or function() return 0 end
local __t0, __tm = __clk(), {}
local function __mark(n) local t = __clk(); __tm[#__tm + 1] = {n, math.floor((t - __t0) * 1000)}; __t0 = t end
local r = state()
__mark("state")
local ss = gobj("scoresheet_GUID")
if ss ~= nil then
  r.scores = ss.getTable("scores")
  r.scoresheetDesc = ss.getDescription()
end
r.cards = {
  deployment = zoneCards("deploymentCardZone_GUID"),
  primary = zoneCards("primaryCardZone_GUID"),
  redPrimary = {}, bluePrimary = {}, twist = zoneCards("missionCardZone_Twist_GUID"),
  redSecondary = {},
  blueSecondary = {},
  challenger = zoneCards("challengerCardZone_GUID"),
}
for _, v in ipairs({"missionCardZone_RedPrimary1_GUID", "missionCardZone_RedPrimary2_GUID"}) do
  for _, n in ipairs(zoneCards(v)) do table.insert(r.cards.redPrimary, n) end
end
for _, v in ipairs({"missionCardZone_BluePrimary1_GUID", "missionCardZone_BluePrimary2_GUID"}) do
  for _, n in ipairs(zoneCards(v)) do table.insert(r.cards.bluePrimary, n) end
end
do -- forces de disposition (11e) : index choisi dans le menu de départ -> nom
  local smd = gobj("startMenu_GUID")
  if smd ~= nil then
    local okv, vals = pcall(function() return smd.getTable("dispositionValues") end)
    if okv and vals ~= nil then
      local ri, bi = smd.getVar("redDispositionSelected"), smd.getVar("blueDispositionSelected")
      if ri ~= nil and vals[ri] ~= nil then r.cards.redDisposition = vals[ri] end
      if bi ~= nil and vals[bi] ~= nil then r.cards.blueDisposition = vals[bi] end
    end
  end
end
r.cards.myHand = {}
local me = "__ME__"
if me ~= "" and Player[me] ~= nil then
  local okh, hand = pcall(function() return Player[me].getHandObjects() end)
  if okh and hand ~= nil then
    for _, o in ipairs(hand) do
      local n = o.getName()
      if n ~= nil and n ~= "" then table.insert(r.cards.myHand, n) end
    end
  end
end
if #r.cards.deployment == 0 then r.cards.deployment = zoneCards("missionCardZone_Deployment_GUID") end
for _, n in ipairs(zoneCards("secondary11CardZone_GUID")) do table.insert(r.cards.redSecondary, n) end
for _, n in ipairs(zoneCards("secondary12CardZone_GUID")) do table.insert(r.cards.redSecondary, n) end
for _, n in ipairs(zoneCards("secondary21CardZone_GUID")) do table.insert(r.cards.blueSecondary, n) end
for _, n in ipairs(zoneCards("secondary22CardZone_GUID")) do table.insert(r.cards.blueSecondary, n) end

__mark("zones")
-- LCT 11e : les cartes posées ne sont pas « dans » les zones (zones trop petites, cartes décalées).
-- On range chaque carte posée sur la table selon la zone de mission nommée la plus proche.
do
  local zones, cards = {}, {}
  for _, o in ipairs(getAllObjects()) do
    local t = o.type
    if t == "Scripting" then
      local n = o.getName() or ""
      local cat = nil
      local side, k = string.match(n, "^(%a+)Sec(%d+)$")
      if side == "Red" or side == "Blue" then
        cat = string.lower(side) .. ((tonumber(k) <= 2) and "Secondary" or "SecondaryDone")
      elseif string.match(n, "^RedPrimary%d$") then cat = "redPrimary"
      elseif string.match(n, "^BluePrimary%d$") then cat = "bluePrimary"
      elseif n == "DeploymentSlot" then cat = "deployment"
      elseif n == "TwistSlot" then cat = "twist" end
      if cat ~= nil then local p = o.getPosition(); table.insert(zones, {cat = cat, x = p.x, z = p.z}) end
    elseif t == "Card" then
      local n = o.getName() or ""
      if n ~= "" and not string.find(n, "^Blank") then
        local p = o.getPosition()
        local lay = false
        local okt, tg = pcall(function() return o.hasTag("layout_art_card") end)
        if okt and tg then lay = true end
        -- getData() est lourd (sérialise toute la carte) : une seule fois par carte, puis cache en mémoire TTS
        _ssImg = _ssImg or {}
        local gc = o.getGUID()
        local url = _ssImg[gc]
        if url == nil then
          url = false
          local okd, dat = pcall(function() return o.getData() end)
          if okd and dat ~= nil and dat.CustomDeck ~= nil then
            for _, dk in pairs(dat.CustomDeck) do
              if (dk.NumWidth or 1) == 1 and (dk.NumHeight or 1) == 1 then url = dk.FaceURL end
            end
          end
          _ssImg[gc] = url
        end
        if url == false then url = nil end
        table.insert(cards, {n = n, x = p.x, z = p.z, lay = lay, url = url})
      end
    end
  end
  if #zones > 0 then
    local m = {redPrimary = {}, bluePrimary = {}, deployment = {}, twist = {}, redSecondary = {}, blueSecondary = {},
               redSecondaryDone = {}, blueSecondaryDone = {}}
    for _, c in ipairs(cards) do
      local best, bd = nil, 6.0
      for _, z in ipairs(zones) do
        local d = math.sqrt((c.x - z.x) ^ 2 + (c.z - z.z) ^ 2)
        if d < bd then best, bd = z, d end
      end
      if c.lay then table.insert(m.deployment, c.n)
      elseif best ~= nil and (c.n == "Tactical Objectives" or string.find(c.n, "^Fixed")) then
        m[string.sub(best.cat, 1, string.find(best.cat, "Secondary") and (string.find(best.cat, "Secondary") - 1) or #best.cat) .. "SecMode"] = c.n
      elseif best ~= nil then table.insert(m[best.cat], c.n) end
    end
    m.images = {}
    for _, c in ipairs(cards) do if c.url ~= nil then m.images[c.n] = c.url end end
    for k, v in pairs(m) do r.cards[k] = v end
  end
end

__mark("cardscan")
local skip = {}
for _, var in ipairs({"mat_GUID", "felt_GUID", "table_GUID", "scoresheet_GUID", "startMenu_GUID"}) do
  local g = Global.getVar(var)
  if g ~= nil then skip[g] = true end
end
local skipNames = {ScriptingTrigger = true, HandTrigger = true, FogOfWarTrigger = true,
                   FogOfWar = true, Infinite_Bag = true, Custom_Model_Infinite_Bag = true,
                   ["3DText"] = true, Counter = true, Digital_Clock = true}

r.objects = {}
r.unitJson = {}
local jsonBudget = 20
local __all = getAllObjects()
for _, o in ipairs(__all) do
  local g = o.getGUID()
  local nick = o.getName() or ""
  local isUnit = string.find(nick, "^%[%x%x%x%x%x%x%]%d+/%d+%[%-%]") ~= nil
  local gm = o.getGMNotes() or ""
  if gm == "Red" or gm == "Blue" then isUnit = true end
  local p = o.getPosition()
  local keep = isUnit
  if light and isUnit and known[g] then
    table.insert(r.objects, {guid = g, name = nick, unit = true, pos = v3(p), rot = v3(o.getRotation()), k = true})
    keep = false
  elseif light then
    keep = isUnit
  elseif not keep and not skip[g] and not skipNames[o.name] then
    keep = p.y > 0.3 and math.abs(p.x) <= 50 and math.abs(p.z) <= 40
  end
  if keep then
    local b = o.getBoundsNormalized()
    local wb = o.getBounds()  -- boîte monde : son centre = vrai centre du décor (le pivot du modèle est souvent décalé)
    local e = {guid = g, name = nick, kind = o.name, unit = isUnit,
               pos = v3(p), rot = v3(o.getRotation()),
               size = {x = b.size.x, y = b.size.y, z = b.size.z},
               center = {x = wb.center.x, z = wb.center.z},
               locked = o.getLock(), gm = gm}
    if isUnit then
      local d = o.getDescription() or ""
      local i = string.find(d, "Abilities", 1, true)
      if i ~= nil then e.abilities = string.sub(d, i, i + 600) end
      e.tags = o.getTags()
      -- getJSON() est lourd : au plus 20 figurines par capture (les autres suivront aux captures suivantes)
      if not known[g] and jsonBudget > 0 then
        jsonBudget = jsonBudget - 1
        r.unitJson[g] = o.getJSON()
      end
    end
    table.insert(r.objects, e)
  end
end
__mark("objects")
r.perf = {st = __tm, nAll = #__all, nObj = #r.objects, light = light}
return r
""").replace("__ME__", my_color or "").replace("__LIGHT__", "true" if light else "false")


def camera(color: str, distance: float, pitch: float = 90.0, yaw_offset: float = 0.0,
           target_x: float = 0.0, target_z: float = 0.0) -> str:
    """Vue fixe pour TA couleur uniquement. yaw de base identique au mod (Rouge 180, Bleu 0)."""
    yaw = ((180 if color == "Red" else 0) + yaw_offset) % 360
    return (
        f'Player["{color}"].lookAt({{position = {{x = {target_x}, y = 0, z = {target_z}}}, '
        f"pitch = {pitch}, yaw = {yaw}, distance = {distance}}})\nreturn true\n"
    )


def restore(units: list[dict], spawn_json: dict[str, str], park_z: float = 60.0) -> str:
    """Remet chaque unité à sa position du tour choisi.
    - unité présente : déplacée + PV (nom) remis
    - unité détruite depuis : refait apparaître depuis son JSON
    - unité absente du tour choisi : rangée hors table (ligne z = ±park_z)"""
    payload = json.dumps({"units": units, "spawn": spawn_json, "parkZ": park_z})
    if "]==]" in payload:
        payload = payload.replace("]==]", "] ==]")
    return r"""
local data = JSON.decode([==[""" + payload + r"""]==])
local wanted = {}
local moved, spawned, parked = 0, 0, 0
for _, u in ipairs(data.units) do
  wanted[u.guid] = true
  local o = getObjectFromGUID(u.guid)
  if o ~= nil then
    o.setPosition(u.pos)
    o.setRotation(u.rot)
    if u.name ~= nil then o.setName(u.name) end
    moved = moved + 1
  elseif data.spawn[u.guid] ~= nil then
    spawnObjectJSON({json = data.spawn[u.guid], position = u.pos, rotation = u.rot})
    spawned = spawned + 1
  end
end
local px = -40
for _, o in ipairs(getAllObjects()) do
  local nick = o.getName() or ""
  if string.find(nick, "^%[%x%x%x%x%x%x%]%d+/%d+%[%-%]") ~= nil and not wanted[o.getGUID()] then
    local p = o.getPosition()
    local z = data.parkZ
    if p.z < 0 then z = -data.parkZ end
    o.setPosition({x = px, y = 2, z = z})
    px = px + 2.5
    parked = parked + 1
  end
end
return {moved = moved, spawned = spawned, parked = parked}
"""


def inspect() -> str:
    """Inventaire de la table (diagnostic) : objets, compteurs, état des scripts."""
    return r"""
local out = {}
for _, o in ipairs(getAllObjects()) do
  local p = o.getPosition()
  local e = {guid = o.getGUID(), kind = o.name, nick = o.getName(), x = p.x, y = p.y, z = p.z,
             desc = string.sub(o.getDescription() or "", 1, 80), tags = o.getTags()}
  if o.Counter ~= nil then e.counter = o.Counter.getValue() end
  local ok, st = pcall(function() return o.script_state end)
  if ok and st ~= nil and st ~= "" then e.state = string.sub(st, 1, 1500) end
  local ok2, code = pcall(function() return o.getLuaScript() end)
  if ok2 and code ~= nil then e.scriptLen = string.len(code) end
  table.insert(out, e)
end
return out
"""


def watch_install(interval: float = 2.0, heartbeat_ticks: int = 30, stale_drops: int = 15, stale_s: int = 240) -> str:
    """Veilleur Lua dans TTS (en mémoire) : regarde tour/phase toutes les `interval` s sans réseau,
    et ne prévient Servo-Skull (sendExternalMessage) que si ça change, + un signe de vie par minute.
    Les identifiants des minuteurs sont rangés dans le vrai Global (Global.setVar) pour pouvoir
    toujours arrêter les anciens, même si l'environnement d'exécution n'est pas conservé."""
    return _HELPERS + f"""
local old = Global.getTable("SERVO_SKULL_TIMERS") or {{}}
for _, id in ipairs(old) do pcall(function() Wait.stop(id) end) end
-- ordre réel des déplacements : chaque figurine posée est notée (guid, n° d'ordre, position).
-- Le Global de LCT n'a pas de onObjectDrop ; s'il en avait un, il serait appelé ensuite.
if SERVO_SKULL_ORIG_DROP == nil then SERVO_SKULL_ORIG_DROP = onObjectDrop or false end
SERVO_SKULL_DROPS = SERVO_SKULL_DROPS or {{}}
SERVO_SKULL_SEQ = SERVO_SKULL_SEQ or 0
onObjectDrop = function(color, obj)
  pcall(function()
    local n = obj.getName() or ""
    if string.find(n, "^%[%x%x%x%x%x%x%]%d+/%d+%[%-%]") ~= nil and #SERVO_SKULL_DROPS < 3000 then
      local p = obj.getPosition()
      SERVO_SKULL_SEQ = SERVO_SKULL_SEQ + 1
      table.insert(SERVO_SKULL_DROPS, {{obj.getGUID(), SERVO_SKULL_SEQ, math.floor(p.x * 100) / 100, math.floor(p.z * 100) / 100}})
    end
  end)
  if SERVO_SKULL_ORIG_DROP then return SERVO_SKULL_ORIG_DROP(color, obj) end
end
local last, beat = "", 0
local __clk = (os ~= nil and os.clock) or function() return 0 end
local tmax, tsum, tn = 0, 0, 0
local since, staleSent = os.time(), false  -- depuis quand la phase est inchangée ; alerte déjà envoyée ?
local id = Wait.time(function()
  local c0 = __clk()
  local ok, err = pcall(function()
    local sm = gobj("startMenu_GUID")
    local k = "?"
    if sm ~= nil then
      k = tostring(sm.getVar("currentTurn")) .. "|" .. tostring(sm.getVar("currentPhase")) .. "|" .. tostring(sm.getVar("inGame"))
    end
    beat = beat + 1
    if k ~= last then since = os.time(); staleSent = false end
    -- beaucoup de figurines posées, phase inchangée depuis longtemps : les joueurs ont sans doute oublié de passer la phase
    if not staleSent and k ~= "?" and #SERVO_SKULL_DROPS >= {stale_drops} and os.time() - since >= {stale_s} then
      staleSent = true
      sendExternalMessage({{servoSkull = true, stale = true, json = JSON.encode({{drops = #SERVO_SKULL_DROPS, minutes = math.floor((os.time() - since) / 60)}})}})
    end
    if k ~= last or beat >= {heartbeat_ticks} then
      local changed = (k ~= last)
      last = k
      beat = 0
      -- l'état part en texte JSON : sendExternalMessage échoue en silence sur les tables complexes
      local b0 = __clk()
      local st = state(changed)
      st.perf = {{tickMaxMs = math.floor(tmax * 1000), tickAvgMs = (tn > 0) and math.floor(tsum / tn * 10000) / 10 or 0, ticks = tn,
                 stateMs = math.floor((__clk() - b0) * 1000), changed = changed}}
      tmax, tsum, tn = 0, 0, 0
      if changed then  -- les figurines posées pendant la phase qui vient de finir
        st.drops = SERVO_SKULL_DROPS
        SERVO_SKULL_DROPS = {{}}
      end
      sendExternalMessage({{servoSkull = true, changed = changed, json = JSON.encode(st)}})
    end
  end)
  local dt = __clk() - c0
  tn = tn + 1; tsum = tsum + dt; if dt > tmax then tmax = dt end
  if not ok then Global.setVar("SERVO_SKULL_LAST_ERROR", tostring(err)) end
end, {interval}, -1)
Global.setTable("SERVO_SKULL_TIMERS", {{id}})
return state(true)
"""


def watch_stop() -> str:
    return ('local old = Global.getTable("SERVO_SKULL_TIMERS") or {}\n'
            'for _, id in ipairs(old) do pcall(function() Wait.stop(id) end) end\n'
            'Global.setTable("SERVO_SKULL_TIMERS", {})\n'
            'if SERVO_SKULL_ORIG_DROP ~= nil then onObjectDrop = SERVO_SKULL_ORIG_DROP or nil; SERVO_SKULL_ORIG_DROP = nil end\n'
            'SERVO_SKULL_DROPS = nil\nreturn #old\n')


def watch_probe() -> str:
    """Diagnostic : envoie un message tout de suite, et un autre via Wait.time dans 1 s."""
    return ('sendExternalMessage({servoSkullProbe = "direct"})\n'
            'Wait.time(function() sendExternalMessage({servoSkullProbe = "timer"}) end, 1)\n'
            'return {timers = #(Global.getTable("SERVO_SKULL_TIMERS") or {}), err = Global.getVar("SERVO_SKULL_LAST_ERROR")}\n')
