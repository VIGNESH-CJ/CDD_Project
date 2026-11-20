/** Shared safe rendering and status helpers for the vanilla JavaScript screens. */
const UI = {
  escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[character]);
  },

  imageUrl(value) {
    try {
      const url = new URL(String(value || ""), window.location.origin);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch {
      return "";
    }
  },

  currency(value) {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value) || 0);
  },

  formatDateTime(value, options = {}) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Date and time unavailable";
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      ...options
    }).format(date);
  },

  setLoading(container, message = "Loading…") {
    if (!container) return;
    container.setAttribute("aria-busy", "true");
    container.innerHTML = `<div class="ui-state" role="status"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span><span>${this.escapeHtml(message)}</span></div>`;
  },

  setError(container, error, retryLabel = "Try again") {
    if (!container) return;
    container.removeAttribute("aria-busy");
    container.innerHTML = `<div class="ui-state ui-state-error" role="alert"><i class="bi bi-exclamation-circle" aria-hidden="true"></i><span>${this.escapeHtml(error?.message || "Something went wrong. Please try again.")}</span>${retryLabel ? `<button class="btn btn-sm btn-outline-danger" type="button" data-ui-retry>${this.escapeHtml(retryLabel)}</button>` : ""}</div>`;
  },

  setEmpty(container, title, detail = "") {
    if (!container) return;
    container.removeAttribute("aria-busy");
    container.innerHTML = `<div class="ui-state ui-state-empty"><strong>${this.escapeHtml(title)}</strong>${detail ? `<span>${this.escapeHtml(detail)}</span>` : ""}</div>`;
  },

  clearBusy(container) {
    container?.removeAttribute("aria-busy");
  }
};

function updateLiveTimes() {
  const now = new Date();
  document.querySelectorAll("[data-live-clock]").forEach(element => {
    element.dateTime = now.toISOString();
    element.textContent = UI.formatDateTime(now);
  });
  document.querySelectorAll("[data-current-year]").forEach(element => {
    element.textContent = String(now.getFullYear());
  });
}

updateLiveTimes();
window.setInterval(updateLiveTimes, 1000);
