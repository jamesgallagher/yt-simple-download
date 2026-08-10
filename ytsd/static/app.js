(function () {
  "use strict";

  const form = document.getElementById("form");
  const providerSel = document.getElementById("provider");
  const urlInput = document.getElementById("url");
  const urlLabel = document.getElementById("url-label");
  const urlMsg = document.getElementById("url-msg");
  const qualitySel = document.getElementById("quality");
  const qualityLabel = document.getElementById("quality-label");
  const submitBtn = document.getElementById("submit");

  const advancedCheck = document.getElementById("advanced");
  const advancedOpts = document.getElementById("advanced-opts");
  const startInput = document.getElementById("start");
  const endInput = document.getElementById("end");

  const preview = document.getElementById("preview");
  const previewThumb = document.getElementById("preview-thumb");
  const previewTitle = document.getElementById("preview-title");
  const previewSub = document.getElementById("preview-sub");

  const statusBox = document.getElementById("status");
  const statusTitle = document.getElementById("status-title");
  const statusStage = document.getElementById("status-stage");
  const statusMsg = document.getElementById("status-msg");
  const barFill = document.getElementById("bar-fill");
  const dlLink = document.getElementById("download-link");

  const PROVIDERS = {};
  JSON.parse(document.getElementById("providers-data").textContent)
    .forEach((p) => { PROVIDERS[p.name] = p; });

  let pollTimer = null;
  let probeTimer = null;
  let probeSeq = 0;
  let validated = false;
  let busy = false;

  // ------------------------------------------------------------ helpers
  function currentFormat() {
    return document.querySelector('input[name="format"]:checked').value;
  }
  function currentProvider() {
    return PROVIDERS[providerSel.value] || Object.values(PROVIDERS)[0];
  }
  function prettyQuality(q) {
    if (q === "best") return "Best available";
    if (/^\d+p$/.test(q)) return q;
    if (/^\d+$/.test(q)) return q + " kbps";
    return q;
  }

  function fillQualities() {
    const prov = currentProvider();
    const fmt = currentFormat();
    const opts = (fmt === "mp3" ? prov.audio : prov.video) || ["best"];
    qualitySel.innerHTML = "";
    for (const q of opts) {
      const o = document.createElement("option");
      o.value = q;
      o.textContent = prettyQuality(q);
      qualitySel.appendChild(o);
    }
    qualityLabel.textContent = fmt === "mp3" ? "Audio quality" : "Max resolution";
  }

  function applyProvider(name) {
    const prov = PROVIDERS[name];
    if (!prov) return;
    providerSel.value = name;
    urlInput.placeholder = prov.placeholder;
    urlLabel.textContent = prov.display + " link";
    fillQualities();
  }

  // ------------------------------------------------------------ preview / probe
  function fmtDuration(s) {
    s = parseInt(s, 10);
    if (!s || s < 0) return "";
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
  }
  function resetPreview() {
    validated = false;
    preview.classList.add("hidden");
    previewThumb.removeAttribute("src");
    updateSubmit();
  }
  function setUrlMsg(text, cls) {
    urlMsg.textContent = text || "";
    urlMsg.className = "url-msg" + (cls ? " " + cls : "");
  }
  function updateSubmit() {
    submitBtn.disabled = !(validated && !busy);
  }

  async function probe() {
    const url = urlInput.value.trim();
    resetPreview();
    if (!url) { setUrlMsg("", null); return; }

    const seq = ++probeSeq;
    setUrlMsg("Checking link…", null);

    let resp;
    try {
      resp = await fetch("/api/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
    } catch (e) {
      if (seq === probeSeq) setUrlMsg("Could not reach the server.", "error");
      return;
    }
    if (seq !== probeSeq) return;

    if (!resp.ok) {
      let detail = "That link isn't supported.";
      try { detail = (await resp.json()).detail || detail; } catch (e) {}
      setUrlMsg(detail, "error");
      return;
    }

    const meta = await resp.json();
    if (seq !== probeSeq) return;

    // Sync the selector to the detected service.
    if (meta.provider && PROVIDERS[meta.provider]) applyProvider(meta.provider);

    previewThumb.onerror = () => { previewThumb.style.visibility = "hidden"; };
    previewThumb.onload = () => { previewThumb.style.visibility = "visible"; };
    previewThumb.style.visibility = "visible";
    previewThumb.src = meta.thumbnail || "";
    previewTitle.textContent = meta.title || "Untitled";
    const bits = [];
    if (meta.provider_display) bits.push(meta.provider_display);
    if (meta.uploader) bits.push(meta.uploader);
    const dur = fmtDuration(meta.duration);
    if (dur) bits.push(dur);
    previewSub.textContent = bits.join("  ·  ");
    preview.classList.remove("hidden");

    validated = true;
    setUrlMsg("Ready to download.", "ok");
    updateSubmit();
  }

  // ------------------------------------------------------------ wiring
  document.querySelectorAll('input[name="format"]').forEach((r) =>
    r.addEventListener("change", fillQualities)
  );
  providerSel.addEventListener("change", () => {
    applyProvider(providerSel.value);
    if (urlInput.value.trim()) probe();
  });
  advancedCheck.addEventListener("change", () => {
    advancedOpts.classList.toggle("hidden", !advancedCheck.checked);
  });
  urlInput.addEventListener("input", () => {
    validated = false;
    updateSubmit();
    clearTimeout(probeTimer);
    probeTimer = setTimeout(probe, 500);
  });

  applyProvider(providerSel.value);

  // ------------------------------------------------------------ status bar
  function setBar(pct, cls) {
    barFill.style.width = Math.max(0, Math.min(100, pct)) + "%";
    barFill.className = "bar-fill" + (cls ? " " + cls : "");
  }
  function stopPolling() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  }
  function setBusy(on) {
    busy = on;
    submitBtn.textContent = on ? "Working…" : "Download";
    updateSubmit();
  }

  async function poll(id) {
    let resp;
    try {
      resp = await fetch("/api/jobs/" + encodeURIComponent(id));
    } catch (e) {
      pollTimer = setTimeout(() => poll(id), 2500);
      return;
    }
    if (!resp.ok) {
      showError("Lost track of that job. Try again.");
      setBusy(false);
      return;
    }
    const j = await resp.json();
    statusStage.textContent = j.stage || "";
    if (j.title) statusTitle.textContent = j.title;

    if (j.status === "ready") {
      setBar(100, "done");
      statusMsg.classList.remove("error");
      statusMsg.textContent = "Ready: " + j.filename;
      dlLink.href = "/api/jobs/" + encodeURIComponent(id) + "/file";
      dlLink.classList.remove("hidden");
      dlLink.click();
      setBusy(false);
      return;
    }
    if (j.status === "error") {
      showError(j.error || "Something went wrong.");
      setBusy(false);
      return;
    }

    if (j.status === "downloading") setBar(j.progress, null);
    else if (j.status === "processing") setBar(100, null);
    else setBar(j.progress || 4, null);
    statusMsg.classList.remove("error");
    statusMsg.textContent = j.status === "queued" ? "Waiting for a free worker…" : "";
    pollTimer = setTimeout(() => poll(id), 1500);
  }

  function showError(msg) {
    setBar(100, "err");
    statusStage.textContent = "Error";
    statusMsg.classList.add("error");
    statusMsg.textContent = msg;
    dlLink.classList.add("hidden");
  }

  // ------------------------------------------------------------ download
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!validated || busy) return;
    stopPolling();
    dlLink.classList.add("hidden");
    statusBox.classList.remove("hidden");
    statusTitle.textContent = previewTitle.textContent || "Working…";
    statusStage.textContent = "Submitting";
    statusMsg.classList.remove("error");
    statusMsg.textContent = "";
    setBar(4, null);
    setBusy(true);

    const payload = {
      url: urlInput.value.trim(),
      provider: providerSel.value,
      format: currentFormat(),
      quality: qualitySel.value,
    };
    if (advancedCheck.checked) {
      payload.start = startInput.value.trim();
      payload.end = endInput.value.trim();
    }

    let resp;
    try {
      resp = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      showError("Could not reach the server.");
      setBusy(false);
      return;
    }

    if (!resp.ok) {
      let detail = "Request rejected.";
      try { detail = (await resp.json()).detail || detail; } catch (e) {}
      showError(detail);
      setBusy(false);
      return;
    }

    const { id } = await resp.json();
    poll(id);
  });
})();
