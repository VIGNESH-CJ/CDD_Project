/* Customer-facing doorway to the Smart Food Intelligence APIs. */
const SmartHub = {
  async init() {
    const signedIn = Boolean(API.getToken());
    document.getElementById("smartAuthNotice").classList.toggle("d-none", signedIn);
    this.renderCapabilities();
    if (!signedIn) return;
    this.bindEvents();
    await Promise.all([this.loadProfile(), this.loadRecommendations(), this.loadRescueOffers(), this.loadFoodMemory()]);
  },

  bindEvents() {
    document.getElementById("smartProfileForm").addEventListener("submit", event => this.saveProfile(event));
    document.getElementById("refreshSmartPicks").addEventListener("click", () => this.loadRecommendations());
    document.getElementById("refreshRescue").addEventListener("click", () => this.loadRescueOffers());
    document.getElementById("groupOrderForm").addEventListener("submit", event => this.createGroupOrder(event));
    document.getElementById("orderExperienceForm").addEventListener("submit", event => this.loadOrderExperience(event));
    document.getElementById("rescueOffers").addEventListener("click", event => {
      const button = event.target.closest("[data-reserve-offer]");
      if (button) this.reserveOffer(Number(button.dataset.reserveOffer));
    });
  },

  renderCapabilities() {
    const items = [
      "Mood Matcher", "Explainable recommendations", "Allergy Guardian", "Health-goal ordering",
      "Group ordering", "Food rescue", "Kitchen digital twin", "Availability forecast",
      "ETA breakdown", "Dynamic rider handoff", "Delay warnings", "Sustainability score",
      "Carbon-aware delivery", "Menu engineering", "Procurement planner", "Quality-risk prediction",
      "Contextual feedback", "Dish confidence", "Personal food memory", "Operations copilot"
    ];
    document.getElementById("capabilityList").innerHTML = items.map((item, index) => `<div class="col"><div class="border rounded-3 bg-light p-2"><span class="text-warning fw-bold me-1">${index + 1}.</span>${UI.escapeHtml(item)}</div></div>`).join("");
  },

  async loadProfile() {
    try {
      const profile = await API.getSmartProfile();
      document.getElementById("smartMood").value = profile.current_mood || "neutral";
      document.getElementById("smartGoal").value = profile.health_goal || "balanced";
      document.getElementById("smartBudget").value = profile.max_meal_budget || "";
    } catch (error) { Auth.showToast(error.message || "Could not load your food profile", "danger"); }
  },

  async saveProfile(event) {
    event.preventDefault();
    try {
      await API.updateSmartProfile({
        current_mood: document.getElementById("smartMood").value,
        health_goal: document.getElementById("smartGoal").value,
        max_meal_budget: Number(document.getElementById("smartBudget").value || 0)
      });
      Auth.showToast("Food profile saved", "success");
      await this.loadRecommendations();
    } catch (error) { Auth.showToast(error.message || "Could not save profile", "danger"); }
  },

  async loadRecommendations() {
    const container = document.getElementById("smartRecommendations");
    try {
      const data = await API.getSmartRecommendations();
      const picks = data.recommendations || [];
      container.innerHTML = picks.length ? picks.map(item => `
        <div class="col-md-6"><article class="border rounded-3 p-3 h-100 bg-light">
          <div class="d-flex justify-content-between gap-2"><strong>${UI.escapeHtml(item.name)}</strong><span class="badge text-bg-success">${item.dish_confidence}% confidence</span></div>
          <div class="small mt-2">${UI.escapeHtml(item.explanation)}</div>
          <div class="small text-muted mt-2"><i class="bi bi-box-seam me-1"></i>${UI.escapeHtml(item.availability_forecast.message)}</div>
          <div class="fw-bold text-dark mt-2">${UI.currency(item.price)}</div>
        </article></div>`).join("") : '<div class="col-12 text-muted small">No safe recommendations are available for the current profile.</div>';
    } catch (error) { container.innerHTML = `<div class="col-12 text-danger small">${UI.escapeHtml(error.message || "Could not load recommendations")}</div>`; }
  },

  async loadRescueOffers() {
    const container = document.getElementById("rescueOffers");
    try {
      const offers = await API.getRescueOffers();
      container.innerHTML = offers.length ? offers.map(offer => `
        <div class="col-md-6"><div class="border border-success-subtle rounded-3 p-3 h-100">
          <div class="d-flex justify-content-between gap-2"><strong>${UI.escapeHtml(offer.title)}</strong><span class="badge text-bg-success">Save ${UI.currency(offer.savings)}</span></div>
          <div class="small text-muted">${UI.escapeHtml(offer.restaurant_name)} · ${offer.quantity_remaining} left</div>
          <div class="mt-2"><del class="text-muted me-1">${UI.currency(offer.original_price)}</del><strong>${UI.currency(offer.rescue_price)}</strong></div>
          <button class="btn btn-sm btn-outline-success mt-2" data-reserve-offer="${offer.id}">Reserve pickup</button>
        </div></div>`).join("") : '<div class="col-12 text-muted small">No rescue meals right now. Check again near restaurant closing time.</div>';
    } catch (error) { container.innerHTML = `<div class="col-12 text-danger small">${UI.escapeHtml(error.message || "Could not load rescue offers")}</div>`; }
  },

  async reserveOffer(offerId) {
    try {
      const result = await API.request(`/api/smart/rescue-offers/${offerId}/reserve`, { method: "POST" });
      Auth.showToast(result.message, "success");
      await this.loadRescueOffers();
    } catch (error) { Auth.showToast(error.message || "Could not reserve this meal", "danger"); }
  },

  async loadFoodMemory() {
    const container = document.getElementById("foodMemory");
    try {
      const memory = await API.getFoodMemory();
      const dishes = memory.favorite_dishes || [];
      container.innerHTML = dishes.length ? `<div class="mb-2">${memory.orders_count} order(s) remembered</div>${dishes.map(dish => `<div class="d-flex justify-content-between border-top py-2"><span>${UI.escapeHtml(dish.name)}</span><strong>${dish.times_ordered}×</strong></div>`).join("")}` : "No food memory yet—your first order will start it.";
    } catch (error) { container.textContent = error.message || "Could not load food memory"; }
  },

  async createGroupOrder(event) {
    event.preventDefault();
    const output = document.getElementById("groupOrderResult");
    try {
      const data = await API.request("/api/smart/group-orders", { method: "POST", body: JSON.stringify({ restaurant_id: Number(document.getElementById("groupRestaurantId").value), delivery_address: document.getElementById("groupAddress").value }) });
      output.className = "small mt-3 text-success";
      output.textContent = `Invite room created. Share code: ${data.invite_code}`;
    } catch (error) { output.className = "small mt-3 text-danger"; output.textContent = error.message || "Could not create group order"; }
  },

  async loadOrderExperience(event) {
    event.preventDefault();
    const output = document.getElementById("orderExperience");
    try {
      const data = await API.getOrderExperience(Number(document.getElementById("experienceOrderId").value));
      const eta = data.eta_breakdown;
      output.innerHTML = `<div class="fw-semibold">About ${eta.estimated_total_minutes} min remaining</div><div class="mt-1">Queue ${eta.kitchen_queue_minutes}m · Prep ${eta.preparation_minutes_remaining}m · Rider ${eta.rider_assignment_minutes}m · Travel ${eta.travel_minutes}m</div><div class="mt-2">Delay risk: <strong>${data.delay_risk}%</strong> · Quality risk: <strong>${data.quality_risk}%</strong> · Carbon: <strong>${data.carbon_kg} kg</strong></div>`;
    } catch (error) { output.textContent = error.message || "Could not load order experience"; }
  }
};

document.addEventListener("DOMContentLoaded", () => SmartHub.init());
