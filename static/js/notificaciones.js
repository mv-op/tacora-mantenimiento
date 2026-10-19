// Notificaciones: cada 20 s pregunta al servidor (sin contar como uso de la sesión), actualiza la campana
// y el título de la pestaña, muestra avisos emergentes y hace sonar los de prioridad alta.
(function () {
  "use strict";

  const cuerpo = document.body;
  const urlEstado = cuerpo.dataset.urlNotificaciones;
  if (!urlEstado) return;

  const INTERVALO = 20000;
  const DURACION_AVISO = 8000;
  let ultima = Number(cuerpo.dataset.notifUltima || 0);
  const contador = document.getElementById("campana-contador");
  const caja = document.getElementById("avisos");
  const fijas = new Map(); // id → tarjeta en pantalla

  function csrf() {
    const meta = document.querySelector("meta[name=csrf-token]");
    return meta ? meta.content : "";
  }

  // Sonido: los navegadores solo lo permiten después de que la persona toca la página una vez.
  let audio = null;
  const botonSonido = document.getElementById("activar-sonido");
  function sonidoListo() { return audio && audio.state === "running"; }
  function desbloquear() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume().then(actualizarBoton);
    } catch (e) { /* sin audio */ }
    actualizarBoton();
  }
  function actualizarBoton() { if (botonSonido) botonSonido.hidden = sonidoListo(); }
  function sonar() {
    if (!sonidoListo()) return;
    const t = audio.currentTime;
    [0, 0.3, 0.6].forEach(function (retraso, i) {
      const oscilador = audio.createOscillator();
      const volumen = audio.createGain();
      oscilador.frequency.value = i % 2 ? 660 : 880;
      volumen.gain.setValueAtTime(0.0001, t + retraso);
      volumen.gain.exponentialRampToValueAtTime(0.5, t + retraso + 0.02);
      volumen.gain.exponentialRampToValueAtTime(0.0001, t + retraso + 0.25);
      oscilador.connect(volumen).connect(audio.destination);
      oscilador.start(t + retraso);
      oscilador.stop(t + retraso + 0.27);
    });
  }
  ["pointerdown", "keydown"].forEach(function (evento) {
    document.addEventListener(evento, desbloquear, { passive: true });
  });
  if (botonSonido) {
    botonSonido.hidden = false;
    botonSonido.addEventListener("click", function () { desbloquear(); setTimeout(sonar, 150); });
  }

  function pintarContador(sinLeer) {
    if (contador) {
      contador.textContent = sinLeer > 99 ? "99+" : sinLeer;
      contador.hidden = sinLeer === 0;
    }
    // El título cambia al navegar (hx-boost): se toma el actual sin el número anterior.
    const titulo = document.title.replace(/^\(\d+\+?\)\s*/, "");
    document.title = sinLeer ? "(" + (sinLeer > 99 ? "99+" : sinLeer) + ") " + titulo : titulo;
    ultimoSinLeer = sinLeer;
  }
  let ultimoSinLeer = 0;
  document.addEventListener("htmx:afterSettle", function () { pintarContador(ultimoSinLeer); });

  function marcarVista(id) {
    return fetch("/notificaciones/" + id + "/vista/", {
      method: "POST", headers: { "X-CSRFToken": csrf() }, credentials: "same-origin",
    });
  }

  // Tarjeta de aviso con el color de su tipo. Las de prioridad alta llevan «Visto» y no se van solas.
  function tarjeta(aviso) {
    const marco = document.createElement("div");
    marco.className = "rounded-xl border-l-8 p-3 shadow-lg " + aviso.tarjeta + (aviso.alta ? " ring-2 ring-red-600" : "");
    const cabecera = document.createElement("div");
    cabecera.className = "flex items-center gap-2 text-sm";
    const etiqueta = document.createElement("span");
    etiqueta.className = "rounded-full px-2 py-0.5 font-semibold " + aviso.etiqueta;
    etiqueta.textContent = aviso.tipo;
    const hora = document.createElement("span");
    hora.className = "ml-auto text-slate-500";
    hora.textContent = aviso.hora;
    cabecera.append(etiqueta, hora);

    const enlace = document.createElement("a");
    enlace.href = aviso.url;
    enlace.className = "mt-1 block font-semibold text-slate-900";
    enlace.textContent = aviso.mensaje;

    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "mt-2 rounded-lg px-4 py-2 text-sm font-semibold " +
      (aviso.alta ? "bg-red-600 text-white" : "bg-white/70 text-slate-700");
    boton.textContent = aviso.alta ? "Visto" : "Cerrar";
    boton.addEventListener("click", function () {
      marco.remove();
      if (aviso.alta) {
        fijas.delete(aviso.id);
        marcarVista(aviso.id).then(consultar);
      }
    });
    marco.append(cabecera, enlace, boton);
    return marco;
  }

  async function consultar() {
    let datos;
    try {
      const respuesta = await fetch(urlEstado + "?despues=" + ultima, {
        headers: { "X-Consulta-Automatica": "1" }, credentials: "same-origin",
      });
      // Si la sesión se cerró, el servidor responde con la página de ingreso (no JSON): se deja de preguntar.
      if (!(respuesta.headers.get("content-type") || "").includes("application/json")) return;
      datos = await respuesta.json();
    } catch (e) {
      return; // sin red: se intenta en la próxima vuelta
    }
    pintarContador(datos.sin_leer);
    ultima = Math.max(ultima, datos.ultima);

    let hayQueSonar = false;
    datos.nuevas.forEach(function (aviso) {
      if (aviso.alta) { hayQueSonar = true; return; } // las altas se pintan abajo como fijas
      const marco = tarjeta(aviso);
      caja.appendChild(marco);
      setTimeout(function () { marco.remove(); }, DURACION_AVISO);
    });

    // Avisos fijos: se agregan los nuevos y se quitan los que ya se marcaron como vistos (aquí u otro equipo).
    const vigentes = new Set();
    datos.fijas.forEach(function (aviso) {
      vigentes.add(aviso.id);
      if (!fijas.has(aviso.id)) {
        const marco = tarjeta(aviso);
        fijas.set(aviso.id, marco);
        caja.prepend(marco);
      }
    });
    fijas.forEach(function (marco, id) {
      if (!vigentes.has(id)) { marco.remove(); fijas.delete(id); }
    });

    if (hayQueSonar) sonar();
  }

  consultar();
  setInterval(consultar, INTERVALO);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) consultar(); });
})();
