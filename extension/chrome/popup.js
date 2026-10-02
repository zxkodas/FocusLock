const api = typeof browser !== "undefined" && browser.alarms ? browser : chrome;

const $ = (id) => document.getElementById(id);

// i18n.js corre antes que este archivo y deja TickFenceT en window. El fallback
// es para que el popup siga funcionando si el script no esta.
const T = window.TickFenceT || { t: (en) => en };
const t = T.t;

const VERSION = "1.4";

function setState(kind, title, detail) {
  $("dot").className = "dot " + kind;
  $("title").textContent = title;
  $("detail").textContent = detail + "  ·  v" + VERSION;
}

/*
 * El popup consulta el servidor DIRECTAMENTE.
 *
 * En Firefox el service worker es una event page: se apaga sola y no siempre
 * está listo para responder mensajes. Depender de él hacía que el popup
 * mostrara "Sin respuesta" aunque el servicio estuviera perfecto. El popup
 * tiene los mismos permisos de host, así que puede hablar con el servidor sin
 * intermediario.
 */
async function fetchDirect() {
  const store = await api.storage.local.get(["endpoint"]);
  const endpoint = store.endpoint;
  if (!endpoint) return { error: "sin configurar" };

  try {
    const res = await fetch(endpoint, { cache: "no-store" });
    if (!res.ok) {
      return { error: res.status === 403 ? "token invalido" : "http " + res.status };
    }
    return { live: await res.json() };
  } catch (_) {
    return { error: "sin conexion" };
  }
}

// El worker sigue siendo quien instala las reglas DNR, así que le avisamos
// que hay estado nuevo. Pero si no responde, no importa: el popup ya tiene su
// respuesta.
async function nudgeWorker() {
  try {
    await api.runtime.sendMessage({ type: "refresh" });
  } catch (_) {
    /* el worker puede estar dormido; no es critico */
  }
}

function paint(state, warn) {
  if (state.locked) {
    // Viene de dos fuentes distintas: el snapshot del worker trae
    // `blockedCount`, la respuesta cruda del servidor trae `blockedHosts`.
    const count = state.blockedCount ?? (state.blockedHosts || []).length;
    setState(
      "l",
      t("Locked", "Bloqueado"),
      `${state.credits}/${state.required} ${t("tasks", "tareas")} · ` +
        `${count} ${t("domains", "dominios")}${warn ? " · " + warn : ""}`
    );
  } else {
    setState(
      "o",
      t("Unlocked", "Desbloqueado"),
      state.reason || t("ready to work", "listo para trabajar")
    );
  }
}

async function refresh() {
  // Pintar al instante lo último guardado: el popup nunca se ve vacío.
  const store = await api.storage.local.get(["lastState"]);
  if (store.lastState) paint(store.lastState, null);

  const result = await fetchDirect();

  if (result.live) {
    paint(result.live, null);
    nudgeWorker();
    return;
  }

  // Falló la consulta directa: pintar el último estado conocido con el aviso.
  if (store.lastState) {
    paint(store.lastState, t("not live", "sin conexion en vivo"));
  } else {
    setState("x", t("No data", "Sin datos"), t("could not read the state", "no se pudo leer el estado"));
  }

  const err = result.error;
  if (err === "sin configurar") {
    $("title").textContent = t("Not configured", "Sin configurar");
    $("detail").textContent =
      t("paste the address in Settings", "pegá la dirección en Configuración") +
      " · v" + VERSION;
  } else if (err === "token invalido") {
    $("title").textContent = t("Old address", "Dirección vieja");
    $("detail").textContent =
      t("paste the address again", "pegá de nuevo la dirección") + " · v" + VERSION;
  } else if (err === "sin conexion") {
    $("title").textContent = t("Service down", "Servicio caído");
    $("detail").textContent =
      t("open the Windows app", "abrí la app de Windows") + " · v" + VERSION;
  }
}

$("refresh").addEventListener("click", async (ev) => {
  const btn = ev.currentTarget;
  const original = btn.textContent;
  btn.textContent = t("Refreshing...", "Actualizando...");
  btn.disabled = true;
  $("title").textContent = t("Asking…", "Consultando…");
  $("detail").textContent = "";
  await refresh();
  btn.textContent = original;
  btn.disabled = false;
});

$("options").addEventListener("click", () => api.runtime.openOptionsPage());

refresh();
setInterval(refresh, 5000);
