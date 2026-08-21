(function () {
  const form = document.getElementById("cwForm");
  const statusBox = document.getElementById("statusBox");
  const downloadBox = document.getElementById("downloadBox");
  const downloadLink = document.getElementById("downloadLink");
  const customWordsWrap = document.getElementById("customWordsWrap");
  const puzzleCountWrap = document.getElementById("puzzleCountWrap");
  const generateBtn = document.getElementById("generateBtn");

  function selectedMode() {
    const picked = form.querySelector('input[name="creation_mode"]:checked');
    return picked ? picked.value : "topic";
  }

  function selectedOutputType() {
    const picked = form.querySelector('input[name="output_type"]:checked');
    return picked ? picked.value : "single_worksheet";
  }

  function syncFormVisibility() {
    const mode = selectedMode();
    const outputType = selectedOutputType();
    customWordsWrap.classList.toggle("hidden", mode !== "custom_word_list");
    puzzleCountWrap.classList.toggle("hidden", outputType !== "book");
  }

  form.querySelectorAll('input[name="creation_mode"], input[name="output_type"]').forEach(function (el) {
    el.addEventListener("change", syncFormVisibility);
  });
  syncFormVisibility();

  function showStatus(kind, messages) {
    statusBox.classList.remove("hidden");
    const list = Array.isArray(messages) ? messages : [messages];
    const color =
      kind === "success"
        ? "border-emerald-200 bg-emerald-50 text-emerald-900"
        : kind === "warning"
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-rose-200 bg-rose-50 text-rose-900";
    statusBox.className = "mt-6 rounded-xl border p-4 text-sm " + color;
    statusBox.innerHTML = list.map(function (line) {
      return "<div>" + String(line).replace(/</g, "&lt;") + "</div>";
    }).join("");
  }

  function formPayload() {
    const data = new FormData(form);
    const body = {};
    data.forEach(function (value, key) {
      body[key] = value;
    });
    body.creation_mode = selectedMode();
    body.output_type = selectedOutputType();
    const answer = form.querySelector('input[name="include_answer_key"]:checked');
    body.include_answer_key = answer ? answer.value : "yes";
    const cover = form.querySelector('input[name="include_cover"]:checked');
    body.include_cover = cover ? cover.value : "yes";
    return body;
  }

  function setLoading(loading) {
    if (loading) {
      generateBtn.disabled = true;
      generateBtn.innerHTML = `
        <svg class="animate-spin -ml-1 mr-2 h-5 w-5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        Generating...`;
    } else {
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate Crossword PDF";
    }
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    downloadBox.classList.add("hidden");
    statusBox.classList.add("hidden");
    setLoading(true);

    try {
      const response = await fetch("/crossword-builder/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formPayload()),
      });
      const payload = await response.json();

      if (!response.ok || !payload.ok) {
        const errors = payload.errors || [payload.error || "Could not generate the PDF."];
        showStatus("error", errors);
        if (payload.warnings && payload.warnings.length) {
          showStatus("warning", payload.warnings);
        }
        return;
      }

      // One box, so warnings never overwrite the success line.
      const lines = [payload.message || "Crossword PDF created successfully."];
      if (payload.warnings && payload.warnings.length) lines.push(...payload.warnings);
      showStatus(payload.warnings && payload.warnings.length ? "warning" : "success", lines);
      downloadLink.href = payload.download_url;
      downloadLink.textContent = "Download PDF";
      downloadBox.classList.remove("hidden");
    } catch (err) {
      showStatus("error", ["Something went wrong while generating the PDF. Please try again."]);
    } finally {
      setLoading(false);
    }
  });
})();
