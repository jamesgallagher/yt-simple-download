(function () {
  "use strict";

  const form = document.getElementById("form");
  const urlInput = document.getElementById("url");
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

  const QUALITIES = JSON.parse(document.getElementById("quality-data").textContent);
  const PRETTY = { best: "Best available", "320": "320 kbps", "192": "192 kbps", "128": "128 kbps" };

  let pollTimer = null;
  let probeTimer = null;
  let probeSeq = 0;      // guards against out-of-order probe responses
  let validated = false; // a valid video is previewed
  let busy = false;      // a download is in flight

  // ------------------------------------------------------------ quality
  function currentFormat() {
    return document.querySelector('input[name="format"]:checked').value;
  }

  function fillQualities() {
    const fmt = currentFormat();
    const opts = QUALITIES[fmt] || ["best"];
    qualitySel.innerHTML = "";
    for (const q of opts) {
      const o = document.createElement("option");
      o.value = q;
      o.textContent = PRETTY[q] || q;
      qualitySel.appendChild(o);
    }
    qualityLabel.textContent = fmt === "mp3" ? "Audio quality" : "Max resolution";
  }

  document.querySelectorAll('input[name="format"]').forEach((r) =>
    r.addEventListener("change", fillQualities)
  );
  fillQualities();

  // ------------------------------------------------------------ advanced options
  advancedCheck.addEventListener("change", () => {
    advancedOpts.classList.toggle("hidden", !advancedCheck.checked);
  });

  // ------------------------------------------------------------ submit gating
  function updateSubmit() {
    submitBtn.disabled = !(validated && !busy);
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
    if (seq !== probeSeq) return; // a newer probe superseded this one

    if (!resp.ok) {
      let detail = "That doesn't look like a YouTube video.";
      try { detail = (await resp.json()).detail || detail; } catch (e) {}
      setUrlMsg(detail, "error");
      return;
    }

    const meta = await resp.json();
    if (seq !== probeSeq) return;

    previewThumb.src = meta.thumbnail || "";
    previewTitle.textContent = meta.title || "Untitled";
    const bits = [];
    if (meta.uploader) bits.push(meta.uploader);
    const dur = fmtDuration(meta.duration);
    if (dur) bits.push(dur);
    previewSub.textContent = bits.join("  ·  ");
    preview.classList.remove("hidden");

    validated = true;
    setUrlMsg("Ready to download.", "ok");
    updateSubmit();
  }

  urlInput.addEventListener("input", () => {
    validated = false;
    updateSubmit();
    clearTimeout(probeTimer);
    probeTimer = setTimeout(probe, 500);
  });

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
      dlLink.click(); // auto-start the download to the device
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
