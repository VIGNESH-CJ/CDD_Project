/** KDS board rendering and order actions. */
const KitchenDisplay = {
  loading: false,
  refreshTimer: null,
  clockTimer: null,

  init() {
    if (!Auth.checkAuthGuard(["kitchen_staff", "restaurant_admin", "super_admin"])) return;

    document.getElementById("refreshQueue").addEventListener("click", () => this.loadQueue());
    document.getElementById("kdsLogout").addEventListener("click", () => API.logout());
    document.querySelector(".kds-board").addEventListener("click", event => {
      const button = event.target.closest("[data-kds-action]");
      if (button) this.applyAction(button);
    });

    WSClient.addListener(event => {
      if (["NEW_ORDER", "KITCHEN_ORDER_UPDATED", "ORDER_STATUS_CHANGED", "DELIVERY_STATUS_UPDATED"].includes(event.event)) {
        this.loadQueue();
      }
    });

    API.getMe().then(user => {
      const heading = document.querySelector(".kds-heading p");
      if (heading && user.full_name) heading.textContent = `Signed in as ${user.full_name} · live order queue`;
    }).catch(() => {});

    this.setClock();
    this.clockTimer = window.setInterval(() => this.setClock(), 30000);
    this.loadQueue();
    this.refreshTimer = window.setInterval(() => this.loadQueue(), 15000);
  },

  setClock() {
    const clock = document.getElementById("kdsClock");
    if (!clock) return;
    const now = new Date();
    clock.dateTime = now.toISOString();
    clock.textContent = new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium", timeStyle: "short"
    }).format(now);
  },

  async loadQueue() {
    if (this.loading) return;
    this.loading = true;
    const refresh = document.getElementById("refreshQueue");
    refresh.disabled = true;
    try {
      const orders = await API.getKitchenQueue(null, true);
      document.getElementById("queueUpdatedAt").classList.remove("text-danger");
      const lanes = {
        pending: "laneNew",
        confirmed: "laneProgress",
        preparing: "laneProgress",
        ready: "laneReady",
        delivered: "laneCompleted"
      };
      const grouped = { laneNew: [], laneProgress: [], laneReady: [], laneCompleted: [] };
      orders.forEach(order => {
        const laneId = lanes[order.status];
        if (laneId) grouped[laneId].push(order);
      });

      Object.entries(grouped).forEach(([laneId, laneOrders]) => {
        const lane = document.getElementById(laneId);
        lane.innerHTML = laneOrders.length
          ? laneOrders.map(order => this.renderCard(order)).join("")
          : '<p class="kds-empty">No orders in this lane</p>';
      });

      document.getElementById("countNew").textContent = grouped.laneNew.length;
      document.getElementById("countProgress").textContent = grouped.laneProgress.length;
      document.getElementById("countReady").textContent = grouped.laneReady.length;
      document.getElementById("countCompleted").textContent = grouped.laneCompleted.length;
      document.getElementById("queueUpdatedAt").textContent = `Updated ${new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
    } catch (error) {
      document.getElementById("queueUpdatedAt").textContent = error.message || "Could not load orders. Try refreshing.";
      document.getElementById("queueUpdatedAt").classList.add("text-danger");
    } finally {
      this.loading = false;
      refresh.disabled = false;
    }
  },

  renderCard(order) {
    const id = Number(order.order_id);
    const completed = order.status === "delivered";
    const urgencyClass = order.is_delayed ? "is-critical" : order.urgency === "HIGH" || order.urgency === "CRITICAL" ? "is-warning" : "";
    const statusLabel = completed ? "Delivered" : order.status.replaceAll("_", " ");
    const actionByStatus = {
      pending: ["accept", "Accept order", "bi-check2"],
      confirmed: ["prepare", "Start preparation", "bi-fire"],
      preparing: ["ready", "Mark ready", "bi-check2-circle"],
      ready: ["complete", "Hand over to rider", "bi-bicycle"]
    };
    const action = actionByStatus[order.status];
    const items = Array.isArray(order.items) ? order.items : [];
    const itemRows = items.map(item => `
      <li><span class="kds-quantity">${Number(item.quantity) || 0}×</span><span>${UI.escapeHtml(item.item_name)}</span></li>
    `).join("");

    return `
      <article class="kds-order-card ${urgencyClass} ${completed ? "is-completed" : ""}" data-order-id="${id}">
        <div class="kds-card-topline">
          <span class="kds-order-number">#${UI.escapeHtml(order.order_number)}</span>
          <span class="kds-status-pill">${UI.escapeHtml(statusLabel)}</span>
        </div>
        <div class="kds-card-meta">
          <span class="kds-priority">${completed ? "Completed" : `${UI.escapeHtml(order.urgency || "Normal")} priority`}</span>
          <span class="kds-elapsed" data-minutes="${Math.max(0, Math.floor(Number(order.elapsed_minutes) || 0))}">${completed ? "" : `${Math.max(0, Math.floor(Number(order.elapsed_minutes) || 0))} min waiting`}</span>
        </div>
        <div class="small text-muted mb-2">Placed ${UI.escapeHtml(UI.formatDateTime(order.created_at))}</div>
        <ul class="kds-order-items">${itemRows}</ul>
        ${order.customer_notes ? `<p class="kds-order-note"><i class="bi bi-chat-left-text" aria-hidden="true"></i><span>${UI.escapeHtml(order.customer_notes)}</span></p>` : ""}
        ${action ? `<button class="kds-action" type="button" data-kds-action="${action[0]}" data-order-id="${id}"><i class="bi ${action[2]}" aria-hidden="true"></i>${action[1]}</button>` : ""}
      </article>
    `;
  },

  async applyAction(button) {
    const orderId = Number(button.dataset.orderId);
    const action = button.dataset.kdsAction;
    if (!Number.isInteger(orderId) || !action) return;

    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      await API.updateKitchenOrder(orderId, action);
      Auth.showToast(`Order #${orderId} updated`, "success");
      await this.loadQueue();
    } catch (error) {
      Auth.showToast(error.message || "Could not update this order", "danger");
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }
};

document.addEventListener("DOMContentLoaded", () => KitchenDisplay.init());
