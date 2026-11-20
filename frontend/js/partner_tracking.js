/* Rider-side Leaflet map and location publisher for assigned deliveries. */
window.PartnerTracking = (() => {
  const state = {
    map: null,
    orders: [],
    order: null,
    socket: null,
    watchId: null,
    simulation: null,
    markers: {},
    route: null,
    routeCoords: [],
    smoothPath: [],
    simIndex: 0
  };

  const token = () => localStorage.getItem("aifoodie_token");
  const status = message => {
    const el = document.getElementById("partnerGpsStatus");
    if (el) el.textContent = message;
  };
  const selected = () => state.orders.find(order => String(order.order_id) === document.getElementById("trackingOrderSelect")?.value);
  function point(lat, lon) { return [Number(lat), Number(lon)]; }

  function marker(name, coords, emoji, label) {
    if (state.markers[name]) {
      state.markers[name].setLatLng(coords);
    } else {
      state.markers[name] = L.marker(coords, {
        icon: L.divIcon({
          className: "partner-map-icon " + (name === "rider" ? "rider-pin" : name + "-pin"),
          html: `<span aria-label="${label}">${emoji}</span>`,
          iconSize: [36, 36],
          iconAnchor: [18, 18]
        })
      }).addTo(state.map).bindPopup(label);
    }
    return state.markers[name];
  }

  function densifyRoute(coordinates, targetStepCount = 140) {
    if (!coordinates || coordinates.length === 0) return [];
    if (coordinates.length === 1) return [coordinates[0]];
    const distances = [0];
    let totalDistance = 0;
    for (let i = 1; i < coordinates.length; i++) {
      const dLat = coordinates[i][0] - coordinates[i - 1][0];
      const dLon = coordinates[i][1] - coordinates[i - 1][1];
      const segDist = Math.hypot(dLat, dLon);
      totalDistance += segDist;
      distances.push(totalDistance);
    }
    if (totalDistance === 0) return new Array(targetStepCount).fill(coordinates[0]);
    const dense = [];
    const stepSize = totalDistance / (targetStepCount - 1);
    let segIndex = 0;
    for (let step = 0; step < targetStepCount; step++) {
      const targetDist = step * stepSize;
      while (segIndex < distances.length - 2 && distances[segIndex + 1] < targetDist) {
        segIndex++;
      }
      const d1 = distances[segIndex];
      const d2 = distances[segIndex + 1];
      const p1 = coordinates[segIndex];
      const p2 = coordinates[segIndex + 1];
      const segLen = d2 - d1;
      const factor = segLen > 0 ? (targetDist - d1) / segLen : 0;
      const lat = p1[0] + (p2[0] - p1[0]) * factor;
      const lon = p1[1] + (p2[1] - p1[1]) * factor;
      dense.push([Number(lat.toFixed(6)), Number(lon.toFixed(6))]);
    }
    return dense;
  }

  function generateRoadFallback(start, end) {
    const [lat1, lon1] = start;
    const [lat2, lon2] = end;
    const dLat = lat2 - lat1;
    const dLon = lon2 - lon1;
    return [
      start,
      [lat1 + dLat * 0.25, lon1 + dLon * 0.05],
      [lat1 + dLat * 0.45, lon1 + dLon * 0.40],
      [lat1 + dLat * 0.70, lon1 + dLon * 0.55],
      [lat1 + dLat * 0.85, lon1 + dLon * 0.90],
      end
    ];
  }

  async function loadAndDrawRoute(from, to) {
    if (state.route) {
      state.map.removeLayer(state.route);
      state.route = null;
    }
    let coords = null;
    try {
      const url = `https://router.project-osrm.org/route/v1/driving/${from[1]},${from[0]};${to[1]},${to[0]}?overview=full&geometries=geojson`;
      const response = await fetch(url);
      if (response.ok) {
        const result = await response.json();
        if (result.routes && result.routes.length > 0) {
          coords = result.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
        }
      }
    } catch (error) {
      console.warn("OSRM routing service unavailable, using street fallback", error);
    }

    if (!coords || coords.length < 2) {
      coords = generateRoadFallback(from, to);
    }

    state.routeCoords = coords;
    state.smoothPath = densifyRoute(coords, 140);
    state.simIndex = 0;

    state.route = L.polyline(coords, {
      color: "#f97316",
      weight: 5,
      opacity: 0.85,
      lineCap: "round",
      lineJoin: "round"
    }).addTo(state.map);
    state.map.fitBounds(state.route.getBounds(), { padding: [28, 28] });
  }

  function closeConnection() {
    if (state.watchId !== null && navigator.geolocation) navigator.geolocation.clearWatch(state.watchId);
    state.watchId = null;
    if (state.simulation) clearInterval(state.simulation);
    state.simulation = null;
    if (state.socket) state.socket.close();
    state.socket = null;
    ["startPartnerGps", "simulatePartnerGps", "stopPartnerGps"].forEach(id => {
      const button = document.getElementById(id);
      if (button) button.disabled = true;
    });
  }

  function sendLocation(lat, lon) {
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      status("Connect to an assigned order before sharing location.");
      return;
    }
    const coords = [Number(lat), Number(lon)];
    state.socket.send(JSON.stringify({ lat: coords[0], lon: coords[1] }));
    marker("rider", coords, "🛵", "Your location");
  }

  async function connect(order) {
    closeConnection();
    state.order = order;
    const pickup = point(order.restaurant_lat, order.restaurant_lon);
    const drop = point(order.delivery_lat, order.delivery_lon);

    marker("restaurant", pickup, "🍽️", "Restaurant pickup: " + (order.restaurant_name || "Restaurant"));
    marker("customer", drop, "🏠", "Customer address: " + (order.delivery_address || "Customer"));
    marker("rider", pickup, "🛵", "Your location");

    await loadAndDrawRoute(pickup, drop);

    if (!token()) {
      status("Please sign in again to share delivery location.");
      return;
    }
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    state.socket = new WebSocket(`${scheme}//${location.host}/ws/delivery/${order.order_id}?token=${encodeURIComponent(token())}`);
    state.socket.onopen = () => {
      status(`Connected to order #${order.order_number}. Road route loaded.`);
      ["startPartnerGps", "simulatePartnerGps", "stopPartnerGps"].forEach(id => {
        const button = document.getElementById(id);
        if (button) button.disabled = false;
      });
    };
    state.socket.onclose = () => status("Tracking connection closed.");
    state.socket.onerror = () => status("Could not connect to tracking. Check that this order is assigned to your account.");
  }

  function setOrders(orders) {
    state.orders = orders || [];
    if (!state.map) {
      status("The map library could not load. Check your internet connection and reload.");
      return;
    }
    const select = document.getElementById("trackingOrderSelect");
    if (!select) return;
    const previous = select.value;
    select.innerHTML = state.orders.length
      ? state.orders.map(order => `<option value="${order.order_id}">#${order.order_number} · ${order.status.replaceAll("_", " ")}</option>`).join("")
      : '<option value="">No assigned orders</option>';

    if (!state.orders.length) {
      closeConnection();
      state.order = null;
      status("No assigned orders are available to track.");
      return;
    }
    select.value = state.orders.some(order => String(order.order_id) === previous) ? previous : String(state.orders[0].order_id);
    connect(selected());
  }

  function initialize() {
    const node = document.getElementById("partnerMap");
    if (!node || state.map) return;
    if (!window.L) {
      status("The map library could not load. Check your internet connection and reload.");
      return;
    }
    state.map = L.map(node).setView([12.9716, 77.5946], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors"
    }).addTo(state.map);

    document.getElementById("trackingOrderSelect")?.addEventListener("change", () => {
      const order = selected();
      if (order) connect(order);
    });

    document.getElementById("startPartnerGps")?.addEventListener("click", () => {
      if (!navigator.geolocation) {
        status("This browser does not provide geolocation.");
        return;
      }
      if (state.simulation) {
        clearInterval(state.simulation);
        state.simulation = null;
      }
      state.watchId = navigator.geolocation.watchPosition(
        position => sendLocation(position.coords.latitude, position.coords.longitude),
        error => status(`Location error: ${error.message}`),
        { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
      );
      status("Live GPS active. Sharing location as you move.");
    });

    document.getElementById("simulatePartnerGps")?.addEventListener("click", () => {
      if (!state.order || !state.smoothPath || state.smoothPath.length === 0) {
        status("Wait for route to load before starting simulation.");
        return;
      }
      if (state.watchId !== null && navigator.geolocation) {
        navigator.geolocation.clearWatch(state.watchId);
        state.watchId = null;
      }
      if (state.simulation) {
        clearInterval(state.simulation);
        state.simulation = null;
      }

      state.simIndex = 0;
      const totalSteps = state.smoothPath.length;
      status("Moving smoothly along delivery route...");

      state.simulation = setInterval(() => {
        if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
          clearInterval(state.simulation);
          state.simulation = null;
          status("Disconnected from live tracking.");
          return;
        }

        const coords = state.smoothPath[state.simIndex];
        sendLocation(coords[0], coords[1]);

        state.simIndex++;
        if (state.simIndex >= totalSteps) {
          status("🎉 Arrived at customer delivery location!");
          clearInterval(state.simulation);
          state.simulation = null;
        } else {
          const progress = Math.round((state.simIndex / (totalSteps - 1)) * 100);
          status(`En route on mapped road: ${progress}% to destination`);
        }
      }, 400);
    });

    document.getElementById("stopPartnerGps")?.addEventListener("click", () => {
      if (state.watchId !== null && navigator.geolocation) {
        navigator.geolocation.clearWatch(state.watchId);
        state.watchId = null;
      }
      if (state.simulation) {
        clearInterval(state.simulation);
        state.simulation = null;
      }
      status("Location sharing paused. Click Simulate Movement or Start live GPS to resume.");
    });

    window.addEventListener("beforeunload", closeConnection);
  }

  return { initialize, setOrders };
})();
