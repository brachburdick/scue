/**
 * SCUE Frontend — Upload, analysis, playback, and UI coordination.
 */

let renderer = null;
let audioEl = null;
let currentTrackId = null;
let analysisResult = null;

// --- DOM refs ---
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const status = document.getElementById("status");
const analyzeSection = document.getElementById("analyze-section");
const resultsSection = document.getElementById("results-section");
const bpmDisplay = document.getElementById("bpm");
const durationDisplay = document.getElementById("duration-display");
const sectionCountDisplay = document.getElementById("section-count");
const canvas = document.getElementById("waveform-canvas");
const playBtn = document.getElementById("play-btn");
const stopBtn = document.getElementById("stop-btn");
const timeDisplay = document.getElementById("time-display");
const zoomInBtn = document.getElementById("zoom-in");
const zoomOutBtn = document.getElementById("zoom-out");
const jsonPanel = document.getElementById("json-panel");
const jsonToggle = document.getElementById("json-toggle");
const jsonContent = document.getElementById("json-content");
const sectionsList = document.getElementById("sections-list");

// --- Init ---
audioEl = document.getElementById("audio-player");
renderer = new RGBWaveformRenderer(canvas, audioEl);

// --- Upload handling ---
dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

async function handleFile(file) {
  const ext = file.name.split(".").pop().toLowerCase();
  if (!["wav", "mp3"].includes(ext)) {
    showStatus("Please upload a .wav or .mp3 file", "error");
    return;
  }

  showStatus(`Uploading ${file.name}...`, "info");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const uploadRes = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });

    if (!uploadRes.ok) {
      const err = await uploadRes.json();
      showStatus(`Upload failed: ${err.detail}`, "error");
      return;
    }

    const { track_id } = await uploadRes.json();
    currentTrackId = track_id;

    showStatus(`Analyzing ${file.name}... This may take 30-90 seconds.`, "info");
    analyzeSection.style.display = "block";
    resultsSection.style.display = "none";

    // Set audio source immediately so user can listen while waiting
    audioEl.src = `/api/audio/${track_id}`;

    const analyzeRes = await fetch(`/api/analyze/${track_id}`, {
      method: "POST",
    });

    if (!analyzeRes.ok) {
      const err = await analyzeRes.json();
      showStatus(`Analysis failed: ${err.detail}`, "error");
      return;
    }

    analysisResult = await analyzeRes.json();
    displayResults(analysisResult);
    showStatus("Analysis complete!", "success");
  } catch (e) {
    showStatus(`Error: ${e.message}`, "error");
  }
}

function displayResults(result) {
  analyzeSection.style.display = "none";
  resultsSection.style.display = "block";

  // Header stats
  bpmDisplay.textContent = Math.round(result.bpm);
  durationDisplay.textContent = formatTime(result.waveform.duration);
  sectionCountDisplay.textContent = result.sections.length;

  // Waveform
  renderer.setData(result.waveform, result.sections);

  // Sections list
  renderSectionsList(result.sections);

  // JSON panel
  jsonContent.textContent = JSON.stringify(result, null, 2);
}

function renderSectionsList(sections) {
  sectionsList.innerHTML = "";
  const colors = {
    intro: "#4682B4",
    verse: "#20B2AA",
    build: "#FF8C00",
    drop: "#DC143C",
    fakeout: "#9370DB",
    breakdown: "#3CB371",
    outro: "#708090",
  };

  for (const sec of sections) {
    const el = document.createElement("div");
    el.className = "section-item";
    el.innerHTML = `
      <span class="section-dot" style="background: ${colors[sec.label] || "#888"}"></span>
      <span class="section-label">${sec.label.toUpperCase()}</span>
      <span class="section-time">${formatTime(sec.start)} - ${formatTime(sec.end)}</span>
      <span class="section-conf" title="Confidence">${Math.round(sec.confidence * 100)}%</span>
    `;
    el.addEventListener("click", () => {
      audioEl.currentTime = sec.start;
      renderer.render();
    });
    sectionsList.appendChild(el);
  }
}

// --- Playback controls ---
playBtn.addEventListener("click", () => {
  if (audioEl.paused) {
    audioEl.play();
    renderer.startPlayback();
    playBtn.textContent = "Pause";
  } else {
    audioEl.pause();
    renderer.stopPlayback();
    playBtn.textContent = "Play";
  }
});

stopBtn.addEventListener("click", () => {
  audioEl.pause();
  audioEl.currentTime = 0;
  renderer.stopPlayback();
  renderer.scrollOffset = 0;
  renderer.render();
  playBtn.textContent = "Play";
});

audioEl.addEventListener("ended", () => {
  renderer.stopPlayback();
  playBtn.textContent = "Play";
});

audioEl.addEventListener("timeupdate", () => {
  timeDisplay.textContent = `${formatTime(audioEl.currentTime)} / ${formatTime(audioEl.duration || 0)}`;
});

// --- Zoom ---
zoomInBtn.addEventListener("click", () => renderer.setZoom(renderer.pixelsPerSecond * 1.3));
zoomOutBtn.addEventListener("click", () => renderer.setZoom(renderer.pixelsPerSecond / 1.3));

// --- JSON toggle ---
jsonToggle.addEventListener("click", () => {
  jsonPanel.classList.toggle("collapsed");
  jsonToggle.textContent = jsonPanel.classList.contains("collapsed") ? "Show JSON" : "Hide JSON";
});

// --- Helpers ---
function formatTime(sec) {
  if (!sec || isNaN(sec)) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function showStatus(msg, type) {
  status.textContent = msg;
  status.className = `status ${type}`;
  status.style.display = "block";
  if (type === "success") {
    setTimeout(() => (status.style.display = "none"), 3000);
  }
}
