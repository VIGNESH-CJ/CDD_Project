/**
 * AI Foodie - Centralized API Client
 */

const API_BASE_URL = window.location.protocol === "file:"
  ? "http://127.0.0.1:8000"
  : window.location.origin;

const API = {
  // Token management
  getToken() {
    return localStorage.getItem("aifoodie_token");
  },
  setToken(token) {
    localStorage.setItem("aifoodie_token", token);
  },
  getUser() {
    const userStr = localStorage.getItem("aifoodie_user");
    try {
      return userStr ? JSON.parse(userStr) : null;
    } catch {
      return null;
    }
  },
  setUser(user) {
    localStorage.setItem("aifoodie_user", JSON.stringify(user));
  },
  logout() {
    if (window.WSClient) window.WSClient.disconnect();
    localStorage.removeItem("aifoodie_token");
    localStorage.removeItem("aifoodie_user");
    window.location.href = "/pages/login.html";
  },

  // Base fetch wrapper
  async request(endpoint, options = {}) {
    const headers = new Headers(options.headers || {});
    const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
    if (options.body !== undefined && !isFormData && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const token = this.getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const config = {
      ...options,
      headers
    };

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
      const responseText = await response.text();
      let data = {};
      if (responseText) {
        try {
          data = JSON.parse(responseText);
        } catch {
          data = { detail: responseText };
        }
      }

      if (!response.ok) {
        const detail = Array.isArray(data.detail)
          ? data.detail.map(issue => issue.msg || "Invalid request").join("; ")
          : data.detail || data.message;
        throw new Error(detail || `Request failed with status ${response.status}`);
      }
      return data;
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  // Auth endpoints
  async login(email, password) {
    return this.request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
  },

  async register(payload) {
    return this.request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async demoLogin(role) {
    return this.request("/api/auth/demo-login", {
      method: "POST",
      body: JSON.stringify({ role })
    });
  },

  async getMe() {
    return this.request("/api/auth/me");
  },

  // Restaurants & Menu
  async getRestaurants(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/api/restaurants${query ? '?' + query : ''}`);
  },

  async getRestaurantDetails(id) {
    return this.request(`/api/restaurants/${id}`);
  },

  async getCategories() {
    return this.request("/api/restaurants/categories/all");
  },

  async getMenuItems(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/api/menu${query ? '?' + query : ''}`);
  },

  async getMenuItem(id) {
    return this.request(`/api/menu/${id}`);
  },

  async toggleMenuItemAvailability(id) {
    return this.request(`/api/menu/item/${id}/toggle-availability`, { method: "PATCH" });
  },

  // Cart
  async getCart() {
    return this.request("/api/cart");
  },

  async addToCart(menuItemId, quantity = 1, replaceCart = false) {
    return this.request("/api/cart/add", {
      method: "POST",
      body: JSON.stringify({ menu_item_id: menuItemId, quantity, replace_cart: replaceCart })
    });
  },

  async updateCart(menuItemId, quantity) {
    return this.request(`/api/cart/update?menu_item_id=${menuItemId}`, {
      method: "PUT",
      body: JSON.stringify({ quantity })
    });
  },

  async removeFromCart(menuItemId) {
    return this.request(`/api/cart/remove/${menuItemId}`, { method: "DELETE" });
  },

  async clearCart() {
    return this.request("/api/cart/clear", { method: "DELETE" });
  },

  async validateCoupon(code, subtotal) {
    return this.request("/api/cart/validate-coupon", {
      method: "POST",
      body: JSON.stringify({ code, subtotal })
    });
  },

  // Orders
  async createOrder(payload) {
    return this.request("/api/orders", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async getMyOrders() {
    return this.request("/api/orders/my-orders");
  },

  async getOrderDetails(orderId) {
    return this.request(`/api/orders/${orderId}`);
  },

  async updateOrderStatus(orderId, status, notes = "") {
    return this.request(`/api/orders/${orderId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status, notes })
    });
  },

  async reorder(orderId) {
    return this.request(`/api/orders/${orderId}/reorder`, { method: "POST" });
  },

  // Admin & Analytics
  async getManagedRestaurants() {
    return this.request("/api/admin/restaurants");
  },

  async createRestaurant(payload) {
    return this.request("/api/admin/restaurants", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async updateRestaurant(id, payload) {
    return this.request(`/api/admin/restaurants/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },

  async getAdminStats(restaurantId = null) {
    const q = restaurantId ? `?restaurant_id=${restaurantId}` : "";
    return this.request(`/api/admin/dashboard-stats${q}`);
  },

  async getRevenueAnalytics(restaurantId = null) {
    const q = restaurantId ? `?restaurant_id=${restaurantId}` : "";
    return this.request(`/api/admin/analytics/revenue${q}`);
  },

  async getPeakHoursAnalytics(restaurantId = null) {
    const q = restaurantId ? `?restaurant_id=${restaurantId}` : "";
    return this.request(`/api/admin/analytics/peak-hours${q}`);
  },

  async getBestsellersAnalytics(restaurantId = null) {
    const q = restaurantId ? `?restaurant_id=${restaurantId}` : "";
    return this.request(`/api/admin/analytics/bestsellers${q}`);
  },

  async getSalesPerformance(restaurantId = null) {
    const q = restaurantId ? `?restaurant_id=${restaurantId}` : "";
    return this.request(`/api/admin/analytics/sales-performance${q}`);
  },

  async createPaymentCheckout(amount) {
    return this.request("/api/payments/checkout", {
      method: "POST",
      body: JSON.stringify({ amount })
    });
  },

  async getAdminOrders(restaurantId = null, statusFilter = "all") {
    let q = `?status_filter=${statusFilter}`;
    if (restaurantId) q += `&restaurant_id=${restaurantId}`;
    return this.request(`/api/admin/orders${q}`);
  },

  async getInventory(restaurantId = null) {
    const q = restaurantId ? `?restaurant_id=${restaurantId}` : "";
    return this.request(`/api/admin/inventory${q}`);
  },

  async createIngredient(payload) {
    return this.request("/api/admin/inventory", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async restockIngredient(ingredientId, quantity) {
    return this.request(`/api/admin/inventory/restock?ingredient_id=${ingredientId}&quantity_to_add=${quantity}`, {
      method: "POST"
    });
  },
  async logFoodWaste(ingredientId, quantity, reason) {
    return this.request("/api/admin/waste/log", {
      method: "POST",
      body: JSON.stringify({
        ingredient_id: ingredientId,
        quantity_wasted: quantity,
        reason
      })
    });
  },

  // Kitchen KDS
  async getKitchenQueue(restaurantId = null, includeCompleted = false) {
    const params = new URLSearchParams();
    if (restaurantId) params.set("restaurant_id", restaurantId);
    if (includeCompleted) params.set("include_completed", "true");
    const q = params.toString() ? `?${params}` : "";
    return this.request(`/api/kitchen/queue${q}`);
  },

  async updateKitchenOrder(orderId, action) {
    return this.request(`/api/kitchen/orders/${orderId}/action?action=${action}`, { method: "POST" });
  },

  // Delivery
  async getAssignedDeliveries(partnerId = null) {
    const q = partnerId ? `?partner_id=${partnerId}` : "";
    return this.request(`/api/delivery/assigned-orders${q}`);
  },

  async getDeliveryEta(orderId) {
    return this.request(`/api/delivery/orders/${orderId}/eta`);
  },

  async updateDeliveryAction(orderId, action) {
    return this.request(`/api/delivery/orders/${orderId}/action?action=${action}`, { method: "POST" });
  },

  async getDeliveryStats(partnerId = null) {
    const q = partnerId ? `?partner_id=${partnerId}` : "";
    return this.request(`/api/delivery/stats${q}`);
  },

  async setDeliveryAvailability(isAvailable) {
    return this.request(`/api/delivery/availability?is_available=${isAvailable}`, { method: "PATCH" });
  },

  // Super Admin
  async getSuperAdminStats() {
    return this.request("/api/superadmin/stats");
  },

  async getSuperAdminUsers() {
    return this.request("/api/superadmin/users");
  },

  async createDeliveryPartner(payload) {
    return this.request("/api/superadmin/delivery-partners", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async toggleUserStatus(userId) {
    return this.request(`/api/superadmin/users/${userId}/toggle-status`, { method: "PATCH" });
  },

  async getSuperAdminRestaurants() {
    return this.request("/api/superadmin/restaurants");
  },

  async toggleRestaurantStatus(restId) {
    return this.request(`/api/superadmin/restaurants/${restId}/toggle-status`, { method: "PATCH" });
  },

  // AI & ML
  async getRecommendations(userId = null, restaurantId = null, limit = 6) {
    let q = `?limit=${limit}`;
    if (restaurantId) q += `&restaurant_id=${restaurantId}`;
    return this.request(`/api/ai/recommendations${q}`);
  },

  async chatWithAssistant(message, userId = null, restaurantId = null, conversationHistory = []) {
    return this.request("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message, user_id: userId, restaurant_id: restaurantId, conversation_history: conversationHistory })
    });
  },

  async getDemandForecast(restaurantId = null) {
    const q = restaurantId ? `?restaurant_id=${restaurantId}` : "";
    return this.request(`/api/ai/demand-forecast${q}`);
  },

  async getSmartInventory(restaurantId = null) {
    const q = restaurantId ? `?restaurant_id=${restaurantId}` : "";
    return this.request(`/api/ai/smart-inventory${q}`);
  }
};
