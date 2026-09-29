/*
 * TickFence - background (MV3).
 *
 * Este archivo es el MISMO en extension/chrome/ y en extension/firefox/, y
 * test_extension lo verifica. La logica no se duplica: la unica diferencia
 * entre los dos navegadores esta en el manifest (background.service_worker
 * en Chrome, background.scripts en Firefox) y en el shim de mas abajo, que
 * elige entre el namespace `browser` y el `chrome`.
 *
 * OJO con el diseño: en Firefox la pagina se APAGA sola cuando no hay nada
 * que hacer. Por eso el estado se guarda en storage en cada ciclo, y el popup
 * lo lee de ahi primero en vez de depender de que el worker este vivo.
 */

const api = typeof browser !== "undefined" && browser.alarms ? browser : chrome;

const POLL_ALARM = "tickfence-poll";
const POLL_PERIOD_MINUTES = 0.5;
const RULE_ID_BASE = 1000;
const RULE_PRIORITY = 1;
const VERSION = "1.1";

const RESOURCE_TYPES = [
  "main_frame", "sub_frame", "stylesheet", "script", "image", "font",
  "object", "xmlhttprequest", "ping", "media", "websocket", "other",
];

// ------------------------------------------------------------------ estado
async function getEndpoint() {
  const store = await api.storage.local.get(["endpoint"]);
  return store.endpoint || null;
}

async function setError(error) {
  const store = await api.storage.local.get(["lastError"]);
  await api.storage.local.set({ lastError: error, lastErrorAt: Date.now() });
  if (error && store.lastError !== error) {
    // Solo se registra el cambio, no cada ciclo.
    console.warn("[TickFence]", error);
  }
}

// Devuelve el estado, o null con el motivo en storage.lastError.
async function fetchState() {
  const endpoint = await getEndpoint();
  if (!endpoint) {
    await setError("sin configurar");
    return null;
  }
  try {
    const res = await fetch(endpoint, { cache: "no-store" });
    if (!res.ok) {
      // 403 = token vencido. Casi siempre el servicio se reinstaló.
      await setError(res.status === 403 ? "token invalido" : "http " + res.status);
      return null;
    }
    const state = await res.json();
    await api.storage.local.set({
      lastError: null,
      lastOkAt: Date.now(),
      endpoint: endpoint,
      version: VERSION,
    });
    return state;
  } catch (e) {
    await setError("sin conexion");
    return null;
  }
}

// ---------------------------------------------------------------- matching
function hostMatches(host, rule) {
  return host === rule || host.endsWith("." + rule);
}

function shouldBlockHost(host, blocked, allowed) {
  host = String(host || "").toLowerCase().replace(/^www\./, "");
  if (!host) return false;
  for (const rule of allowed || []) {
    if (hostMatches(host, String(rule).toLowerCase())) return false;
  }
  for (const rule of blocked || []) {
    if (hostMatches(host, String(rule).toLowerCase())) return true;
  }
  return false;
}

function hostOf(url) {
  try {
    return new URL(url).hostname.toLowerCase().replace(/^www\./, "");
  } catch (_) {
    return "";
  }
}

// ------------------------------------------------------------- reglas DNR
function buildRule(id, host) {
  return {
    id,
    priority: RULE_PRIORITY,
    action: { type: "block" },
    condition: { urlFilter: "||" + host, resourceTypes: RESOURCE_TYPES },
  };
}

async function syncRules(state) {
  const blocked = state && state.locked ? state.blockedHosts || [] : [];
  const wanted = Array.from(new Set(blocked.map((h) => String(h).toLowerCase()))).sort();

  const existing = await api.declarativeNetRequest.getDynamicRules();
  const key = (r) => r.condition.urlFilter.replace(/^\|\|/, "");
  const have = new Set(existing.map(key));
  const want = new Set(wanted);

  const removeRuleIds = existing.filter((r) => !want.has(key(r))).map((r) => r.id);
  const addRules = wanted.filter((h) => !have.has(h)).map((h, i) => buildRule(RULE_ID_BASE + i, h));

  if (removeRuleIds.length || addRules.length) {
    await api.declarativeNetRequest.updateDynamicRules({ removeRuleIds, addRules });
  }
}

// --------------------------------------------------------------- pestanas
async function closeBlockedTabs(state) {
  if (!state || !state.locked) return 0;
  const blocked = state.blockedHosts || [];
  const allowed = state.allowedHosts || [];
  if (!blocked.length) return 0;

  const tabs = await api.tabs.query({});
  const victims = [];
  for (const tab of tabs) {
    const host = hostOf(tab.url || "");
    if (!host) continue;
    if (shouldBlockHost(host, blocked, allowed)) victims.push(tab.id);
  }
  if (victims.length) {
    try {
      await api.tabs.remove(victims);
    } catch (_) {
      /* alguna pestana ya se habia cerrado */
    }
  }
  return victims.length;
}

// ------------------------------------------------------------------ ciclo
async function tick() {
  const state = await fetchState();
  if (!state) return;

  await syncRules(state);
  const closed = await closeBlockedTabs(state);

  await api.storage.local.set({
    lastState: {
      locked: !!state.locked,
      blockedCount: (state.blockedHosts || []).length,
      credits: state.credits,
      required: state.required,
      reason: state.reason || "",
      updatedAt: Date.now(),
    },
    lastClosed: closed,
  });
}

function startPolling() {
  api.alarms.create(POLL_ALARM, { periodInMinutes: POLL_PERIOD_MINUTES });
}

api.alarms.onAlarm.addListener((a) => {
  if (a.name === POLL_ALARM) tick();
});

api.runtime.onInstalled.addListener(() => {
  startPolling();
  tick();
});

api.runtime.onStartup.addListener(() => {
  startPolling();
  tick();
});

// Red de seguridad: si el tick de 30s se atrasa, cerramos al navegar.
api.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status !== "complete" || !tab.url) return;
  fetchState().then(async (state) => {
    if (!state || !state.locked) return;
    const host = hostOf(tab.url);
    if (shouldBlockHost(host, state.blockedHosts || [], state.allowedHosts || [])) {
      try {
        await api.tabs.remove(tabId);
      } catch (_) {}
    }
  });
});

api.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg === "refresh") {
    tick().then(() => sendResponse({ ok: true })).catch(() => sendResponse({ ok: false }));
    return true;
  }
  if (msg === "state") {
    // Solo lee storage. Sin red ni esperas: contesta siempre, aunque la event
    // page se esté descargando. El popup consulta el servidor por su cuenta.
    api.storage.local.get(["lastState", "lastError"]).then(
      (store) =>
        sendResponse({
          live: null,
          last: store.lastState || null,
          error: store.lastError || null,
          version: VERSION,
        }),
      () => sendResponse({ live: null, last: null, error: "sin datos", version: VERSION })
    );
    return true;
  }
  return false;
});

startPolling();
tick();
