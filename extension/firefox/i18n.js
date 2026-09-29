/*
 * Aplica el idioma del sistema a los textos con data-t-en / data-t-es.
 *
 * El HTML viene en ingles (que es el default de TickFence) y este script
 * sobreescribe los textos segun navigator.language. Se corre antes que
 * options.js y popup.js, asi que cuando ellos escriban en los nodos ya
 * estan en el idioma correcto.
 *
 * Por que el idioma del sistema y no el de TickFence: la extension no lee la
 * config de la app. Tendria que pedirlo por el endpoint /state, y para el 95%
 * de los casos coincide. Un endpoint menos del que depende el popup vale mas.
 */
(function () {
  "use strict";

  var es = (navigator.language || "en").toLowerCase().indexOf("es") === 0;

  function aplicar() {
    var nodos = document.querySelectorAll("[data-t-en]");
    for (var i = 0; i < nodos.length; i++) {
      var nodo = nodos[i];
      var texto = es ? nodo.getAttribute("data-t-es") : nodo.getAttribute("data-t-en");
      // Un texto sin traducir se deja el de ingles: preferimos que aparezca
      // en el idioma que casi es correcto antes que mostrar la clave.
      nodo.textContent = texto || nodo.getAttribute("data-t-en") || nodo.textContent;
    }
    document.documentElement.lang = es ? "es" : "en";
  }

  aplicar();

  // popup.js y options.js escriben textos despues. Se les da la funcion para
  // que la usen al armar sus propios mensajes.
  window.TickFenceT = {
    es: es,
    t: function (en, esTexto) {
      return es ? (esTexto || en) : en;
    },
    aplicar: aplicar,
  };
})();
