/* Insider Threat Detection dashboard logic (Phase 8).
 *
 * Consumes the Phase 7 JSON APIs (/api/summary, /api/anomalies) and renders the
 * summary tiles, anomaly table, and row-click detail panel. All field access is
 * defensive so a missing value renders as a dash rather than crashing the page.
 */
(function () {
  "use strict";

  const SUMMARY_URL = "/api/summary";
  const ANOMALIES_URL = "/api/anomalies";
  const EXPORT_URL = "/api/anomalies.csv";

  let currentRows = [];

  function $(id) { return document.getElementById(id); }

  function showError(message) {
    setText("error-text", message);
    $("error-banner").hidden = false;
  }
  function clearError() {
    $("error-banner").hidden = true;
    const text = $("error-text");
    if (text) text.textContent = "";
  }

  function setLoading(isLoading) {
    const loader = $("table-loading");
    if (loader) loader.hidden = !isLoading;
    const scroll = document.querySelector(".table-scroll");
    if (scroll) scroll.setAttribute("aria-busy", isLoading ? "true" : "false");
    if (isLoading) $("empty-state").hidden = true;
    ["btn-apply", "btn-clear", "btn-export"].forEach(id => {
      const btn = $(id);
      if (btn) btn.disabled = isLoading;
    });
  }

  function setText(id, value) {
    const el = $(id);
    if (!el) return;
    el.textContent = (value === undefined || value === null || value === "") ? "—" : value;
  }

  function fmtScore(score) {
    return (typeof score === "number") ? score.toFixed(2) : "—";
  }

  function severityBadge(level) {
    const span = document.createElement("span");
    span.className = "badge badge-" + (level ? String(level).toLowerCase() : "none");
    span.textContent = level || "—";
    return span;
  }

  function explainFeature(reason) {
    if (!reason) return "—";
    if (reason.indexOf("login_time") !== -1)
      return "Login time — the user signed in well outside their normal hours.";
    if (reason.indexOf("access_count") !== -1)
      return "Access count — activity volume is far above the user's normal level.";
    if (reason.indexOf("resource_type") !== -1)
      return "Resource type — a resource that is rare or unseen for this user.";
    return "—";
  }

  async function loadSummary() {
    try {
      const resp = await fetch(SUMMARY_URL);
      if (!resp.ok) throw new Error("summary " + resp.status);
      const data = await resp.json();
      setText("tile-logs", data.total_activity_logs);
      setText("tile-anomalies", data.total_anomalies);
      setText("tile-high", data.high_risk_anomalies);
      setText("tile-users", data.users_monitored);
    } catch (err) {
      showError("Could not load summary data.");
    }
  }

  function buildFilterParams() {
    const params = new URLSearchParams();
    const user = $("f-user").value.trim();
    const start = $("f-start").value;
    const end = $("f-end").value;
    const severity = $("f-severity").value;
    if (user) params.set("user", user);
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    if (severity) params.set("severity", severity);
    return params;
  }

  function buildAnomaliesUrl() {
    const qs = buildFilterParams().toString();
    return qs ? (ANOMALIES_URL + "?" + qs) : ANOMALIES_URL;
  }

  function exportCsv() {
    const qs = buildFilterParams().toString();
    window.location.href = qs ? (EXPORT_URL + "?" + qs) : EXPORT_URL;
  }

  function renderRows(rows) {
    const tbody = $("anomaly-rows");
    tbody.innerHTML = "";
    setText("result-count", rows.length);
    $("empty-state").hidden = rows.length > 0;

    rows.forEach((row, index) => {
      const tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.dataset.index = String(index);

      const plainCells = [
        row.user_id, row.activity_date, row.login_time,
        row.resource_type, row.access_count, fmtScore(row.deviation_score),
      ];
      // Indices 4 (access count) and 5 (score) are numeric: right-align them.
      const numericIndexes = [4, 5];
      plainCells.forEach((value, cellIndex) => {
        const td = document.createElement("td");
        if (numericIndexes.indexOf(cellIndex) !== -1) td.className = "num";
        td.textContent = (value === undefined || value === null) ? "—" : value;
        tr.appendChild(td);
      });

      const severityTd = document.createElement("td");
      severityTd.appendChild(severityBadge(row.severity_level));
      tr.appendChild(severityTd);

      const reasonTd = document.createElement("td");
      reasonTd.className = "reason-cell";
      reasonTd.textContent = row.anomaly_reason || "—";
      tr.appendChild(reasonTd);

      tr.addEventListener("click", () => showDetail(index));
      tr.addEventListener("keydown", ev => {
        if (ev.key === "Enter" || ev.key === " " || ev.key === "Spacebar") {
          ev.preventDefault();  // stop Space scrolling the page
          showDetail(index);
        }
      });
      tbody.appendChild(tr);
    });
  }

  function showDetail(index) {
    const row = currentRows[index];
    if (!row) return;

    $("detail-hint").hidden = true;
    $("detail-list").hidden = false;

    setText("d-id", row.anomaly_id);
    setText("d-user", row.user_id);
    setText("d-datetime", (row.activity_date || "—") + "  " + (row.login_time || ""));
    setText("d-resource", row.resource_type);
    setText("d-access", row.access_count);
    setText("d-score", fmtScore(row.deviation_score));
    setText("d-feature", explainFeature(row.anomaly_reason));
    setText("d-reason", row.anomaly_reason);

    const severityDd = $("d-severity");
    severityDd.innerHTML = "";
    severityDd.appendChild(severityBadge(row.severity_level));

    document.querySelectorAll(".anomaly-table tbody tr").forEach(tr => tr.classList.remove("selected"));
    const selected = document.querySelector('.anomaly-table tbody tr[data-index="' + index + '"]');
    if (selected) selected.classList.add("selected");
  }

  async function loadAnomalies() {
    clearError();
    setLoading(true);
    try {
      const resp = await fetch(buildAnomaliesUrl());
      if (!resp.ok) throw new Error("anomalies " + resp.status);
      const data = await resp.json();
      currentRows = Array.isArray(data.anomalies) ? data.anomalies : [];
      renderRows(currentRows);
    } catch (err) {
      currentRows = [];
      renderRows([]);
      showError("Could not load anomalies. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function retry() {
    loadSummary();
    loadAnomalies();
  }

  function clearFilters() {
    $("f-user").value = "";
    $("f-start").value = "";
    $("f-end").value = "";
    $("f-severity").value = "";
    loadAnomalies();
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("btn-apply").addEventListener("click", loadAnomalies);
    $("btn-clear").addEventListener("click", clearFilters);
    $("btn-export").addEventListener("click", exportCsv);
    const retryBtn = $("btn-retry");
    if (retryBtn) retryBtn.addEventListener("click", retry);
    loadSummary();
    loadAnomalies();
  });
})();
