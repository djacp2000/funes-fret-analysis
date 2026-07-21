"""Dependency-free HTML template for the read-only Module 9 ROI viewer."""

ROI_REVIEW_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__FUNES_TITLE__</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #0d131a; color: #eef4f8; }
    header { padding: 18px 22px; border-bottom: 1px solid #2b3945; background: #121b24; }
    h1 { margin: 0 0 5px; font-size: 20px; }
    header p { margin: 0; color: #aebdca; font-size: 13px; }
    main { display: grid; grid-template-columns: minmax(420px, 1fr) 330px; gap: 18px; padding: 18px; }
    .panel { background: #121b24; border: 1px solid #2b3945; border-radius: 9px; padding: 14px; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; margin-bottom: 12px; }
    button, select, input, textarea { font: inherit; color: inherit; background: #1d2a35; border: 1px solid #415362; border-radius: 5px; }
    button { padding: 7px 11px; cursor: pointer; }
    button:hover:not(:disabled) { background: #263847; }
    button:disabled { cursor: not-allowed; opacity: 0.45; }
    select, input { padding: 6px 8px; }
    input[type="range"] { flex: 1; min-width: 160px; padding: 0; }
    input[type="checkbox"] { accent-color: #37c6e8; }
    .stage { position: relative; width: 100%; background: #000; overflow: hidden; border: 1px solid #4b5c69; }
    .stage img, .stage svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
    .roi { cursor: pointer; }
    .roi path { fill: none; stroke-width: 1.5; vector-effect: non-scaling-stroke; }
    .roi text { font: 600 10px Arial, sans-serif; text-anchor: middle; dominant-baseline: central; paint-order: stroke; stroke: #071018; stroke-width: 2.5px; vector-effect: non-scaling-stroke; }
    .roi.accepted path { stroke: #00d9ff; }
    .roi.accepted text { fill: #00d9ff; }
    .roi.flagged path { stroke: #ffd166; }
    .roi.flagged text { fill: #ffd166; }
    .roi.flagged path { stroke-dasharray: 1 3; }
    .roi.rejected path { stroke: #ff6b6b; }
    .roi.rejected text { fill: #ff6b6b; }
    .roi.rejected path { stroke-dasharray: 5 3; }
    svg.hide-accepted .roi.accepted, svg.hide-flagged .roi.flagged, svg.hide-rejected .roi.rejected { display: none; }
    svg.hide-labels .roi text { display: none; }
    .legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 11px; font-size: 12px; color: #c6d2db; }
    .swatch { display: inline-block; width: 22px; height: 3px; margin-right: 6px; vertical-align: middle; }
    .accepted-swatch { background: #00d9ff; }
    .flagged-swatch { background: #ffd166; }
    .rejected-swatch { background: #ff6b6b; }
    aside { display: grid; gap: 14px; align-content: start; }
    h2 { margin: 0 0 11px; font-size: 16px; }
    dl { display: grid; grid-template-columns: 110px 1fr; gap: 7px 9px; margin: 0; font-size: 13px; }
    dt { color: #92a6b5; }
    dd { margin: 0; overflow-wrap: anywhere; }
    label.block { display: block; margin-top: 10px; color: #bac8d2; font-size: 12px; }
    label.block input, label.block textarea { width: 100%; margin-top: 5px; }
    textarea { min-height: 96px; resize: vertical; padding: 8px; }
    .confirmation { display: flex; gap: 8px; align-items: flex-start; margin: 13px 0; font-size: 12px; line-height: 1.35; }
    .notice { color: #ffca83; font-size: 12px; line-height: 1.4; }
    .saved { min-height: 18px; color: #7ee2a8; font-size: 12px; margin-top: 8px; }
    .frame-atlas { margin: 0 18px 18px; }
    .frame-atlas > p { color: #aebdca; font-size: 13px; }
    .frame-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
    .frame-card { margin: 0; background: #080c10; border: 1px solid #415362; border-radius: 6px; overflow: hidden; }
    .frame-card img { display: block; width: 100%; height: auto; }
    .frame-card figcaption { padding: 8px 10px; color: #d7e2e9; font-size: 13px; font-weight: 600; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>__FUNES_TITLE__</h1>
    <p id="context-line"></p>
  </header>
  <main>
    <section class="panel">
      <div class="toolbar">
        <label>Channel <select id="channel"><option>C0</option><option>C1</option></select></label>
        <button id="previous" type="button">Previous</button>
        <label id="frame-label" for="frame">Frame 0</label>
        <input id="frame" type="range" min="0" value="0" step="1">
        <button id="next" type="button">Next</button>
      </div>
      <div class="toolbar">
        <label><input id="show-accepted" type="checkbox" checked> Accepted</label>
        <label><input id="show-flagged" type="checkbox" checked> Flagged</label>
        <label><input id="show-rejected" type="checkbox" checked> Rejected</label>
        <label><input id="show-labels" type="checkbox" checked> Labels</label>
      </div>
      <div id="stage" class="stage">
        <img id="frame-image" alt="Temporal fluorescence frame">
        __FUNES_OVERLAY__
      </div>
      <div class="legend">
        <span><i class="swatch accepted-swatch"></i>Accepted</span>
        <span><i class="swatch flagged-swatch"></i>Flagged</span>
        <span><i class="swatch rejected-swatch"></i>Rejected</span>
        <span>Contours are fixed Module 7/8 labels on every frame.</span>
      </div>
    </section>
    <aside>
      <section class="panel">
        <h2>Selected ROI</h2>
        <dl>
          <dt>Label</dt><dd id="roi-label">Click a contour</dd>
          <dt>Status</dt><dd id="roi-status">—</dd>
          <dt>Area</dt><dd id="roi-area">—</dd>
          <dt>Border</dt><dd id="roi-border">—</dd>
          <dt>Reasons</dt><dd id="roi-reasons">—</dd>
        </dl>
      </section>
      <section class="panel">
        <h2>Field review</h2>
        <dl>
          <dt>Method/profile</dt><dd id="selection"></dd>
          <dt>Selection source</dt><dd id="selection-source"></dd>
          <dt>Current status</dt><dd id="review-status"></dd>
          <dt>Label SHA-256</dt><dd id="label-hash"></dd>
          <dt>Filtering SHA-256</dt><dd id="filtering-hash"></dd>
        </dl>
        <label class="block">Reviewer (optional)<input id="reviewer" type="text"></label>
        <label class="block">Inspection time (optional)<input id="inspected-at" type="text" placeholder="ISO 8601 or laboratory notation"></label>
        <label class="block">Review note (optional)<textarea id="note"></textarea></label>
        <label class="confirmation"><input id="reviewed" type="checkbox">I inspected this field with the displayed fixed labels and selection.</label>
        <button id="export" type="button" disabled>Export review JSON</button>
        <div id="saved" class="saved"></div>
        <p class="notice">Read-only viewer: exporting a review records inspection only. It does not delete ROIs, edit masks, rerun segmentation, or approve a global policy.</p>
      </section>
    </aside>
  </main>
  <section class="panel frame-atlas">
    <h2>All embedded frames — static fallback</h2>
    <p>These panels are written directly into the HTML and remain visible even if local-file JavaScript or browser storage is restricted.</p>
    <div class="frame-grid">__FUNES_FRAME_ATLAS__</div>
  </section>
  <script id="viewer-data" type="application/json">__FUNES_VIEWER_DATA__</script>
  <script>
    (() => {
      "use strict";
      const data = JSON.parse(document.getElementById("viewer-data").textContent);
      const byId = (id) => document.getElementById(id);
      const channel = byId("channel");
      const frame = byId("frame");
      const image = byId("frame-image");
      const overlay = byId("roi-overlay");
      const reviewer = byId("reviewer");
      const inspectedAt = byId("inspected-at");
      const note = byId("note");
      const reviewed = byId("reviewed");
      const exportButton = byId("export");

      byId("context-line").textContent = `${data.field.capture} · ${data.field.position} · ${data.frame_count} temporal frame(s)`;
      byId("selection").textContent = `${data.selection.method}/${data.selection.profile}`;
      byId("selection-source").textContent = data.selection.source;
      byId("review-status").textContent = data.review_status;
      byId("label-hash").textContent = data.source_label_sha256;
      byId("filtering-hash").textContent = data.roi_filtering_sha256;
      byId("stage").style.aspectRatio = `${data.width} / ${data.height}`;
      frame.max = String(data.frame_count - 1);

      function loadState() {
        try {
          return JSON.parse(localStorage.getItem(data.storage_key) || "{}");
        } catch (error) {
          return {};
        }
      }

      const saved = loadState();
      channel.value = saved.channel === "C1" ? "C1" : "C0";
      frame.value = String(Math.min(data.frame_count - 1, Math.max(0, Number(saved.frame || 0))));
      reviewer.value = saved.reviewer || "";
      inspectedAt.value = saved.inspected_at || "";
      note.value = saved.note || "";
      reviewed.checked = Boolean(saved.reviewed);
      for (const key of ["accepted", "flagged", "rejected", "labels"]) {
        const control = byId(`show-${key}`);
        control.checked = saved[`show_${key}`] === undefined ? true : Boolean(saved[`show_${key}`]);
      }

      function saveState() {
        const state = {
          channel: channel.value,
          frame: Number(frame.value),
          reviewer: reviewer.value,
          inspected_at: inspectedAt.value,
          note: note.value,
          reviewed: reviewed.checked
        };
        for (const key of ["accepted", "flagged", "rejected", "labels"]) {
          state[`show_${key}`] = byId(`show-${key}`).checked;
        }
        try {
          localStorage.setItem(data.storage_key, JSON.stringify(state));
          byId("saved").textContent = "Review draft saved in this browser.";
        } catch (error) {
          byId("saved").textContent = "Browser storage is unavailable; viewer controls still work.";
        }
      }

      function render() {
        const index = Number(frame.value);
        image.src = data.channels[channel.value][index];
        image.alt = `${channel.value} temporal frame ${index}`;
        byId("frame-label").textContent = `Frame ${index} / ${data.frame_count - 1}`;
        byId("previous").disabled = index === 0;
        byId("next").disabled = index === data.frame_count - 1;
        for (const key of ["accepted", "flagged", "rejected"]) {
          overlay.classList.toggle(`hide-${key}`, !byId(`show-${key}`).checked);
        }
        overlay.classList.toggle("hide-labels", !byId("show-labels").checked);
        exportButton.disabled = !reviewed.checked;
      }

      channel.addEventListener("change", () => { render(); saveState(); });
      frame.addEventListener("input", () => { render(); saveState(); });
      byId("previous").addEventListener("click", () => { frame.value = String(Number(frame.value) - 1); render(); saveState(); });
      byId("next").addEventListener("click", () => { frame.value = String(Number(frame.value) + 1); render(); saveState(); });
      for (const id of ["show-accepted", "show-flagged", "show-rejected", "show-labels", "reviewer", "inspected-at", "note", "reviewed"]) {
        byId(id).addEventListener("input", () => { render(); saveState(); });
      }

      overlay.addEventListener("click", (event) => {
        const group = event.target.closest(".roi");
        if (!group) return;
        const record = data.rois[group.dataset.label];
        byId("roi-label").textContent = record.label;
        byId("roi-status").textContent = record.status;
        byId("roi-area").textContent = `${record.area_pixels} px`;
        byId("roi-border").textContent = record.touches_border ? "yes" : "no";
        byId("roi-reasons").textContent = record.reasons.length ? record.reasons.join(", ") : "none";
      });

      exportButton.addEventListener("click", () => {
        if (!reviewed.checked) return;
        const record = JSON.parse(JSON.stringify(data.review_record));
        record.inspection = {
          inspector: reviewer.value.trim() || null,
          inspected_at: inspectedAt.value.trim() || null,
          note: note.value.trim() || null
        };
        const blob = new Blob([JSON.stringify(record, null, 2) + "\n"], {type: "application/json"});
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = data.review_filename;
        link.click();
        URL.revokeObjectURL(url);
      });

      render();
    })();
  </script>
</body>
</html>
"""
