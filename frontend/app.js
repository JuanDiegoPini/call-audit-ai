const API_URL = window.CALL_AUDIT_API_URL || "http://127.0.0.1:8000";
const CHUNK_INTERVAL_MS = 30_000;
const CHUNK_DURATION_MS = 25_000;

let currentCallId = null;
let active = false;
let microphoneStream = null;
let customerStream = null;
let microphoneInterval = null;
let customerInterval = null;
let microphoneRecorder = null;
let customerRecorder = null;
const pendingUploads = new Set();

async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // The status code remains the safe fallback when no JSON body exists.
    }
    throw new Error(message);
  }
  return response.json();
}

async function iniciarLlamadaCompleta() {
  const agentReference = document.getElementById("referenciaAgente").value.trim();
  const agentName = document.getElementById("nombreAgente").value.trim();
  const classification = document.getElementById("clasificacionAgente").value;
  if (!agentReference) {
    alert("Ingresa una referencia ficticia para el agente.");
    return;
  }

  bloquearInicio();
  try {
    setText("estadoLlamada", "Creando llamada...");
    const call = await api("/calls", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_reference: agentReference,
        agent_name: agentName || null,
        agent_classification: classification,
      }),
    });
    currentCallId = call.id;
    setText("idLlamada", call.id);

    microphoneStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
    customerStream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true,
    });
    if (customerStream.getAudioTracks().length === 0) {
      throw new Error("La fuente compartida no contiene una pista de audio.");
    }

    active = true;
    setText("estadoLlamada", "IN_PROGRESS");
    setText("estadoMic", "Activo como AGENT");
    setText("estadoCliente", "Activo como CUSTOMER");
    setText("reporteFinal", "Captura local activa; se enviarán fragmentos periódicos.");
    recordChunk(microphoneStream, "AGENT");
    recordChunk(customerStream, "CUSTOMER");
    microphoneInterval = setInterval(
      () => recordChunk(microphoneStream, "AGENT"),
      CHUNK_INTERVAL_MS,
    );
    customerInterval = setInterval(
      () => recordChunk(customerStream, "CUSTOMER"),
      CHUNK_INTERVAL_MS,
    );
    document.getElementById("btnDetener").disabled = false;
  } catch (error) {
    console.error(error);
    detenerCapturaLocal();
    desbloquearInicio();
    setText("estadoLlamada", "Error de inicio");
    alert(error.message);
  }
}

function recordChunk(stream, source) {
  if (!active || !stream || !currentCallId || !stream.getAudioTracks().length) return;
  const recorder = new MediaRecorder(new MediaStream(stream.getAudioTracks()), {
    mimeType: "audio/webm",
  });
  const chunks = [];
  let resolveCompletion;
  recorder.completion = new Promise((resolve) => {
    resolveCompletion = resolve;
  });
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  recorder.onstop = () => {
    const blob = new Blob(chunks, { type: "audio/webm" });
    if (blob.size > 0 && currentCallId) {
      const upload = uploadAudio(blob, source);
      trackUpload(upload);
      upload.finally(resolveCompletion);
    } else {
      resolveCompletion();
    }
  };
  recorder.start();
  if (source === "AGENT") microphoneRecorder = recorder;
  else customerRecorder = recorder;
  setTimeout(() => {
    if (recorder.state === "recording") recorder.stop();
  }, CHUNK_DURATION_MS);
}

function trackUpload(promise) {
  pendingUploads.add(promise);
  promise
    .catch((error) => {
      console.error(error);
      setText("reporteFinal", `No se pudo procesar un fragmento: ${error.message}`);
    })
    .finally(() => pendingUploads.delete(promise));
}

async function uploadAudio(blob, source) {
  const data = new FormData();
  data.append("source", source);
  data.append("audio", blob, `${source.toLowerCase()}-${Date.now()}.webm`);
  await api(`/calls/${currentCallId}/segments`, { method: "POST", body: data });
  await cargarSegmentos();
}

async function cargarSegmentos() {
  if (!currentCallId) return;
  const segments = await api(`/calls/${currentCallId}/segments`);
  setText(
    "segmentos",
    segments.length
      ? segments.map((segment) => `${segment.source}: ${segment.transcript}`).join("\n\n")
      : "No hay segmentos todavía.",
  );
}

async function detenerYAnalizar() {
  if (!currentCallId) return;
  document.getElementById("btnDetener").disabled = true;
  setText("reporteFinal", "Esperando los últimos fragmentos...");
  const recorderCompletions = [microphoneRecorder, customerRecorder]
    .filter(Boolean)
    .map((recorder) => recorder.completion);
  detenerCapturaLocal();
  await Promise.allSettled(recorderCompletions);
  await Promise.allSettled([...pendingUploads]);
  active = false;
  try {
    const call = await api(`/calls/${currentCallId}/finalize`, { method: "POST" });
    setText("estadoLlamada", call.status);
    setText("reporteFinal", JSON.stringify(JSON.parse(call.analysis_json), null, 2));
    await cargarSegmentos();
  } catch (error) {
    console.error(error);
    setText("reporteFinal", error.message);
  } finally {
    desbloquearInicio();
  }
}

function detenerCapturaLocal() {
  clearInterval(microphoneInterval);
  clearInterval(customerInterval);
  microphoneInterval = null;
  customerInterval = null;
  for (const recorder of [microphoneRecorder, customerRecorder]) {
    if (recorder?.state === "recording") recorder.stop();
  }
  for (const stream of [microphoneStream, customerStream]) {
    stream?.getTracks().forEach((track) => track.stop());
  }
  microphoneStream = null;
  customerStream = null;
  setText("estadoMic", "Detenido");
  setText("estadoCliente", "Detenido");
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function bloquearInicio() {
  document.getElementById("btnIniciar").disabled = true;
}

function desbloquearInicio() {
  document.getElementById("btnIniciar").disabled = false;
  document.getElementById("btnDetener").disabled = true;
}

window.iniciarLlamadaCompleta = iniciarLlamadaCompleta;
window.detenerYAnalizar = detenerYAnalizar;
