const $ = (id) => document.getElementById(id);

function render(state) {
  const box = $("state");
  const detail = $("detail");
  if (!state) {
    box.className = "state offline";
    box.textContent = "Sin conexión con TickFence";
    detail.textContent =
      "El servicio de Windows no respondió. Verificá que esté corriendo y que la dirección sea correcta.";
    return;
  }
  if (state.locked) {
    box.className = "state locked";
    box.textContent = "BLOQUEADO — la extensión está frenando los dominios configurados";
  } else {
    box.className = "state open";
    box.textContent = "DESBLOQUEADO — la extensión no está bloqueando nada";
  }
  const parts = [
    `Lecturas: ${state.credits} de ${state.required}`,
    `Dominios bloqueados: ${state.blockedCount}`,
  ];
  if (state.reason) parts.push(`Motivo: ${state.reason}`);
  parts.push(`Actualizado: ${new Date(state.updatedAt).toLocaleTimeString()}`);
  detail.textContent = parts.join(" · ");
}

async function refresh() {
  const res = await chrome.runtime.sendMessage({ type: "state" });
  render(res && res.live ? res.live.state : res && res.last ? res.last : null);
}

$("save").addEventListener("click", async () => {
  const endpoint = $("endpoint").value.trim();
  if (!endpoint) return;
  await chrome.storage.local.set({ endpoint });
  await chrome.runtime.sendMessage({ type: "refresh" });
  await refresh();
});

$("test").addEventListener("click", refresh);

(async () => {
  const store = await chrome.storage.local.get(["endpoint"]);
  $("endpoint").value = store.endpoint || "";
  await refresh();
  setInterval(refresh, 5000);
})();
