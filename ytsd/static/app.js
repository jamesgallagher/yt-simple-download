(function () {
  "use strict";

  const form = document.getElementById("form");
  const urlInput = document.getElementById("url");
  const qualitySel = document.getElementById("quality");
  const qualityLabel = document.getElementById("quality-label");
  const submitBtn = document.getElementById("submit");

  const statusBox = document.getElementById("status");
  const statusTitle = document.getElementById("status-title");
  const statusStage = document.getElementById("status-stage");
  const statusMsg = document.getElementById("status-msg");
  const barFill = document.getElementById("bar-fill");
  const dlLink = document.getElementById("download-link");

  const QUALITIES = JSON.parse(document.getElementById("quality-data").textContent);
  const PRETTY = { best: "Best available", "320": "320 kbps", "192": "192 kbps", "128": "128 kbps" };

  let pollTimer = null;

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

  function setBar(pct, cls) {
    barFill.style.width = Math.max(0, Math.min(100, pct)) + "%";
    barFill.className = "bar-fill" + (cls ? " " + cls : "");
  }

  function stopPolling() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  }

  function finish(enable) {
    submitBtn.disabled = !enable;
    submitBtn.textContent = enable ? "Download" : "Working…";
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
      finish(true);
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
      finish(true);
      return;
    }
    if (j.status === "error") {
      showError(j.error || "Something went wrong.");
      finish(true);
      return;
    }

    // in-flight
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

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    stopPolling();
    dlLink.classList.add("hidden");
    statusBox.classList.remove("hidden");
    statusTitle.textContent = "Working…";
    statusStage.textContent = "Submitting";
    statusMsg.classList.remove("error");
    statusMsg.textContent = "";
    setBar(4, null);
    finish(false);

    let resp;
    try {
      resp = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: urlInput.value.trim(),
          format: currentFormat(),
          quality: qualitySel.value,
        }),
      });
    } catch (err) {
      showError("Could not reach the server.");
      finish(true);
      return;
    }

    if (!resp.ok) {
      let detail = "Request rejected.";
      try { detail = (await resp.json()).detail || detail; } catch (e) {}
      showError(detail);
      finish(true);
      return;
    }

    const { id } = await resp.json();
    poll(id);
  });
})();
