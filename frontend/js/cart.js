/**
 * AI Foodie - Shopping Cart & Checkout Manager
 */

const Cart = {
  activeCoupon: null,

  async updateBadge() {
    const badgeEl = document.getElementById("cartBadgeCount");
    if (!badgeEl) return;

    if (!API.getToken()) {
      badgeEl.textContent = "0";
      badgeEl.classList.add("d-none");
      return;
    }

    try {
      const cart = await API.getCart();
      const count = cart.item_count || 0;
      badgeEl.textContent = count;
      badgeEl.classList.toggle("d-none", count === 0);
    } catch {
      badgeEl.textContent = "0";
      badgeEl.classList.add("d-none");
    }
  },

  async addItem(menuItemId, quantity = 1, forceReplace = false) {
    if (!API.getToken()) {
      Auth.showToast("Please log in to add items to your cart", "warning");
      setTimeout(() => {
        window.location.href = "/pages/login.html";
      }, 900);
      return;
    }

    try {
      await API.addToCart(menuItemId, quantity, forceReplace);
      Auth.showToast(forceReplace ? "Cart updated with new restaurant item! 🛒" : "Item added to cart! 🛒", "success");
      await this.updateBadge();
      if (typeof this.renderCartPage === "function" && document.getElementById("cartItemsList")) {
        await this.renderCartPage();
      }
    } catch (err) {
      const msg = err.message || "";
      if (msg.includes("another restaurant") || msg.includes("Discard and add")) {
        this.showReplaceCartModal(menuItemId, quantity, msg);
      } else {
        Auth.showToast(msg || "Failed to add item to cart", "danger");
      }
    }
  },

  showReplaceCartModal(menuItemId, quantity, message) {
    let modalEl = document.getElementById("replaceCartModal");
    if (!modalEl) {
      const modalHtml = `
        <div class="modal fade replace-cart-modal" id="replaceCartModal" tabindex="-1" aria-hidden="true">
          <div class="modal-dialog modal-dialog-centered replace-cart-dialog">
            <div class="modal-content border-0 shadow-lg rounded-4 overflow-hidden">
              <div class="modal-header border-0 pb-0 pt-4 px-4 d-flex justify-content-between align-items-start">
                <div class="d-flex align-items-center gap-2">
                  <div class="bg-warning-subtle text-warning p-2 rounded-3 fs-4 d-flex align-items-center justify-content-center replace-cart-icon">
                    <i class="bi bi-cart-x text-warning fs-4"></i>
                  </div>
                  <div>
                    <h5 class="modal-title fw-bold fs-5 mb-0">Replace Cart Items?</h5>
                    <small class="text-muted">A single order is from one restaurant</small>
                  </div>
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
              </div>
              <div class="modal-body px-4 py-3">
                <p id="replaceCartModalMsg" class="text-muted mb-0 replace-cart-message"></p>
              </div>
              <div class="modal-footer border-0 pt-0 pb-4 px-4 gap-2">
                <button type="button" class="btn btn-light rounded-3 px-3 py-2 flex-grow-1 fw-semibold" data-bs-dismiss="modal">
                  Keep Existing Cart
                </button>
                <button type="button" class="btn btn-primary-orange rounded-3 px-3 py-2 flex-grow-1 fw-semibold text-white" id="confirmReplaceCartBtn">
                  <i class="bi bi-arrow-repeat me-1"></i> Discard & Add
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
      document.body.insertAdjacentHTML("beforeend", modalHtml);
      modalEl = document.getElementById("replaceCartModal");
    }

    const msgEl = document.getElementById("replaceCartModalMsg");
    if (msgEl) {
      msgEl.textContent = message || "Your cart already contains items from another restaurant. Discard previous items and add this dish?";
    }

    const confirmBtn = document.getElementById("confirmReplaceCartBtn");
    if (confirmBtn) {
      const newBtn = confirmBtn.cloneNode(true);
      confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
      newBtn.addEventListener("click", async () => {
        if (window.bootstrap) {
          const bsModal = bootstrap.Modal.getInstance(modalEl);
          if (bsModal) bsModal.hide();
        }
        await Cart.addItem(menuItemId, quantity, true);
      });
    }

    if (window.bootstrap && bootstrap.Modal) {
      const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
      bsModal.show();
    } else {
      if (confirm((message || "Your cart contains items from another restaurant.") + "\n\nDiscard previous cart and add this item?")) {
        Cart.addItem(menuItemId, quantity, true);
      }
    }
  },

  async renderCartPage() {
    const container = document.getElementById("cartItemsList");
    const summaryContainer = document.getElementById("cartSummaryContainer");
    if (!container || !summaryContainer) return;

    if (!API.getToken()) {
      container.innerHTML = `
        <div class="text-center py-5">
          <i class="bi bi-person-lock fs-1 text-muted"></i>
          <h4 class="mt-3">Please Sign In</h4>
          <p class="text-muted">Log in to view and checkout items in your cart.</p>
          <a href="/pages/login.html" class="btn btn-primary-orange mt-2">Log In</a>
        </div>
      `;
      summaryContainer.innerHTML = "";
      return;
    }

    try {
      const cart = await API.getCart();
      if (!cart.items || cart.items.length === 0) {
        container.innerHTML = `
          <div class="text-center py-5">
            <i class="bi bi-cart-x fs-1 text-muted"></i>
            <h4 class="mt-3">Your Cart is Empty</h4>
            <p class="text-muted">Looks like you haven't added any delicious food yet.</p>
            <a href="/pages/restaurants.html" class="btn btn-primary-orange mt-2">Explore Restaurants</a>
          </div>
        `;
        summaryContainer.innerHTML = "";
        return;
      }

      container.innerHTML = cart.items.map(item => `
        <div class="card border-0 shadow-sm mb-3 rounded-4 p-3">
          <div class="d-flex align-items-center gap-3">
            <img src="${UI.imageUrl(item.image_url) || '/static/assets/food-placeholder.svg'}" alt="${UI.escapeHtml(item.name)}" class="rounded-3 cart-item-image" loading="lazy">
            <div class="flex-grow-1">
              <div class="d-flex align-items-center gap-2">
                <span class="${item.is_veg ? 'veg-indicator' : 'nonveg-indicator'}"></span>
                <h6 class="mb-0 fw-bold">${UI.escapeHtml(item.name)}</h6>
              </div>
              <div class="text-muted small mt-1">${UI.currency(item.price)} each</div>
              <div class="fw-bold brand-orange mt-1">Total: ${UI.currency(item.total_price)}</div>
            </div>
            <div class="d-flex align-items-center gap-2 border rounded-3 p-1">
              <button class="btn btn-sm btn-light border-0 fw-bold" type="button" data-cart-action="quantity" data-item-id="${Number(item.menu_item_id)}" data-quantity="${Number(item.quantity) - 1}" aria-label="Remove one ${UI.escapeHtml(item.name)}">−</button>
              <span class="fw-bold px-2">${item.quantity}</span>
              <button class="btn btn-sm btn-light border-0 fw-bold" type="button" data-cart-action="quantity" data-item-id="${Number(item.menu_item_id)}" data-quantity="${Number(item.quantity) + 1}" aria-label="Add one ${UI.escapeHtml(item.name)}">+</button>
            </div>
            <button class="btn btn-link text-danger p-0 ms-2" type="button" data-cart-action="remove" data-item-id="${Number(item.menu_item_id)}" aria-label="Remove ${UI.escapeHtml(item.name)} from cart">
              <i class="bi bi-trash fs-5"></i>
            </button>
          </div>
        </div>
      `).join('');

      // Calculate discount if coupon applied
      let discountAmount = 0.0;
      if (this.activeCoupon) {
        discountAmount = this.activeCoupon.discount_amount || 0.0;
      }

      const finalTotal = Math.max(0, cart.subtotal + cart.tax + cart.delivery_fee - discountAmount);

      summaryContainer.innerHTML = `
        <div class="card border-0 shadow-sm rounded-4 p-4 sticky-top cart-summary-sticky">
          <h5 class="fw-bold mb-3">Order Summary</h5>
          
          <!-- Promo Code Box -->
          <div class="mb-4">
            <label class="form-label small fw-bold text-muted">Promo Code / Coupon</label>
            <div class="input-group">
              <input type="text" id="couponCodeInput" class="form-control text-uppercase" placeholder="e.g. AIFOODIE20" value="${UI.escapeHtml(this.activeCoupon?.coupon_code || '')}">
              <button class="btn btn-dark" type="button" data-cart-action="coupon">Apply</button>
            </div>
            <div class="small text-muted mt-1">Available demo coupons: <strong class="text-primary">AIFOODIE20</strong> (20% off), <strong class="text-primary">WELCOME50</strong> (₹50 off)</div>
            ${this.activeCoupon ? `<div class="badge bg-success-subtle text-success border border-success mt-2 p-2 w-100 text-start">✓ ${UI.escapeHtml(this.activeCoupon.message)}</div>` : ''}
          </div>

          <!-- Price Breakdown -->
          <div class="d-flex justify-content-between mb-2">
            <span class="text-muted">Subtotal (${cart.item_count} items)</span>
            <span class="fw-semibold">₹${cart.subtotal.toFixed(2)}</span>
          </div>
          <div class="d-flex justify-content-between mb-2">
            <span class="text-muted">GST & Restaurant Tax (5%)</span>
            <span class="fw-semibold">₹${cart.tax.toFixed(2)}</span>
          </div>
          <div class="d-flex justify-content-between mb-2">
            <span class="text-muted">Standard Delivery Fee</span>
            <span class="fw-semibold">₹${cart.delivery_fee.toFixed(2)}</span>
          </div>
          ${discountAmount > 0 ? `
            <div class="d-flex justify-content-between mb-2 text-success">
              <span>Coupon Discount</span>
              <span class="fw-bold">- ₹${discountAmount.toFixed(2)}</span>
            </div>
          ` : ''}
          <hr>
          <div class="d-flex justify-content-between mb-4 fs-5 fw-bold">
            <span>To Pay</span>
            <span class="brand-orange">₹${finalTotal.toFixed(2)}</span>
          </div>

          <!-- Address selection -->
          <div class="mb-3">
            <label class="form-label small fw-bold text-muted">Delivery Address</label>
            <textarea id="orderAddress" class="form-control" rows="2" placeholder="Enter flat/house no, street, landmark...">Flat 402, Green Glen Layout, Bellandur, Bangalore - 560103</textarea>
          </div>

          <!-- Payment Method -->
          <div class="mb-4">
            <label class="form-label small fw-bold text-muted">Payment Method</label>
            <div class="form-check p-2 border rounded-3 mb-2">
              <input class="form-check-input ms-1" type="radio" name="paymentMethod" id="payCOD" value="cod" checked>
              <label class="form-check-label ms-2 fw-semibold" for="payCOD">
                💵 Cash on Delivery (COD)
              </label>
            </div>
            <div class="form-check p-2 border rounded-3">
              <input class="form-check-input ms-1" type="radio" name="paymentMethod" id="payOnline" value="online">
              <label class="form-check-label ms-2 fw-semibold" for="payOnline">
                💳 Verified Sandbox Payment Gateway (Cards/UPI/Netbanking)
              </label>
            </div>
          </div>

          <!-- Special instructions -->
          <div class="mb-4">
            <input type="text" id="orderNotes" class="form-control form-control-sm" placeholder="Cooking or delivery instructions (optional)">
          </div>

          <button class="btn btn-primary-orange w-100 py-3 fs-6" type="button" data-cart-action="checkout" data-restaurant-id="${Number(cart.restaurant_id)}">
            Place Order • ${UI.currency(finalTotal)}
          </button>
        </div>
      `;
    } catch (err) {
      UI.setError(container, err, "Retry");
    }
  },

  async clearCart() {
    try {
      await API.clearCart();
      this.activeCoupon = null;
      await this.updateBadge();
      await this.renderCartPage();
      Auth.showToast("Your cart is empty now.", "info");
    } catch (err) {
      Auth.showToast(err.message || "Could not clear your cart.", "danger");
    }
  },

  async changeQty(menuItemId, newQty) {
    try {
      await API.updateCart(menuItemId, newQty);
      await this.updateBadge();
      await this.renderCartPage();
    } catch (err) {
      Auth.showToast(err.message, "danger");
    }
  },

  async removeItem(menuItemId) {
    try {
      await API.removeFromCart(menuItemId);
      Auth.showToast("Item removed from cart", "info");
      await this.updateBadge();
      await this.renderCartPage();
    } catch (err) {
      Auth.showToast(err.message, "danger");
    }
  },

  async applyCoupon(subtotal = null) {
    const input = document.getElementById("couponCodeInput");
    if (!input || !input.value.trim()) {
      Auth.showToast("Please enter a coupon code", "warning");
      return;
    }
    const code = input.value.trim();
    try {
      const cart = subtotal === null ? await API.getCart() : null;
      const currentSubtotal = subtotal === null ? cart.subtotal : subtotal;
      const res = await API.validateCoupon(code, currentSubtotal);
      this.activeCoupon = res;
      Auth.showToast(res.message, "success");
      await this.renderCartPage();
    } catch (err) {
      this.activeCoupon = null;
      Auth.showToast(err.message, "danger");
    }
  },

  async checkout(restaurantId) {
    const address = document.getElementById("orderAddress")?.value?.trim();
    if (!address) {
      Auth.showToast("Please enter delivery address", "warning");
      return;
    }

    const paymentMethodEl = document.querySelector('input[name="paymentMethod"]:checked');
    const paymentMethod = paymentMethodEl ? paymentMethodEl.value : "cod";
    const notes = document.getElementById("orderNotes")?.value?.trim() || "";

    try {
      const cart = await API.getCart();
      const itemsPayload = cart.items.map(i => ({
        menu_item_id: i.menu_item_id,
        quantity: i.quantity
      }));

      const payload = {
        restaurant_id: restaurantId || cart.restaurant_id || 1,
        items: itemsPayload,
        delivery_address: address,
        coupon_code: this.activeCoupon ? this.activeCoupon.coupon_code : null,
        payment_method: paymentMethod,
        customer_notes: notes
      };

      if (paymentMethod !== "cod") {
        const checkout = await API.createPaymentCheckout(
          Math.max(0, Number(cart.subtotal) + Number(cart.delivery_fee || 30) + Number(cart.tax || 0))
        );
        if (checkout.checkout_url) {
          localStorage.setItem("aifoodie_pending_order", JSON.stringify(payload));
          window.location.assign(checkout.checkout_url);
          return;
        }
        payload.payment_reference = checkout.reference;
      }

      Auth.showToast("Placing your order...", "info");
      const orderResp = await API.createOrder(payload);

      Auth.showToast(`Order #${orderResp.order_number} confirmed! 🎉`, "success");
      this.activeCoupon = null;
      await this.updateBadge();

      // Redirect to Order Tracking page
      setTimeout(() => {
        window.location.href = `/pages/order-tracking.html?order_id=${orderResp.order_id}`;
      }, 1000);
    } catch (err) {
      Auth.showToast(err.message || "Failed to place order", "danger");
    }
  }
};

document.addEventListener("DOMContentLoaded", () => {
  Cart.updateBadge();
  if (document.getElementById("cartItemsList")) Cart.renderCartPage();
  const params = new URLSearchParams(window.location.search);
  if (params.get("payment") === "success") {
    const sessionId = params.get("session_id");
    const pending = localStorage.getItem("aifoodie_pending_order");
    if (!sessionId || !pending) return;
    try {
      const payload = JSON.parse(pending);
      payload.payment_reference = sessionId;
      Auth.showToast("Payment confirmed. Placing your order...", "info");
      API.createOrder(payload).then(orderResp => {
        localStorage.removeItem("aifoodie_pending_order");
        Cart.activeCoupon = null;
        Cart.updateBadge();
        window.location.href = `/pages/order-tracking.html?order_id=${orderResp.order_id}`;
      }).catch(err => {
        Auth.showToast(err.message || "Payment succeeded but order creation failed", "danger");
      });
    } catch (error) {
      Auth.showToast("Could not restore the pending order", "danger");
    }
  }
});

document.addEventListener("click", event => {
  const button = event.target.closest("[data-cart-action]");
  if (!button) return;
  const itemId = Number(button.dataset.itemId);
  switch (button.dataset.cartAction) {
    case "quantity":
      if (Number.isSafeInteger(itemId) && itemId > 0) Cart.changeQty(itemId, Number(button.dataset.quantity));
      break;
    case "remove":
      if (Number.isSafeInteger(itemId) && itemId > 0) Cart.removeItem(itemId);
      break;
    case "coupon":
      Cart.applyCoupon();
      break;
    case "checkout": {
      const restaurantId = Number(button.dataset.restaurantId);
      if (Number.isSafeInteger(restaurantId) && restaurantId > 0) Cart.checkout(restaurantId);
      break;
    }
  }
});

document.addEventListener("click", event => {
  if (event.target.closest('[data-action="clear-cart"]')) Cart.clearCart();
  if (event.target.closest("[data-ui-retry]") && document.getElementById("cartItemsList")) Cart.renderCartPage();
});
