const api = typeof browser !== "undefined" && browser.alarms ? browser : chrome;

const $ = (id) => document.getElementById(id);

function render(state) {
  const box = $("state");
  const detail = $("detail");
  if (!state) {
    box.className = "state offline";
    box.textContent = "Sin conexion con FocusLock";
    detail.textContent =
      "El servicio de Windows no respondio. Verifica que este corriendo y que la direccion sea correcta.";
    return;
  }
  if (state.locked) {
    box.className = "state locked";
    box.textContent = "BLOQUEADO - la extension esta frenando los dominios configurados";
  } else {
    box.className = "state open";
    box.textContent = "DESBLOQUEADO - la extension no esta bloqueando nada";
  }
  const parts = [
    `Lecturas: ${state.credits} de ${state.required}`,
    `Dominios bloqueados: ${state.blockedCount}`,
  ];
  if (state.reason) parts.push(`Motivo: ${state.reason}`);
  parts.push(`Actualizado: ${new Date(state.updatedAt).toLocaleTimeString()}`);
  detail.textContent = parts.join(" - ");
}

async function refresh() {
  const res = await api.runtime.sendMessage({ type: "state" });
  render(res && res.live ? res.live : res && res.last ? res.last : null);
}

$("save").addEventListener("click", async () => {
  const endpoint = $("endpoint").value.trim();
  if (!endpoint) return;
  await api.storage.local.set({ endpoint });
  await api.runtime.sendMessage({ type: "refresh" });
  await refresh();
});

$("test").addEventListener("click", refresh);

(async () => {
  const store = await api.storage.local.get(["endpoint"]);
  $("endpoint").value = store.endpoint || "";
  await refresh();
  setInterval(refresh, 5000);
})();
