/* Leaflet live order tracking for customer view. Load Leaflet 1.9.x before this script. */
(() => {
  const qs = new URLSearchParams(location.search);
  const orderId = Number(qs.get("order_id"));
  const token = localStorage.getItem("aifoodie_token");
  const mapNode = document.getElementById("trackingMap");
  if (!mapNode || !orderId || !token || !window.L) return;

  const map = L.map(mapNode).setView([12.9716, 77.5946], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors"
  }).addTo(map);

  const restaurantIcon = L.divIcon({
    className: "tracking-pin restaurant-pin",
    html: `<span style="font-size: 26px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">🍽️</span>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17]
  });
  const customerIcon = L.divIcon({
    className: "tracking-pin customer-pin",
    html: `<span style="font-size: 26px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">🏠</span>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17]
  });
  const riderIcon = L.divIcon({
    className: "tracking-pin rider-pin",
    html: `<span style="font-size: 28px; filter: drop-shadow(0 2px 5px rgba(0,0,0,0.35));">🛵</span>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18]
  });

  let rider = null;
  let routeLayer = null;
  let smoothPath = [];
  let demoTimer = null;
  let hasReceivedLiveLocation = false;

  const setMarker = (markerRef, coords, icon, title) => {
    if (markerRef) {
      markerRef.setLatLng(coords);
      return markerRef;
    }
    return L.marker(coords, { icon, title }).addTo(map);
  };

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

  async function loadRouteOnce(start, end) {
    if (routeLayer) map.removeLayer(routeLayer);
    let rawCoords = [];
    try {
      const url = `https://router.project-osrm.org/route/v1/driving/${start[1]},${start[0]};${end[1]},${end[0]}?overview=full&geometries=geojson`;
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        if (data.routes && data.routes.length > 0) {
          rawCoords = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
        }
      }
    } catch (error) {
      console.warn("OSRM route fetch unavailable, using road fallback", error);
    }

    if (!rawCoords || rawCoords.length < 2) {
      rawCoords = generateRoadFallback(start, end);
    }

    smoothPath = densifyRoute(rawCoords, 140);
    routeLayer = L.polyline(rawCoords, {
      color: "#f97316",
      weight: 5,
      opacity: 0.85,
      lineCap: "round",
      lineJoin: "round"
    }).addTo(map);

    map.fitBounds(routeLayer.getBounds(), { padding: [32, 32] });
  }

  function startSmoothSimulation() {
    if (hasReceivedLiveLocation || !smoothPath || smoothPath.length === 0 || demoTimer) return;
    let step = 0;
    const totalSteps = smoothPath.length;
    demoTimer = setInterval(() => {
      if (hasReceivedLiveLocation) {
        clearInterval(demoTimer);
        demoTimer = null;
        return;
      }
      const coords = smoothPath[step];
      rider = setMarker(rider, coords, riderIcon, "Delivery Partner (Simulated)");
      step = (step + 1) % totalSteps;
    }, 400);
  }

  async function initialize() {
    const res = await fetch(`/api/delivery/orders/${orderId}/location`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error("Could not load order locations");
    const data = await res.json();
    const rest = [data.restaurant.lat, data.restaurant.lon];
    const customer = [data.customer.lat, data.customer.lon];

    L.marker(rest, { icon: restaurantIcon }).addTo(map).bindPopup("Restaurant: Pickup Point");
    L.marker(customer, { icon: customerIcon }).addTo(map).bindPopup("Delivery Address: Dropoff Point");

    await loadRouteOnce(rest, customer);

    const initialPoint = data.partner
      ? [data.partner.lat, data.partner.lon]
      : rest;
    rider = setMarker(rider, initialPoint, riderIcon, "Delivery Partner");

    // If no live WebSocket coordinates arrive after 1.8s, run smooth demo road animation
    setTimeout(() => {
      if (!hasReceivedLiveLocation) {
        startSmoothSimulation();
      }
    }, 1800);
  }

  initialize().catch(error => {
    const status = document.getElementById("trackingStatus");
    if (status) status.textContent = error.message;
  });

  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/ws/delivery/${orderId}?token=${encodeURIComponent(token)}`);

  socket.addEventListener("open", () => {
    const status = document.getElementById("trackingStatus");
    if (status) status.textContent = "Live location connected";
  });

  socket.addEventListener("message", event => {
    try {
      const data = JSON.parse(event.data);
      if (data.type !== "location") return;
      hasReceivedLiveLocation = true;
      if (demoTimer) {
        clearInterval(demoTimer);
        demoTimer = null;
      }
      const point = [Number(data.lat), Number(data.lon)];
      rider = setMarker(rider, point, riderIcon, "Delivery Partner (Live)");
    } catch (e) {
      console.warn("Invalid tracking message", e);
    }
  });
})();
