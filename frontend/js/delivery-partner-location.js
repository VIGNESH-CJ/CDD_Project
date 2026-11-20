(() => {
  const token = API.getToken();
  const user = API.getUser();
  const connectForm = document.getElementById("connectForm");
  const orderInput = document.getElementById("orderId");
  const status = document.getElementById("status");
  const gpsButton = document.getElementById("gps");
  const simulateButton = document.getElementById("simulate");
  const stopButton = document.getElementById("stop");
  let socket = null;
  let watchId = null;
  let simulationTimer = null;
  let map = null;
  let marker = null;

  function setStatus(message, state = "") {
    status.textContent = message;
    status.dataset.state = state;
  }

  function setSharingControls(enabled) {
    gpsButton.disabled = !enabled;
    simulateButton.disabled = !enabled;
    stopButton.disabled = !enabled && watchId === null && simulationTimer === null;
  }

  function stopLocationSources() {
    if (watchId !== null && navigator.geolocation) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    if (simulationTimer !== null) window.clearInterval(simulationTimer);
    simulationTimer = null;
  }

  function publish(latitude, longitude) {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setStatus("The location coordinates were invalid.", "error");
      return;
    }
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setStatus("Connect to an assigned order before sharing location.", "error");
      return;
    }
    socket.send(JSON.stringify({ lat, lon }));
    if (map) {
      if (marker) marker.setLatLng([lat, lon]);
      else marker = L.circleMarker([lat, lon], { radius: 9, color: "#c2410c", fillColor: "#f97316", fillOpacity: 1 }).addTo(map);
      map.panTo([lat, lon]);
    }
    setStatus(`Sharing location: ${lat.toFixed(5)}, ${lon.toFixed(5)}`, "live");
  }

  function buildSocketUrl(orderId) {
    const url = new URL(API_BASE_URL);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = `/ws/delivery/${orderId}`;
    url.search = new URLSearchParams({ token }).toString();
    return url.href;
  }

  if (!token || user?.role !== "delivery_partner") {
    setStatus("Sign in with a delivery partner account to share location.", "error");
    connectForm.querySelector("button[type='submit']").disabled = true;
    window.setTimeout(() => { window.location.href = "/pages/login.html"; }, 900);
    return;
  }

  if (window.L) {
    map = L.map("partnerMap", { scrollWheelZoom: false }).setView([12.9716, 77.5946], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors"
    }).addTo(map);
  } else {
    setStatus("Map tiles did not load. You can still share your location.", "warning");
  }

  connectForm.addEventListener("submit", event => {
    event.preventDefault();
    const orderId = Number(orderInput.value);
    if (!Number.isSafeInteger(orderId) || orderId < 1) {
      setStatus("Enter a valid assigned order ID.", "error");
      orderInput.focus();
      return;
    }
    stopLocationSources();
    socket?.close();
    setStatus("Connecting to the assigned order…");
    socket = new WebSocket(buildSocketUrl(orderId));
    socket.addEventListener("open", () => {
      setStatus(`Connected to order ${orderId}. Location sharing is off.`, "connected");
      setSharingControls(true);
    });
    socket.addEventListener("message", event => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "error") setStatus(message.detail || "The server rejected this location update.", "error");
      } catch {
        setStatus("Received an unreadable update from the server.", "warning");
      }
    });
    socket.addEventListener("close", event => {
      stopLocationSources();
      setSharingControls(false);
      setStatus(event.code === 4403 ? "This order is not assigned to your account." : "Connection closed.", "warning");
    });
    socket.addEventListener("error", () => setStatus("Connection failed. Check the order assignment and try again.", "error"));
  });

  gpsButton.addEventListener("click", () => {
    if (!navigator.geolocation) {
      setStatus("This browser does not provide geolocation.", "error");
      return;
    }
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = navigator.geolocation.watchPosition(
      position => publish(position.coords.latitude, position.coords.longitude),
      error => setStatus(error.message || "Could not read the device location.", "error"),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
    );
    setSharingControls(true);
    setStatus("Waiting for GPS location…", "connected");
  });

  function densifyRoute(coordinates, targetStepCount = 120) {
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

  async function getOrderRoadRoute(orderId) {
    try {
      const res = await fetch(`/api/delivery/orders/${orderId}/location`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const start = [data.restaurant.lat, data.restaurant.lon];
      const end = [data.customer.lat, data.customer.lon];
      const url = `https://router.project-osrm.org/route/v1/driving/${start[1]},${start[0]};${end[1]},${end[0]}?overview=full&geometries=geojson`;
      const routeRes = await fetch(url);
      if (routeRes.ok) {
        const routeData = await routeRes.json();
        if (routeData.routes && routeData.routes.length > 0) {
          return routeData.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
        }
      }
      return [start, [start[0] + (end[0]-start[0])*0.5 + 0.003, start[1] + (end[1]-start[1])*0.5 - 0.002], end];
    } catch {
      return [[12.9784, 77.6408], [12.9720, 77.6350], [12.9620, 77.6290], [12.9352, 77.6245]];
    }
  }

  simulateButton.addEventListener("click", async () => {
    stopLocationSources();
    const orderId = Number(orderInput.value);
    setStatus("Calculating road delivery path…");
    const rawRoute = await getOrderRoadRoute(orderId);
    const smoothRoute = densifyRoute(rawRoute, 120);
    let index = 0;
    simulationTimer = window.setInterval(() => {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        stopLocationSources();
        setSharingControls(false);
        return;
      }
      const coords = smoothRoute[index % smoothRoute.length];
      publish(coords[0], coords[1]);
      index++;
      if (index >= smoothRoute.length) {
        setStatus("🎉 Arrived at delivery location!", "connected");
        stopLocationSources();
      }
    }, 400);
    setSharingControls(true);
    setStatus("Smooth road route is sharing location.", "live");
  });

  stopButton.addEventListener("click", () => {
    stopLocationSources();
    socket?.close();
    socket = null;
    setSharingControls(false);
    setStatus("Location sharing stopped.");
  });

  window.addEventListener("beforeunload", () => {
    stopLocationSources();
    socket?.close();
  });
})();
