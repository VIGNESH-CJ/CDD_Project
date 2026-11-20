/** Restaurant menu filters, dietary suitability, allergen alerts, and safe alternatives. */
const RestaurantMenu = {
  restaurantId: null,
  restaurant: null,
  items: [],
  selectedCategory: "",

  async init() {
    const value = Number(new URLSearchParams(window.location.search).get("id"));
    this.restaurantId = Number.isInteger(value) && value > 0 ? value : 1;

    document.getElementById("menuItemSearch").addEventListener("input", () => this.render());
    document.getElementById("dietaryFilter").addEventListener("change", () => this.render());
    document.getElementById("allergenFilter").addEventListener("input", () => this.render());
    document.getElementById("safetyFilter").addEventListener("change", () => this.render());
    document.getElementById("vegFilterSwitch").addEventListener("change", () => this.render());

    // Quick allergen pills
    const pillsContainer = document.getElementById("allergenQuickPills");
    if (pillsContainer) {
      pillsContainer.addEventListener("click", event => {
        const btn = event.target.closest("[data-allergen]");
        if (!btn) return;
        const alg = btn.dataset.allergen;
        const input = document.getElementById("allergenFilter");
        const currentTerms = input.value.split(/[,;|]/).map(t => t.trim().toLowerCase()).filter(Boolean);
        const idx = currentTerms.indexOf(alg.toLowerCase());
        if (idx >= 0) {
          currentTerms.splice(idx, 1);
          btn.classList.remove("btn-danger", "text-white");
          btn.classList.add("btn-outline-secondary");
        } else {
          currentTerms.push(alg);
          btn.classList.remove("btn-outline-secondary");
          btn.classList.add("btn-danger", "text-white");
        }
        input.value = currentTerms.join(", ");
        this.render();
      });
    }

    document.getElementById("categoryTabs").addEventListener("click", event => {
      const button = event.target.closest("[data-category]");
      if (!button) return;
      this.selectedCategory = button.dataset.category;
      document.querySelectorAll("#categoryTabs [data-category]").forEach(tab => {
        tab.setAttribute("aria-pressed", String(tab === button));
        tab.classList.toggle("active", tab === button);
        tab.classList.toggle("btn-dark", tab === button);
      });
      this.render();
    });

    document.getElementById("menuItemsGrid").addEventListener("click", event => {
      const button = event.target.closest("[data-add-item]");
      if (button) Cart.addItem(Number(button.dataset.addItem), 1);
    });

    await this.loadUserPreferences();
    await this.load();
  },

  async loadUserPreferences() {
    try {
      const user = API.getUser();
      if (!user) return;
      const pref = await API.getPreferences();
      if (!pref) return;

      const dietarySelect = document.getElementById("dietaryFilter");
      if (dietarySelect && pref.dietary_preference) {
        const val = pref.dietary_preference.toLowerCase();
        if (["veg", "vegetarian"].includes(val)) dietarySelect.value = "vegetarian";
        else if (val === "vegan") dietarySelect.value = "vegan";
        else if (val === "jain") dietarySelect.value = "jain";
        else if (val.includes("gluten")) dietarySelect.value = "gluten-free";
        else if (val.includes("dairy")) dietarySelect.value = "dairy-free";
      }

      const allergenInput = document.getElementById("allergenFilter");
      if (allergenInput && pref.allergy_info && !["none", "n/a", "no allergies"].includes(pref.allergy_info.toLowerCase())) {
        allergenInput.value = pref.allergy_info;
      }

      const vegSwitch = document.getElementById("vegFilterSwitch");
      if (vegSwitch && ["veg", "vegetarian"].includes((pref.dietary_preference || "").toLowerCase())) {
        vegSwitch.checked = true;
      }

      const badge = document.getElementById("profileAutoAppliedBadge");
      if (badge && (pref.dietary_preference || pref.allergy_info)) {
        badge.classList.remove("d-none");
      }
    } catch {
      // Guest user or no preferences
    }
  },

  async load() {
    const hero = document.getElementById("restaurantHero");
    const grid = document.getElementById("menuItemsGrid");
    try {
      const data = await API.getRestaurantDetails(this.restaurantId);
      this.restaurant = data.restaurant;
      this.items = Array.isArray(data.menu_items) ? data.menu_items : [];
      this.renderHero();
      this.renderCategories();
      this.render();
    } catch (error) {
      UI.setError(hero, error, "");
      UI.setError(grid, error, "");
    }
  },

  renderHero() {
    const restaurant = this.restaurant;
    const image = UI.imageUrl(restaurant.image_url);
    document.getElementById("restaurantHero").innerHTML = `
      <div class="container py-4 py-lg-5">
        <nav aria-label="Breadcrumb"><ol class="breadcrumb mb-4">
          <li class="breadcrumb-item"><a href="/">Home</a></li>
          <li class="breadcrumb-item"><a href="/pages/restaurants.html">Restaurants</a></li>
          <li class="breadcrumb-item active" aria-current="page">${UI.escapeHtml(restaurant.name)}</li>
        </ol></nav>
        <div class="row align-items-center gy-4">
          <div class="col-md-8">
            <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
              <h1 class="display-6 fw-bold mb-0" id="restaurantName">${UI.escapeHtml(restaurant.name)}</h1>
              ${restaurant.is_pure_veg ? '<span class="badge bg-success rounded-pill">Pure vegetarian kitchen</span>' : ""}
            </div>
            <p class="text-secondary mb-2">${UI.escapeHtml(restaurant.cuisine_type)} · ${UI.escapeHtml(restaurant.address)}, ${UI.escapeHtml(restaurant.city)}</p>
            <p class="small text-light opacity-75 restaurant-description">${UI.escapeHtml(restaurant.description)}</p>
            <div class="d-flex flex-wrap gap-3 align-items-center">
              <span class="badge-rating"><i class="bi bi-star-fill text-warning me-1" aria-hidden="true"></i>${Number(restaurant.rating || 0).toFixed(1)} (${Number(restaurant.total_reviews || 0)} ratings)</span>
              <span class="small"><i class="bi bi-clock me-1 text-warning" aria-hidden="true"></i>${Number(restaurant.delivery_time_mins || 0)} min delivery</span>
              <span class="small">${UI.currency(restaurant.cost_for_two)} for two</span>
            </div>
          </div>
          <div class="col-md-4 text-md-end">${image ? `<img src="${UI.escapeHtml(image)}" alt="${UI.escapeHtml(restaurant.name)}" class="restaurant-hero-image">` : ""}</div>
        </div>
      </div>`;
  },

  renderCategories() {
    const categories = [...new Set(this.items.map(item => item.category?.name).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    const tabs = [{ name: "All dishes", value: "" }, ...categories.map(name => ({ name, value: name }))];
    document.getElementById("categoryTabs").innerHTML = tabs.map((tab, index) => `
      <button class="btn btn-sm btn-light text-start fw-semibold ${index === 0 ? "active btn-dark" : ""}" type="button" data-category="${UI.escapeHtml(tab.value)}" aria-pressed="${index === 0}">${UI.escapeHtml(tab.name)}</button>
    `).join("");
  },

  suitability(item, dietaryChoice, allergyTerms) {
    const details = `${item.allergens || ""} ${item.ingredients || ""}`.toLocaleLowerCase();
    const tags = String(item.dietary_tags || "").toLocaleLowerCase().replaceAll("-", " ");
    const hasDietaryTag = preference => new RegExp(`(^|[^a-z])${preference}([^a-z]|$)`, "i").test(tags);

    // Allergen synonyms expansion
    const synonymMap = {
      nut: ["nut", "nuts", "peanut", "peanuts", "cashew", "cashews", "almond", "almonds", "walnut", "walnuts"],
      nuts: ["nut", "nuts", "peanut", "peanuts", "cashew", "cashews", "almond", "almonds", "walnut", "walnuts"],
      peanut: ["peanut", "peanuts", "groundnut"],
      peanuts: ["peanut", "peanuts", "groundnut"],
      dairy: ["dairy", "milk", "butter", "cheese", "paneer", "cream", "ghee", "curd"],
      milk: ["dairy", "milk", "butter", "cheese", "paneer", "cream", "ghee", "curd"],
      gluten: ["gluten", "wheat", "maida", "flour", "atta", "bread"],
      wheat: ["gluten", "wheat", "maida", "flour", "atta"],
      egg: ["egg", "eggs", "mayonnaise"],
      eggs: ["egg", "eggs", "mayonnaise"],
      soy: ["soy", "soya", "tofu"],
      shellfish: ["shellfish", "prawn", "prawns", "shrimp", "crab", "lobster"]
    };

    const matchedAllergens = allergyTerms.filter(term => {
      const syns = synonymMap[term] || [term];
      return syns.some(s => {
        const escaped = s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        return new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, "i").test(details);
      });
    });

    let unsuitableReason = "";
    let isCustomizable = false;

    if (dietaryChoice === "vegetarian" && !item.is_veg) {
      unsuitableReason = "Contains non-vegetarian ingredients";
    }
    if (["vegan", "jain"].includes(dietaryChoice)) {
      if (!item.is_veg) unsuitableReason = "Does not match the selected dietary preference";
      else if (!hasDietaryTag(dietaryChoice)) unsuitableReason = `Not certified ${dietaryChoice}`;
    }
    if (dietaryChoice === "gluten-free") {
      const glutenHits = ["gluten", "wheat", "maida", "flour"].filter(g => new RegExp(`(^|[^a-z0-9])${g}([^a-z0-9]|$)`, "i").test(details));
      if (glutenHits.length) unsuitableReason = `Contains gluten (${glutenHits.join(", ")})`;
    }
    if (dietaryChoice === "dairy-free") {
      const dairyHits = ["dairy", "milk", "cheese", "paneer", "butter", "ghee", "cream"].filter(d => new RegExp(`(^|[^a-z0-9])${d}([^a-z0-9]|$)`, "i").test(details));
      if (dairyHits.length) unsuitableReason = `Contains dairy (${dairyHits.join(", ")})`;
    }

    if (matchedAllergens.length) {
      const dishName = item.name.toLowerCase();
      const isCoreIngredient = ["paneer", "cheese", "peanut", "egg", "chicken", "fish"].some(c => dishName.includes(c));
      const isGarnishOnly = ["cashew", "almond", "nuts", "butter"].some(g => (item.ingredients || "").toLowerCase().includes(g));

      if (isGarnishOnly && !isCoreIngredient && !unsuitableReason) {
        isCustomizable = true;
      } else {
        unsuitableReason = `Contains allergen: ${matchedAllergens.join(", ")}`;
      }
    }

    if (unsuitableReason) {
      return {
        state: "unsuitable",
        label: "Unsuitable",
        detail: unsuitableReason,
        matchedAllergens
      };
    }

    if (isCustomizable) {
      return {
        state: "customizable",
        label: "Customizable",
        detail: `Contains ${matchedAllergens.join(", ")} as optional topping/garnish (request kitchen to omit)`,
        matchedAllergens
      };
    }

    return {
      state: "suitable",
      label: "Suitable",
      detail: "No conflict found with your dietary and allergen preferences",
      matchedAllergens: []
    };
  },

  findSafeAlternatives(unsuitableItem, dietaryChoice, allergyTerms) {
    // Look for dishes in the same restaurant that are suitable
    const suitableItems = this.items.filter(it => {
      if (it.id === unsuitableItem.id) return false;
      const suit = this.suitability(it, dietaryChoice, allergyTerms);
      return suit.state === "suitable";
    });

    // 1. Same category first
    const sameCat = suitableItems.filter(it => it.category_id === unsuitableItem.category_id);
    if (sameCat.length >= 2) return sameCat.slice(0, 2);

    // 2. Mix of same category and other categories
    const otherCat = suitableItems.filter(it => it.category_id !== unsuitableItem.category_id);
    return [...sameCat, ...otherCat].slice(0, 2);
  },

  render() {
    const search = document.getElementById("menuItemSearch").value.trim().toLocaleLowerCase();
    const selectedDietaryChoice = document.getElementById("dietaryFilter").value;
    const dietaryChoice = selectedDietaryChoice === "any" ? "" : selectedDietaryChoice;
    const allergyTerms = document.getElementById("allergenFilter").value
      .split(/[,;|]/).map(term => term.trim().toLocaleLowerCase()).filter(Boolean);
    const safetyFilter = document.getElementById("safetyFilter").value;
    const vegetarianOnly = document.getElementById("vegFilterSwitch").checked;

    const filtered = this.items.filter(item => {
      const matchSearch = !search || [item.name, item.description, item.ingredients, item.category?.name]
        .some(value => String(value || "").toLocaleLowerCase().includes(search));
      const matchCategory = !this.selectedCategory || item.category?.name === this.selectedCategory;
      const suitability = this.suitability(item, dietaryChoice, allergyTerms);
      const matchSafety = safetyFilter === "all"
        || (safetyFilter === "hide-unsuitable" && suitability.state !== "unsuitable")
        || suitability.state === safetyFilter;
      return matchSearch && matchCategory && matchSafety && (!vegetarianOnly || item.is_veg);
    });

    document.getElementById("menuCount").textContent = `${filtered.length} of ${this.items.length} dishes`;
    const grid = document.getElementById("menuItemsGrid");
    UI.clearBusy(grid);
    if (!filtered.length) {
      UI.setEmpty(grid, "No dishes match these filters", "Try changing your search or dietary settings.");
      return;
    }

    grid.innerHTML = filtered.map(item => {
      const status = this.suitability(item, dietaryChoice, allergyTerms);
      const image = UI.imageUrl(item.image_url);
      const price = Number(item.discount_price || item.price || 0);
      const description = item.description || "Freshly prepared by the restaurant kitchen.";

      let statusBadgeClass = "is-suitable";
      let statusIcon = "bi-check-circle-fill text-success";
      if (status.state === "unsuitable") {
        statusBadgeClass = "is-unsuitable";
        statusIcon = "bi-exclamation-octagon-fill text-danger";
      } else if (status.state === "customizable") {
        statusBadgeClass = "is-customizable";
        statusIcon = "bi-exclamation-triangle-fill text-warning";
      }

      // Feature 8: Suggest safe alternatives for unsuitable dishes
      let alternativesHtml = "";
      if (status.state === "unsuitable") {
        const alternatives = this.findSafeAlternatives(item, dietaryChoice, allergyTerms);
        if (alternatives.length > 0) {
          alternativesHtml = `
            <div class="dietary-alternatives-card">
              <div class="small fw-bold text-success mb-2 d-flex align-items-center">
                <i class="bi bi-stars text-warning me-1"></i>Safe Alternative Dishes:
              </div>
              <div class="d-flex flex-column gap-2">
                ${alternatives.map(alt => `
                  <div class="dietary-alt-item">
                    <div class="d-flex align-items-center gap-2">
                      <span class="${alt.is_veg ? 'veg-indicator' : 'nonveg-indicator'}"></span>
                      <div>
                        <span class="small fw-bold d-block text-dark">${UI.escapeHtml(alt.name)}</span>
                        <span class="brand-orange small fw-semibold">${UI.currency(alt.price)}</span>
                      </div>
                    </div>
                    <button class="btn btn-sm btn-outline-success py-0 px-2" type="button" data-add-item="${Number(alt.id)}" aria-label="Add alternative ${UI.escapeHtml(alt.name)} to cart">
                      + Add Safe Dish
                    </button>
                  </div>
                `).join("")}
              </div>
            </div>
          `;
        }
      }

      return `
        <div class="col-md-6">
          <article class="card menu-item-card h-100 border-0 shadow-sm rounded-4 p-3 bg-white">
            <div class="d-flex gap-3">
              <div class="menu-item-detail flex-grow-1">
                <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
                  <span class="${item.is_veg ? "veg-indicator" : "nonveg-indicator"}" aria-label="${item.is_veg ? "Vegetarian" : "Non-vegetarian"}"></span>
                  ${item.is_bestseller ? '<span class="badge bg-danger rounded-pill">Bestseller</span>' : ""}
                  <span class="small text-muted"><i class="bi bi-clock me-1" aria-hidden="true"></i>${Number(item.prep_time_minutes || 0)} min</span>
                </div>
                <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
                  <h2 class="h6 fw-bold mb-0">${UI.escapeHtml(item.name)}</h2>
                  <span class="food-safety-pill ${statusBadgeClass}" title="${UI.escapeHtml(status.detail)}">
                    <i class="bi ${statusIcon} me-1"></i>${UI.escapeHtml(status.label)}
                  </span>
                </div>
                <p class="small text-muted mb-2 menu-item-description">${UI.escapeHtml(description)}</p>
                <div class="menu-item-meta text-secondary"><strong>Ingredients:</strong> ${UI.escapeHtml(item.ingredients || "Not listed")}</div>
                ${item.allergens ? `<div class="menu-item-meta text-danger mt-1"><strong>Declared allergens:</strong> ${UI.escapeHtml(item.allergens)}</div>` : ""}
                ${status.state !== "suitable" ? `<div class="small ${status.state === 'unsuitable' ? 'text-danger' : 'text-warning'} fw-semibold mt-1"><i class="bi bi-info-circle me-1"></i>${UI.escapeHtml(status.detail)}</div>` : ""}
                
                ${alternativesHtml}

                <div class="d-flex justify-content-between align-items-center mt-3 pt-2 border-top">
                  <span class="brand-orange fw-bold">${UI.currency(price)}${item.discount_price ? `<span class="text-muted text-decoration-line-through small ms-1">${UI.currency(item.price)}</span>` : ""}</span>
                  <button class="btn btn-sm ${status.state === 'unsuitable' ? 'btn-outline-danger' : 'btn-primary-orange'}" type="button" data-add-item="${Number(item.id)}" aria-label="Add ${UI.escapeHtml(item.name)} to cart">
                    ${status.state === 'unsuitable' ? 'Add Anyway' : 'Add to cart'}
                  </button>
                </div>
              </div>
              ${image ? `<img src="${UI.escapeHtml(image)}" alt="${UI.escapeHtml(item.name)}" class="menu-item-image rounded-3" loading="lazy">` : ""}
            </div>
          </article>
        </div>`;
    }).join("");
  }
};

document.addEventListener("DOMContentLoaded", () => RestaurantMenu.init());
