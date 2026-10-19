// Campos con mínimo de caracteres (atributo data-minimo): contador debajo, borde rojo mientras falta texto
// y verde con ✓ cuando alcanza. Si se intenta enviar incompleto, no se envía y salta al campo que falta.
(function () {
  "use strict";

  const ROJO = ["border-red-500", "bg-red-50"];
  const VERDE = ["border-green-500"];
  const NEUTRO = ["border-slate-300"];

  function medir(campo) {
    const minimo = Number(campo.dataset.minimo);
    const largo = campo.value.trim().length;
    return { minimo: minimo, largo: largo, completo: largo >= minimo };
  }

  function pintar(campo, forzar) {
    const m = medir(campo);
    // El rojo aparece cuando la persona ya empezó a escribir (o intentó enviar), no apenas abre la pantalla.
    const error = !m.completo && (forzar || campo.dataset.tocado);
    campo.classList.remove.apply(campo.classList, ROJO.concat(VERDE, NEUTRO));
    campo.classList.add.apply(campo.classList, m.completo ? VERDE : error ? ROJO : NEUTRO);

    const contador = campo.contadorMinimo;
    if (!contador) return;
    if (m.completo) contador.textContent = "✓ Listo (" + m.largo + " caracteres)";
    else if (error) contador.textContent = "Faltan " + (m.minimo - m.largo) + " caracteres (mínimo " + m.minimo + ")";
    else contador.textContent = m.largo + " / " + m.minimo + " caracteres mínimo";
    contador.className = "mt-1 block text-sm font-semibold " +
      (m.completo ? "text-green-700" : error ? "text-red-600" : "text-slate-500");
  }

  function iniciar(raiz) {
    raiz.querySelectorAll("[data-minimo]").forEach(function (campo) {
      if (campo.dataset.validacion) return;
      campo.dataset.validacion = "1";
      if (!campo.hasAttribute("data-sin-contador")) {
        campo.contadorMinimo = document.createElement("span");
        campo.insertAdjacentElement("afterend", campo.contadorMinimo);
      }
      campo.addEventListener("input", function () { campo.dataset.tocado = "1"; pintar(campo); });
      campo.addEventListener("blur", function () { if (campo.value) campo.dataset.tocado = "1"; pintar(campo); });
      pintar(campo);
    });
  }

  // Fase de captura: corre antes que HTMX y que el bloqueo "Enviando…", así el botón no queda bloqueado.
  document.addEventListener("submit", function (evento) {
    const formulario = evento.target;
    if (formulario.hasAttribute("data-reporte")) return; // el reporte del operador lo valida reportes.js
    const incompletos = Array.from(formulario.querySelectorAll("[data-minimo]")).filter(function (c) {
      return !medir(c).completo;
    });
    if (!incompletos.length) return;
    evento.preventDefault();
    evento.stopImmediatePropagation();
    incompletos.forEach(function (c) { pintar(c, true); });
    incompletos[0].focus();
    incompletos[0].scrollIntoView({ block: "center", behavior: "smooth" });
  }, true);

  document.addEventListener("DOMContentLoaded", function () { iniciar(document); });
  document.addEventListener("htmx:load", function (e) { iniciar(e.target); });
})();
