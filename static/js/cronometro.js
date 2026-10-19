// Semáforos de SLA: cuenta regresiva y color, con la hora del servidor (no la del dispositivo).
(function () {
  "use strict";

  const COLORES = {
    verde: "bg-green-100 text-green-800",
    amarillo: "bg-yellow-200 text-yellow-900",
    rojo: "bg-red-600 text-white",
  };
  const TODAS = Object.values(COLORES).join(" ").split(" ");

  // Mismo desfase que el reloj del encabezado: hora del servidor menos hora del dispositivo.
  const reloj = document.getElementById("reloj");
  const desfase = reloj ? Number(reloj.dataset.epochMs) - Date.now() : 0;
  // La página puede quedar abierta mucho rato: el desfase se fija al cargar.

  function duracion(ms) {
    const minutos = Math.floor(Math.abs(ms) / 60000);
    const horas = Math.floor(minutos / 60);
    if (horas >= 24) return Math.floor(horas / 24) + " d " + (horas % 24) + " h";
    return horas ? horas + " h " + String(minutos % 60).padStart(2, "0") + " min" : minutos + " min";
  }

  function pintar(caja) {
    const inicio = Number(caja.dataset.inicio);
    const limite = Number(caja.dataset.limite);
    const congelado = caja.dataset.congelado ? Number(caja.dataset.congelado) : null;
    const ahora = congelado || Date.now() + desfase;
    const fraccion = (ahora - inicio) / Math.max(1, limite - inicio);
    const restante = limite - ahora;
    const color = fraccion >= 1 ? "rojo" : fraccion >= 0.7 ? "amarillo" : "verde";

    let texto;
    if (congelado) texto = restante >= 0 ? "Resuelto a tiempo" : "Resuelto con " + duracion(restante) + " de retraso";
    else texto = restante >= 0 ? "Quedan " + duracion(restante) : "Vencido hace " + duracion(restante);
    const destino = caja.querySelector("[data-texto]");
    if (destino) destino.textContent = texto;
    caja.classList.remove.apply(caja.classList, TODAS);
    caja.classList.add.apply(caja.classList, COLORES[color].split(" "));
  }

  function pintarTodos() { document.querySelectorAll("[data-cronometro]").forEach(pintar); }
  document.addEventListener("htmx:load", pintarTodos);
  setInterval(pintarTodos, 15000);
})();
