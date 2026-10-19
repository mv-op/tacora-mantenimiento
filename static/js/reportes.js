// Reporte de fallas del operador: borrador en el equipo, UUID por reporte y reenvío sin conexión.
// Todo se guarda por usuario, para que en un equipo compartido nadie vea ni envíe lo de otro.
(function () {
  "use strict";

  const cuerpo = document.body;
  const usuario = cuerpo.dataset.usuario;
  const urlEnviar = cuerpo.dataset.urlEnviar;
  if (!usuario || !urlEnviar) return;

  const CLAVE_BORRADOR = "mantenimiento." + usuario + ".borrador";
  const CLAVE_PENDIENTES = "mantenimiento." + usuario + ".pendientes";

  // Almacenamiento local (puede fallar en modo privado: entonces solo no se guarda).
  function leer(clave, porDefecto) {
    try { const valor = JSON.parse(localStorage.getItem(clave)); return valor === null ? porDefecto : valor; }
    catch (e) { return porDefecto; }
  }
  function guardar(clave, valor) {
    try { if (valor === null) localStorage.removeItem(clave); else localStorage.setItem(clave, JSON.stringify(valor)); }
    catch (e) { /* sin almacenamiento */ }
  }

  function nuevoUuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    // crypto.randomUUID solo existe con HTTPS; en http://IP-local se arma a mano (UUID v4).
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = Array.from(b, function (x) { return x.toString(16).padStart(2, "0"); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  }

  function csrf() {
    const meta = document.querySelector("meta[name=csrf-token]");
    return meta ? meta.content : "";
  }

  function avisar(texto) {
    const caja = document.getElementById("aviso-flotante");
    if (!caja) return;
    caja.textContent = texto;
    caja.hidden = false;
    clearTimeout(avisar.temporizador);
    avisar.temporizador = setTimeout(function () { caja.hidden = true; }, 6000);
  }

  // Envía un reporte. Devuelve {estado: "ok" | "invalido" | "sin_sesion" | "sin_red", ...}.
  async function enviar(reporte, automatico) {
    const datos = new FormData();
    ["uuid", "nodo", "descripcion", "criticidad"].forEach(function (campo) { datos.append(campo, reporte[campo] || ""); });
    const cabeceras = { "X-CSRFToken": csrf() };
    if (automatico) cabeceras["X-Consulta-Automatica"] = "1";
    let respuesta;
    try {
      respuesta = await fetch(urlEnviar, { method: "POST", body: datos, headers: cabeceras, credentials: "same-origin" });
    } catch (e) {
      return { estado: "sin_red" };
    }
    // Si la sesión se cerró, el servidor redirige a la página de ingreso (HTML, no JSON).
    if (!(respuesta.headers.get("content-type") || "").includes("application/json")) return { estado: "sin_sesion" };
    if (respuesta.status === 403) return { estado: "sin_sesion" };
    const json = await respuesta.json();
    if (respuesta.ok) return Object.assign({ estado: "ok" }, json);
    return { estado: "invalido", errores: json.errores || ["No se pudo enviar el reporte."] };
  }

  function agregarPendiente(reporte) {
    const pendientes = leer(CLAVE_PENDIENTES, []).filter(function (p) { return p.uuid !== reporte.uuid; });
    pendientes.push(reporte);
    guardar(CLAVE_PENDIENTES, pendientes);
  }

  function quitarPendiente(uuid) {
    guardar(CLAVE_PENDIENTES, leer(CLAVE_PENDIENTES, []).filter(function (p) { return p.uuid !== uuid; }));
  }

  // Reenvía los reportes que quedaron esperando conexión (mismo UUID: nunca se duplican).
  let reenviando = false;
  async function reenviarPendientes() {
    if (reenviando || !navigator.onLine) return;
    reenviando = true;
    try {
      for (const reporte of leer(CLAVE_PENDIENTES, [])) {
        const resultado = await enviar(reporte, true);
        if (resultado.estado === "ok") {
          quitarPendiente(reporte.uuid);
          avisar("✓ Se envió el reporte de " + reporte.ruta + " (#" + resultado.ticket + ").");
        } else if (resultado.estado === "invalido") {
          // Ya no se puede enviar tal cual (p. ej. el activo se desactivó): vuelve a ser borrador.
          quitarPendiente(reporte.uuid);
          guardar(CLAVE_BORRADOR, reporte);
          avisar("El reporte de " + reporte.ruta + " necesita revisión: " + resultado.errores.join(" "));
        } else {
          break; // sin red o sin sesión: se intenta más tarde
        }
      }
    } finally {
      reenviando = false;
      pintarPendientes();
    }
  }

  // Lista de pendientes en "Mis reportes".
  function pintarPendientes() {
    document.querySelectorAll("[data-pendientes]").forEach(function (caja) {
      const pendientes = leer(CLAVE_PENDIENTES, []);
      caja.replaceChildren();
      if (!pendientes.length) return;
      const marco = document.createElement("div");
      marco.className = "rounded-2xl bg-amber-100 p-4 text-amber-900";
      const titulo = document.createElement("div");
      titulo.className = "font-bold";
      titulo.textContent = "Esperando conexión (" + pendientes.length + "): se enviarán solos cuando vuelva la señal.";
      marco.appendChild(titulo);
      pendientes.forEach(function (p) {
        const fila = document.createElement("div");
        fila.className = "mt-2";
        fila.textContent = "• " + p.ruta + ": " + p.descripcion.slice(0, 60) + (p.descripcion.length > 60 ? "…" : "");
        marco.appendChild(fila);
      });
      caja.appendChild(marco);
    });
  }

  // Aviso de borrador sin terminar en la pantalla de máquinas.
  function pintarBannerBorrador(raiz) {
    raiz.querySelectorAll("[data-banner-borrador]").forEach(function (caja) {
      const borrador = leer(CLAVE_BORRADOR, null);
      caja.replaceChildren();
      if (!borrador || !borrador.nodo) return;
      const marco = document.createElement("div");
      marco.className = "mb-4 rounded-2xl bg-amber-100 p-4 text-amber-900";
      const texto = document.createElement("div");
      texto.className = "font-semibold";
      texto.textContent = "Tiene un reporte sin terminar en " + borrador.ruta + ".";
      const continuar = document.createElement("a");
      continuar.href = "/reportar/" + borrador.nodo + "/describir/";
      continuar.className = "mt-3 inline-block rounded-xl bg-amber-600 px-5 py-3 font-semibold text-white";
      continuar.textContent = "Continuar";
      const descartar = document.createElement("button");
      descartar.type = "button";
      descartar.className = "mt-3 ml-2 rounded-xl bg-white px-5 py-3 font-semibold";
      descartar.textContent = "Descartar";
      descartar.addEventListener("click", function () { guardar(CLAVE_BORRADOR, null); caja.replaceChildren(); });
      marco.append(texto, continuar, descartar);
      caja.appendChild(marco);
    });
  }

  // Formulario "Describa la falla".
  function iniciarFormulario(formulario) {
    if (formulario.dataset.iniciado) return;
    formulario.dataset.iniciado = "1";

    const nodo = formulario.dataset.nodo;
    const minimo = Number(formulario.dataset.minimo);
    const texto = formulario.querySelector("[name=descripcion]");
    const contador = formulario.querySelector("[data-contador]");
    const errores = formulario.querySelector("[data-errores]");
    const boton = formulario.querySelector("[type=submit]");

    // Se retoma el borrador si es del mismo activo; si no, empieza uno nuevo con su UUID.
    let borrador = leer(CLAVE_BORRADOR, null);
    if (!borrador || String(borrador.nodo) !== String(nodo)) {
      borrador = { uuid: nuevoUuid(), nodo: nodo, ruta: formulario.dataset.ruta, descripcion: "", criticidad: "" };
      guardar(CLAVE_BORRADOR, borrador);
    }
    texto.value = borrador.descripcion || "";
    if (borrador.criticidad) {
      const opcion = formulario.querySelector("[name=criticidad][value='" + borrador.criticidad + "']");
      if (opcion) opcion.checked = true;
    }

    function actualizarContador() {
      const largo = texto.value.trim().length;
      contador.textContent = largo;
      contador.className = largo >= minimo ? "font-semibold text-green-700" : "";
    }
    function guardarBorrador() {
      const elegida = formulario.querySelector("[name=criticidad]:checked");
      borrador.descripcion = texto.value;
      borrador.criticidad = elegida ? elegida.value : "";
      guardar(CLAVE_BORRADOR, borrador);
    }
    function mostrarErrores(lista) {
      errores.replaceChildren();
      lista.forEach(function (mensaje) {
        const linea = document.createElement("div");
        linea.textContent = mensaje;
        errores.appendChild(linea);
      });
      errores.hidden = !lista.length;
      if (lista.length) errores.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    function liberarBoton() {
      boton.disabled = false;
      boton.textContent = boton.dataset.textoOriginal || "Enviar reporte";
      delete boton.dataset.enviando;
    }

    actualizarContador();
    texto.addEventListener("input", function () { actualizarContador(); guardarBorrador(); });
    formulario.addEventListener("change", guardarBorrador);

    formulario.querySelector("[data-descartar]").addEventListener("click", function () {
      guardar(CLAVE_BORRADOR, null);
      window.location.href = "/reportar/" + nodo + "/";
    });

    formulario.addEventListener("submit", async function (evento) {
      evento.preventDefault();
      if (boton.dataset.enviando) return; // doble toque: ya se está enviando
      guardarBorrador();
      const faltantes = [];
      if (texto.value.trim().length < minimo) faltantes.push("Describa la falla con al menos " + minimo + " caracteres.");
      if (!borrador.criticidad) faltantes.push("Elija la criticidad.");
      if (faltantes.length) {
        mostrarErrores(faltantes);
        evento.stopPropagation(); // así el bloqueo general no deja el botón en "Enviando…"
        return;
      }
      mostrarErrores([]);
      const reporte = Object.assign({ guardado_en: new Date().toISOString() }, borrador);
      const resultado = await enviar(reporte, false);

      if (resultado.estado === "ok") {
        guardar(CLAVE_BORRADOR, null);
        window.location.href = resultado.url + "?enviado=1";
      } else if (resultado.estado === "invalido") {
        mostrarErrores(resultado.errores);
        liberarBoton();
      } else {
        // Sin red o sin sesión: queda guardado y se envía solo después, con el mismo UUID.
        agregarPendiente(reporte);
        guardar(CLAVE_BORRADOR, null);
        if (resultado.estado === "sin_sesion") {
          window.location.href = "/ingresar/?next=/reportes/";
          return;
        }
        // Sin red no se puede abrir otra página: se avisa aquí mismo.
        const aviso = document.createElement("div");
        aviso.className = "rounded-2xl bg-amber-100 p-5 text-center text-amber-900";
        aviso.innerHTML = '<div class="text-xl font-bold">Sin conexión</div>' +
          '<div class="mt-2">Su reporte quedó guardado en este equipo y se enviará solo cuando vuelva la señal. ' +
          "No lo vuelva a escribir.</div>";
        formulario.replaceChildren(aviso);
      }
    });
  }

  function iniciar(raiz) {
    raiz.querySelectorAll("form[data-reporte]").forEach(iniciarFormulario);
    pintarBannerBorrador(raiz);
    pintarPendientes();
  }

  // Se inicia al cargar la página y cada vez que HTMX cambia un pedazo (hx-boost).
  document.addEventListener("DOMContentLoaded", function () {
    iniciar(document);
    reenviarPendientes();
  });
  document.addEventListener("htmx:load", function (e) { iniciar(e.target); });
  window.addEventListener("online", reenviarPendientes);
  setInterval(function () { if (leer(CLAVE_PENDIENTES, []).length) reenviarPendientes(); }, 30000);
})();
