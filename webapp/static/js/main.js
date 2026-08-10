/* ==========================================================================
   IamGroot web UI logic
   ========================================================================== */
(() => {
  "use strict";

  // ---- Tabs -------------------------------------------------------------
  const tabEncode = document.getElementById("tab-encode");
  const tabDecode = document.getElementById("tab-decode");
  const panelEncode = document.getElementById("panel-encode");
  const panelDecode = document.getElementById("panel-decode");

  function activateTab(which) {
    const encoding = which === "encode";
    tabEncode.classList.toggle("is-active", encoding);
    tabDecode.classList.toggle("is-active", !encoding);
    tabEncode.setAttribute("aria-selected", String(encoding));
    tabDecode.setAttribute("aria-selected", String(!encoding));
    panelEncode.classList.toggle("is-hidden", !encoding);
    panelDecode.classList.toggle("is-hidden", encoding);
  }

  tabEncode.addEventListener("click", () => activateTab("encode"));
  tabDecode.addEventListener("click", () => activateTab("decode"));

  // ---- Encode: char counter + live duration estimate ---------------------
  const messageEl = document.getElementById("message");
  const charCounter = document.getElementById("char-counter");
  const durationEstimate = document.getElementById("duration-estimate");
  const encodePwToggle = document.getElementById("encode-pw-toggle");
  const encodePwWrap = document.getElementById("encode-pw-wrap");
  const encodePassword = document.getElementById("encode-password");

  let estimateTimer = null;
  // let currentCap = null;

  // async function refreshEstimate() {
  //   const chars = [...messageEl.value].length; // count code points, not UTF-16 units
  //   const encrypted = encodePwToggle.checked;
  //   try {
  //     const res = await fetch(`/api/estimate?chars=${chars}&encrypted=${encrypted}`);
  //     const data = await res.json();
  //     currentCap = data.max_chars;
  //     // charCounter.textContent = `${chars} / ${data.max_chars} characters`;
  //     charCounter.classList.toggle("is-over", chars > data.max_chars);
  //     durationEstimate.textContent = chars > 0
  //       ? `~${data.duration_seconds}s of audio`
  //       : "~– s of audio";
  //   } catch (err) {
  //     durationEstimate.textContent = "";
  //   }
  // }

  // function scheduleEstimate() {
  //   clearTimeout(estimateTimer);
  //   estimateTimer = setTimeout(refreshEstimate, 150);
  // }

  // messageEl.addEventListener("input", scheduleEstimate);
  encodePwToggle.addEventListener("change", () => {
    encodePwWrap.classList.toggle("is-hidden", !encodePwToggle.checked);
    if (encodePwToggle.checked) {
      encodePassword.focus();
    } else {
      encodePassword.value = "";
    }
    scheduleEstimate();
  });

  // refreshEstimate();

  // ---- Encode: submit -----------------------------------------------------
  const encodeForm = document.getElementById("encode-form");
  const encodeSubmit = document.getElementById("encode-submit");
  const encodeResult = document.getElementById("encode-result");

  function setStatus(container, text) {
    container.innerHTML = `
      <div class="status-line">
        <span class="status-dot" aria-hidden="true"></span>
        <span>${text}</span>
      </div>`;
  }

  function setError(container, message) {
    container.innerHTML = `
      <div class="result-card is-error">
        <p class="result-headline">Couldn't do that</p>
        <p>${escapeHtml(message)}</p>
      </div>`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  encodeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = messageEl.value.trim();
    if (!text) {
      setError(encodeResult, "Write something for the voice to carry first.");
      return;
    }
    // if (currentCap !== null && [...text].length > currentCap) {
    //   setError(encodeResult, `That message is too long for one breath of audio -- keep it under ${currentCap} characters.`);
    //   return;
    // }

    const password = encodePwToggle.checked ? encodePassword.value : "";

    encodeSubmit.disabled = true;
    setStatus(encodeResult, "Growing the voice\u2026 stretching pitch and loudness around your words.");

    try {
      const res = await fetch("/api/encode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, password: password || null }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(encodeResult, data.error || "Something went wrong while encoding.");
        return;
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);

      encodeResult.innerHTML = `
        <div class="result-card">
          <p class="result-headline">Ready</p>
          ${password ? '<span class="encrypted-badge">🔒 AES-256 locked</span>' : ""}
          <audio class="result-audio" controls src="${url}"></audio>
          <div class="result-actions">
            <a class="ghost-btn" href="${url}" download="iamgroot_message.wav">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M7 1v8M7 9L4 6M7 9l3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M2 11.5v.5A1.5 1.5 0 0 0 3.5 13.5h7A1.5 1.5 0 0 0 12 12v-.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
              </svg>
              Download .wav
            </a>
          </div>
        </div>`;
    } catch (err) {
      setError(encodeResult, "Couldn't reach the server. Is it still running?");
    } finally {
      encodeSubmit.disabled = false;
    }
  });

  // ---- Decode: dropzone ----------------------------------------------------
  const dropzone = document.getElementById("dropzone");
  const audioInput = document.getElementById("audio-input");
  const dropzoneFilename = document.getElementById("dropzone-filename");
  let selectedFile = null;

  function pickFile(file) {
    if (!file) return;
    selectedFile = file;
    dropzoneFilename.textContent = file.name;
  }

  dropzone.addEventListener("click", () => audioInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      audioInput.click();
    }
  });
  audioInput.addEventListener("change", () => pickFile(audioInput.files[0]));

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) pickFile(file);
  });

  // ---- Decode: submit -------------------------------------------------------
  const decodeForm = document.getElementById("decode-form");
  const decodeSubmit = document.getElementById("decode-submit");
  const decodeResult = document.getElementById("decode-result");
  const decodePassword = document.getElementById("decode-password");

  decodeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) {
      setError(decodeResult, "Choose a .wav file to reveal first.");
      return;
    }

    const formData = new FormData();
    formData.append("audio", selectedFile);
    if (decodePassword.value) formData.append("password", decodePassword.value);

    decodeSubmit.disabled = true;
    setStatus(decodeResult, "Listening closely\u2026 reading pitch and loudness back into words.");

    try {
      const res = await fetch("/api/decode", { method: "POST", body: formData });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError(decodeResult, data.error || "Couldn't reveal a message from that file.");
        return;
      }

      decodeResult.innerHTML = `
        <div class="result-card">
          <p class="result-headline">Revealed</p>
          <div class="revealed-message"></div>
          <div class="result-actions">
            <button type="button" class="ghost-btn" id="copy-message-btn">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <rect x="5" y="5" width="7.5" height="7.5" rx="1.2" stroke="currentColor" stroke-width="1.3"/>
                <path d="M2.5 9V2.7A1.2 1.2 0 0 1 3.7 1.5H10" stroke="currentColor" stroke-width="1.3"/>
              </svg>
              Copy text
            </button>
          </div>
        </div>`;
      // set as text (not innerHTML) to avoid any injection from decoded content
      decodeResult.querySelector(".revealed-message").textContent = data.message;

      document.getElementById("copy-message-btn").addEventListener("click", async () => {
        await navigator.clipboard.writeText(data.message);
        const btn = document.getElementById("copy-message-btn");
        const original = btn.innerHTML;
        btn.textContent = "Copied";
        setTimeout(() => { btn.innerHTML = original; }, 1400);
      });
    } catch (err) {
      setError(decodeResult, "Couldn't reach the server. Is it still running?");
    } finally {
      decodeSubmit.disabled = false;
    }
  });
})();
