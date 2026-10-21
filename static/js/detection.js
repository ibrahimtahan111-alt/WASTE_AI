// detection.js
document.addEventListener("DOMContentLoaded", function () {
  // ----------------------------
  // Spinner Overlay
  // ----------------------------
  const spinner = document.createElement("div");
  spinner.id = "loading-spinner";
  spinner.style.cssText = `
    display:none; position:fixed; top:0; left:0; width:100%; height:100%;
    background:rgba(255,255,255,0.8); z-index:2000;
    justify-content:center; align-items:center; flex-direction:column;
  `;
  spinner.innerHTML = `
    <div class="spinner-border text-success" style="width:3rem;height:3rem;" role="status"></div>
    <p class="mt-3 mb-0 fw-semibold">Detecting waste…</p>
    <p class="text-muted small">This may take a few seconds</p>
  `;
  document.body.appendChild(spinner);

  function showSpinner() {
    spinner.style.display = "flex";
  }
  function hideSpinner() {
    spinner.style.display = "none";
  }

  // ----------------------------
  // Elements
  // ----------------------------
  const uploadArea = document.querySelector(".upload-area");
  const fileInput = document.getElementById("image-input");
  const previewContainer = document.getElementById("preview-container");
  const previewImg = document.getElementById("preview-img");
  const form = document.getElementById("detection-form");
  const resultsDiv = document.getElementById("detection-results");
  const previewDiv = document.getElementById("detection-preview");

  // ----------------------------
  // Helpers
  // ----------------------------
  function showPreview(file) {
    if (file && file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        previewImg.src = e.target.result;
        previewContainer.style.display = "block";
      };
      reader.readAsDataURL(file);
    }
  }
  function resetPreview() {
    fileInput.value = "";
    previewImg.src = "";
    previewContainer.style.display = "none";
  }
 function normalizeCategory(cat) {
  if (!cat) return "unknown";
  return cat.trim().toLowerCase().replace(/[_\s]+/g, "-"); 
  // ensures "Non Recyclable", "non_recyclable" → "non-recyclable"
}

function getBadge(category) {
  switch ((category || "").toLowerCase().replace(/[_\s]+/g, "-")) {
    case "recyclable":
      return `<span class="badge bg-success">♻️ Recyclable</span>`;
    case "hazardous":
      return `<span class="badge bg-danger">☣️ Hazardous</span>`;
    case "organic":
      return `<span class="badge bg-success bg-opacity-75">🌿 Organic</span>`;
    case "non-recyclable":
      return `<span class="badge bg-warning text-dark">🚫 Non-Recyclable</span>`;
    default:
      return `<span class="badge bg-secondary">❓ Unknown</span>`;
  }
}


  function getConfidenceBar(conf) {
    const value = Number(conf) || 0;
    const pct = Math.round(value * 1000) / 10;
    let color = value >= 0.8 ? "bg-success" : value >= 0.5 ? "bg-warning" : "bg-danger";
    return `
      <div class="d-flex align-items-center gap-2">
        <div class="progress flex-grow-1" style="height:8px;max-width:140px;">
          <div class="progress-bar ${color}" role="progressbar"
               style="width:${Math.min(pct, 100)}%"
               aria-valuenow="${value}" aria-valuemin="0" aria-valuemax="1"></div>
        </div>
        <small class="text-muted">${pct}%</small>
      </div>`;
  }

  // ----------------------------
  // File Input + Drag Drop
  // ----------------------------
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) showPreview(fileInput.files[0]);
  });
  uploadArea.addEventListener("dragover", (e) => {
    e.preventDefault(); uploadArea.classList.add("dragover");
  });
  uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("dragover"));
  uploadArea.addEventListener("drop", (e) => {
    e.preventDefault(); uploadArea.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      fileInput.files = e.dataTransfer.files;
      showPreview(e.dataTransfer.files[0]);
    }
  });

  // ----------------------------
  // Submit Detection
  // ----------------------------
  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();

      if (!fileInput.files || fileInput.files.length === 0) {
        resultsDiv.innerHTML = `<div class="alert alert-warning mb-0">Please choose an image first.</div>`;
        return;
      }

      const selected = fileInput.files[0];
      if (!selected.type.startsWith("image/")) {
        resultsDiv.innerHTML = `<div class="alert alert-warning mb-0">Please upload an image file (JPG, PNG, WEBP, or BMP).</div>`;
        return;
      }
      if (selected.size > 10 * 1024 * 1024) {
        resultsDiv.innerHTML = `<div class="alert alert-warning mb-0">Image is too large. Max size is 10 MB.</div>`;
        return;
      }

      const formData = new FormData(form);

      resultsDiv.innerHTML = "";
      previewDiv.innerHTML = "";
      showSpinner();

      try {
        const response = await fetch("/detect", { method: "POST", body: formData });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.error || `Server error: ${response.status}`);
        }
        if (data.error) {
          throw new Error(data.error);
        }

        // Preview Images
        previewDiv.innerHTML = `
          <h5>📸 Detection Preview</h5>
          <div class="d-flex flex-wrap gap-3 justify-content-center">
            <div>
              <p class="text-muted">Original</p>
              <img src="${data.image}" class="img-fluid shadow rounded mb-3" style="max-width:250px;">
            </div>
            <div>
              <p class="text-muted">With Detections</p>
              <img src="${data.annotated}" class="img-fluid shadow rounded mb-3" style="max-width:250px;">
            </div>
          </div>`;

        // Results
        resultsDiv.innerHTML = "<h4>Detections</h4>";
        if (!data.detections || data.detections.length === 0) {
          resultsDiv.innerHTML += `
            <div class="alert alert-info">
              <strong>No waste items detected.</strong>
              <div class="small mt-1">Try a clearer photo, better lighting, or move closer to the object.</div>
            </div>`;
        } else {
          resultsDiv.innerHTML += `<div id="detection-cards"></div>`;
          const cardsContainer = document.getElementById("detection-cards");

          for (const d of data.detections) {
            const params = new URLSearchParams({ label: d.label, category: d.category, confidence: d.confidence ?? 0 });
            if (navigator.geolocation) {
              try {
                const pos = await new Promise((res, rej) =>
                  navigator.geolocation.getCurrentPosition(res, rej, { timeout: 5000 })
                );
                params.set("lat", pos.coords.latitude);
                params.set("lng", pos.coords.longitude);
              } catch (_) {}
            }

            let suggestion = null;
            try {
              const sRes = await fetch(`/api/suggest?${params.toString()}`);
              suggestion = await sRes.json();
            } catch (e) { console.error("Suggestion fetch failed:", e); }

            const card = document.createElement("div");
            card.className = "card my-3 shadow-sm";
            card.innerHTML = `
              <div class="card-body">
                <h5 class="card-title mb-2">${d.label} ${getBadge(d.category)}</h5>
                <div class="mb-2">${getConfidenceBar(d.confidence)}</div>
                <p class="small text-muted">${suggestion?.notes || d.advice || ""}</p>

                <div class="row g-3">
                  <div class="col-md-6">
                    <h6>Prep</h6>
                    <ul>${(suggestion?.prep || []).map(p => `<li>${p}</li>`).join("") || "<li class='text-muted'>No prep tips</li>"}</ul>
                    <h6>Checklist</h6>
                    <ul>${(suggestion?.checklist || []).map(c => `<li>${c}</li>`).join("") || "<li class='text-muted'>No checklist items</li>"}</ul>
                  </div>
                  <div class="col-md-6">
                    <h6>Reuse Ideas</h6>
                    <ul>${(suggestion?.reuse || []).map(r => `<li>${r}</li>`).join("") || "<li class='text-muted'>No reuse ideas</li>"}</ul>
                    <h6>Warnings</h6>
                    <ul>${(suggestion?.warnings || []).map(w => `<li>${w}</li>`).join("") || "<li class='text-muted'>None</li>"}</ul>
                  </div>
                </div>

                <div class="mt-3">
                  <h6>Nearest Facility</h6>
                  ${suggestion?.nearest
                    ? `<p><strong>${suggestion.nearest.name}</strong><br>
                       ${suggestion.nearest.address || ""}<br>
                       ${suggestion.nearest.distance_km} km away</p>
                       <a href="https://www.google.com/maps/dir/?api=1&destination=${suggestion.nearest.lat},${suggestion.nearest.lng}"
                          target="_blank" class="btn btn-sm btn-outline-success">🚗 Route</a>`
                    : `<p class="text-muted small">No facility found nearby</p>`}
                </div>
              </div>`;
            cardsContainer.appendChild(card);
          }
        }

        // History
        if (data.history && data.history.length > 1) {
          resultsDiv.innerHTML += "<h5 class='mt-4'>🕓 Recent Detections</h5>";
          data.history.slice(0, -1).forEach((h) => {
            resultsDiv.innerHTML += `
              <div class="card mt-2 p-2">
                <img src="${h.annotated}" class="img-fluid rounded" style="max-width:180px;">
                <p class="mb-1"><small>${h.detections.length} objects</small></p>
              </div>`;
          });
        }

        resetPreview();
      } catch (err) {
        resultsDiv.innerHTML = `<div class="alert alert-danger mb-0">❌ Detection failed: ${err.message}</div>`;
        console.error("Detection error:", err);
      } finally {
        hideSpinner();
      }
    });
  }

  // ----------------------------
  // Webcam Detection
  // ----------------------------
  const startBtn = document.getElementById("start-webcam");
  const stopBtn = document.getElementById("stop-webcam");
  const resumeBtn = document.getElementById("resume-webcam");
  const restartBtn = document.getElementById("restart-webcam");
  const feedDiv = document.getElementById("webcam-feed");
  const snapshotControls = document.getElementById("snapshot-controls");
  const list = document.getElementById("webcam-detections");
  const statusDot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");
  const thresholdRange = document.getElementById("threshold-range");
  const thresholdValue = document.getElementById("threshold-value");
  const clearHistoryBtn = document.getElementById("clear-history");

  let interval = null;
  let lastImage = null;
  let fetchingFrame = false;
  let cameraActive = false;

  function setStatus(live) {
    if (!statusDot || !statusText) return;
    statusDot.className = live
      ? "rounded-circle bg-success d-inline-block"
      : "rounded-circle bg-danger d-inline-block";
    statusText.textContent = live ? "Live" : "Paused";
  }

  function setCameraButtons({ starting = false, live = false, paused = false } = {}) {
    startBtn?.classList.toggle("d-none", starting || live || paused);
    stopBtn?.classList.toggle("d-none", !(live || paused || starting));
    resumeBtn?.classList.toggle("d-none", !paused);
    restartBtn?.classList.toggle("d-none", !paused);
  }

  function showCameraError(message) {
    if (feedDiv) {
      feedDiv.innerHTML = `<div class="alert alert-danger mb-0 text-start">📷 ${message}</div>`;
    }
    setStatus(false);
    cameraActive = false;
    setCameraButtons({});
  }

  function addDetection(d) {
    if (!list) return;
    const confPct = Math.round((Number(d.confidence) || 0) * 1000) / 10;
    const li = document.createElement("li");
    li.className = "list-group-item d-flex justify-content-between align-items-center";
    li.innerHTML = `<div><strong>${d.label}</strong> (${confPct}%)<br>
                    <small class="text-muted">⏱ ${d.timestamp || ""}</small></div>
                    ${getBadge(d.category)}`;
    if (list.children.length >= 30) list.removeChild(list.lastChild);
    list.prepend(li);
  }

  function showSnapshotButton() {
    if (!snapshotControls) return;
    snapshotControls.innerHTML = "";
    const btn = document.createElement("button");
    btn.className = "btn btn-sm btn-outline-secondary";
    btn.textContent = "📷 Save Snapshot";
    btn.onclick = () => {
      if (lastImage) {
        const a = document.createElement("a");
        a.href = "data:image/jpeg;base64," + lastImage;
        a.download = "snapshot.jpg";
        a.click();
      }
    };
    snapshotControls.appendChild(btn);
  }

  function clearSnapshotButton() {
    if (snapshotControls) snapshotControls.innerHTML = "";
  }

  function handleDetections(detections) {
    const recyclable = detections.some((d) => d.suggestion === true);
    const toastNode = document.getElementById("recycleToast");
    if (recyclable && toastNode) {
      const toastEl = new bootstrap.Toast(toastNode);
      toastEl.show();
    }
  }

  function stopCameraLoop() {
    if (interval) {
      clearInterval(interval);
      interval = null;
    }
    fetchingFrame = false;
  }

  async function closeCamera(message) {
    stopCameraLoop();
    cameraActive = false;
    try {
      await fetch("/stop_webcam", { method: "POST" });
    } catch (_) {}
    if (feedDiv) {
      feedDiv.innerHTML = `<p class="text-muted">${message || "Camera stopped."}</p>`;
    }
    clearSnapshotButton();
    setStatus(false);
    setCameraButtons({});
  }

  async function startCameraLoop(statusMessage) {
    stopCameraLoop();
    cameraActive = true;
    setCameraButtons({ starting: true });
    if (feedDiv) feedDiv.innerHTML = `<p>${statusMessage || "🌀 Starting camera..."}</p>`;
    clearSnapshotButton();
    setStatus(true);

    try {
      const res = await fetch("/resume_webcam", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || "Could not start webcam.");
      }
      setCameraButtons({ live: true });
      interval = setInterval(fetchFrame, 500);
      fetchFrame();
    } catch (err) {
      console.error("Start webcam failed:", err);
      showCameraError(err.message || "Could not start webcam.");
    }
  }

  function fetchFrame() {
    if (fetchingFrame || !cameraActive) return;
    fetchingFrame = true;

    fetch("/webcam_frame")
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (res.status === 401 || res.status === 302) {
          throw new Error("Session expired. Please log in again.");
        }
        if (!res.ok || data.error) {
          throw new Error(data.error || `Camera error (${res.status})`);
        }

        if (data.paused && !data.image) {
          return;
        }

        if (data.image && feedDiv) {
          lastImage = data.image;
          feedDiv.innerHTML = `<img src="data:image/jpeg;base64,${data.image}" class="img-fluid rounded shadow" alt="Live detection">`;
          setStatus(!data.paused);
        }

        if (data.detections && data.detections.length > 0 && data.paused) {
          stopCameraLoop();
          setCameraButtons({ paused: true });
          setStatus(false);
          data.detections.forEach((d) => addDetection(d));
          showSnapshotButton();
          handleDetections(data.detections);
        }
      })
      .catch((err) => {
        console.error("Webcam error:", err);
        stopCameraLoop();
        showCameraError(err.message || "Webcam failed.");
      })
      .finally(() => {
        fetchingFrame = false;
      });
  }

  startBtn?.addEventListener("click", () => {
    startCameraLoop("🌀 Starting camera...");
  });

  stopBtn?.addEventListener("click", () => {
    closeCamera("Camera stopped. Click Start to open it again.");
  });

  resumeBtn?.addEventListener("click", () => {
    startCameraLoop("🌀 Resuming camera...");
  });

  restartBtn?.addEventListener("click", () => {
    if (list) list.innerHTML = "";
    startCameraLoop("🌀 Restarting camera...");
  });

  clearHistoryBtn?.addEventListener("click", () => {
    if (list) list.innerHTML = "";
  });

  thresholdRange?.addEventListener("input", () => {
    const value = parseFloat(thresholdRange.value).toFixed(2);
    if (thresholdValue) thresholdValue.textContent = value;
    fetch("/set_threshold", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threshold: value }),
    });
  });

  window.addEventListener("beforeunload", () => {
    stopCameraLoop();
    cameraActive = false;
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/stop_webcam");
    }
  });
  // ----------------------------
  // Map Modal
  // ----------------------------
  const openMapLink = document.getElementById("openMap");
  if (openMapLink) {
    openMapLink.addEventListener("click", function (e) {
      e.preventDefault();
      const mapModalEl = document.getElementById("mapModal");
      if (!mapModalEl) return;
      const mapModal = new bootstrap.Modal(mapModalEl);
      mapModal.show();
      initMap();
    });
  }

  function initMap() {
    const mapEl = document.getElementById("map");
    if (!mapEl || !window.google || !google.maps) return;

    const defaultCenter = { lat: 33.8938, lng: 35.5018 };
    const map = new google.maps.Map(mapEl, { center: defaultCenter, zoom: 11 });
    const info = new google.maps.InfoWindow();

    const placeUser = (pos) => {
      map.setCenter(pos);
      map.setZoom(12);
      new google.maps.Marker({ position: pos, map, title: "You are here" });
    };

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => placeUser({ lat: position.coords.latitude, lng: position.coords.longitude }),
        () => placeUser(defaultCenter),
        { timeout: 5000 }
      );
    }

    fetch("/api/facilities")
      .then((r) => r.json())
      .then((list) => {
        (list || []).forEach((f) => {
          if (f.lat == null || f.lng == null) return;
          const marker = new google.maps.Marker({
            position: { lat: Number(f.lat), lng: Number(f.lng) },
            map,
            title: f.name,
          });
          marker.addListener("click", () => {
            info.setContent(`
              <div style="max-width:240px">
                <strong>${f.name}</strong><br>
                <small>${f.address || f.city || ""}</small><br>
                <small>Accepts: ${f.accepts || "—"}</small>
                ${f.phone ? `<br><small>${f.phone}</small>` : ""}
              </div>`);
            info.open({ anchor: marker, map });
          });
        });
      })
      .catch((err) => console.error("Facilities map load failed:", err));
  }
});
