const api = typeof browser !== "undefined" && browser.alarms ? browser : chrome;

const $ = (id) => document.getElementById(id);

const VERSION = "1.3";

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
      "Bloqueado",
      `${state.credits}/${state.required} tareas · ` +
        `${count} dominios${warn ? " · " + warn : ""}`
    );
  } else {
    setState("o", "Desbloqueado", state.reason || "listo para trabajar");
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
    paint(store.lastState, "sin conexion en vivo");
  } else {
    setState("x", "Sin datos", "no se pudo leer el estado");
  }

  const err = result.error;
  if (err === "sin configurar") {
    $("title").textContent = "Sin configurar";
    $("detail").textContent = "pegá la dirección en Configuración · v" + VERSION;
  } else if (err === "token invalido") {
    $("title").textContent = "Dirección vieja";
    $("detail").textContent = "pegá de nuevo la dirección · v" + VERSION;
  } else if (err === "sin conexion") {
    $("title").textContent = "Servicio caído";
    $("detail").textContent = "abrí la app de Windows · v" + VERSION;
  }
}

$("refresh").addEventListener("click", async (ev) => {
  const btn = ev.currentTarget;
  const original = btn.textContent;
  btn.textContent = "Actualizando...";
  btn.disabled = true;
  $("title").textContent = "Consultando…";
  $("detail").textContent = "";
  await refresh();
  btn.textContent = original;
  btn.disabled = false;
});

$("options").addEventListener("click", () => api.runtime.openOptionsPage());

refresh();
setInterval(refresh, 5000);
