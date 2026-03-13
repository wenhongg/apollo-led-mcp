let brightnessTimer = null;
let selectedEffect = "scroll_horizontal";

// --- API helper ---

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return resp.json();
}

// --- Toast notifications ---

function toast(message, type = "success") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2500);
}

// --- Status ---

async function checkStatus() {
  try {
    const status = await api("/api/status");
    const bar = document.getElementById("status-bar");
    if (status.connected) {
      bar.textContent = status.wled_host;
      bar.className = "status connected";
    } else {
      bar.textContent = "Disconnected";
      bar.className = "status disconnected";
    }
    if (status.wled_state) {
      const bri = status.wled_state.bri;
      document.getElementById("brightness").value = bri;
      document.getElementById("bri-val").textContent = bri;
    }
  } catch {
    const bar = document.getElementById("status-bar");
    bar.textContent = "Offline";
    bar.className = "status disconnected";
  }
}

// --- Tabs ---

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.panel).classList.add("active");
  });
});

// --- Effect buttons ---

document.querySelectorAll(".effect-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".effect-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    selectedEffect = btn.dataset.effect;
  });
});

// --- Text display ---

async function sendText() {
  const text = document.getElementById("text-input").value;
  if (!text) return;
  const btn = event.target;
  btn.classList.add("loading");
  btn.disabled = true;
  try {
    await api("/api/display/text", {
      method: "POST",
      body: JSON.stringify({
        text,
        color: hexToRgb(document.getElementById("text-color").value),
        bg_color: hexToRgb(document.getElementById("bg-color").value),
        font_size: parseInt(document.getElementById("font-size").value),
      }),
    });
    toast("Text displayed");
    refreshPreview();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

// --- Animated text ---

async function sendAnimatedText() {
  const text = document.getElementById("anim-text").value;
  if (!text) return;
  const btn = event.target;
  btn.classList.add("loading");
  btn.disabled = true;
  try {
    await api("/api/display/animated-text", {
      method: "POST",
      body: JSON.stringify({
        text,
        effect: selectedEffect,
        color: hexToRgb(document.getElementById("anim-color").value),
        bg_color: hexToRgb(document.getElementById("anim-bg").value),
        font_size: parseInt(document.getElementById("anim-size").value),
        speed: parseInt(document.getElementById("anim-speed").value),
      }),
    });
    toast(`${selectedEffect} effect applied`);
    refreshPreview();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

// --- File uploads ---

function setupFileDrop(inputId, dropId) {
  const input = document.getElementById(inputId);
  const drop = document.getElementById(dropId);

  input.addEventListener("change", () => {
    if (input.files.length) {
      drop.classList.add("has-file");
      const existing = drop.querySelector(".file-name");
      if (existing) existing.remove();
      const name = document.createElement("span");
      name.className = "file-name";
      name.textContent = input.files[0].name;
      drop.appendChild(name);
    }
  });

  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("dragover");
  });

  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));

  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      input.dispatchEvent(new Event("change"));
    }
  });
}

setupFileDrop("gif-input", "gif-drop");
setupFileDrop("image-input", "image-drop");
setupFileDrop("video-input", "video-drop");

async function uploadFile(type) {
  const input = document.getElementById(`${type}-input`);
  if (!input.files.length) { toast("Select a file first", "error"); return; }

  const btn = event.target;
  btn.classList.add("loading");
  btn.disabled = true;

  const formData = new FormData();
  formData.append("file", input.files[0]);

  try {
    const resp = await fetch(`/api/display/${type}`, { method: "POST", body: formData });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || "Upload failed");
    }
    toast(`${type.charAt(0).toUpperCase() + type.slice(1)} uploaded`);
    refreshPreview();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

async function uploadVideo() {
  const input = document.getElementById("video-input");
  if (!input.files.length) { toast("Select a video first", "error"); return; }

  const btn = event.target;
  btn.classList.add("loading");
  btn.disabled = true;

  const fps = document.getElementById("video-fps").value;
  const dur = document.getElementById("video-duration").value;
  const formData = new FormData();
  formData.append("file", input.files[0]);

  try {
    const resp = await fetch(`/api/display/video?fps=${fps}&max_duration=${dur}`, {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || "Conversion failed");
    }
    const data = await resp.json();
    toast(`Video converted: ${data.frames} frames`);
    refreshPreview();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

// --- Brightness ---

function updateBrightness(val) {
  document.getElementById("bri-val").textContent = val;
  clearTimeout(brightnessTimer);
  brightnessTimer = setTimeout(async () => {
    try {
      await api("/api/brightness", {
        method: "POST",
        body: JSON.stringify({ brightness: parseInt(val) }),
      });
    } catch (e) {
      toast(e.message, "error");
    }
  }, 200);
}

// --- Off ---

async function turnOff() {
  try {
    await api("/api/display/off", { method: "POST" });
    toast("Panel off");
    refreshPreview();
  } catch (e) {
    toast(e.message, "error");
  }
}

// --- Preview ---

function refreshPreview() {
  document.getElementById("preview").src = `/api/preview?t=${Date.now()}`;
}

// --- Helpers ---

function hexToRgb(hex) {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

// --- Init ---

checkStatus();
setInterval(refreshPreview, 5000);
