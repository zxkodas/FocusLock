const $ = (id) => document.getElementById(id);

// i18n.js corre antes que este archivo (ver popup.html / options.html).
const T = window.TickFenceT || { t: (en) => en };
const t = T.t;

function render(state) {
  const box = $("state");
  const detail = $("detail");
  if (!state) {
    box.className = "state offline";
    box.textContent = t("No connection to TickFence", "Sin conexión con TickFence");
    detail.textContent = t(
      "The Windows service did not respond. Check that it is running and that the address is right.",
      "El servicio de Windows no respondió. Verificá que esté corriendo y que la dirección sea correcta."
    );
    return;
  }
  if (state.locked) {
    box.className = "state locked";
    box.textContent = t(
      "LOCKED — the extension is stopping the configured domains",
      "BLOQUEADO — la extensión está frenando los dominios configurados"
    );
  } else {
    box.className = "state open";
    box.textContent = t(
      "UNLOCKED — the extension is blocking nothing",
      "DESBLOQUEADO — la extensión no está bloqueando nada"
    );
  }
  const parts = [
    `${t("Readings", "Lecturas")}: ${state.credits} ${t("of", "de")} ${state.required}`,
    `${t("Blocked domains", "Dominios bloqueados")}: ${state.blockedCount}`,
  ];
  if (state.reason) parts.push(`${t("Reason", "Motivo")}: ${state.reason}`);
  parts.push(`${t("Updated", "Actualizado")}: ${new Date(state.updatedAt).toLocaleTimeString()}`);
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
