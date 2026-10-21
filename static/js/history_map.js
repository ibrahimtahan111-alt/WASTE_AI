
let currentCategory = null;
let map, directionsService, directionsRenderer, streetView;
let userMarker = null, userPos = null;
let facilityMarkers = [];
let facilitiesData = [];
let favoritesData = [];

// ----------------- Detection Modal -----------------
document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("detectionModal");
  const mapModal = document.getElementById("mapModal");
  const openMapBtn = document.getElementById("open-map-btn");

  modal.addEventListener("show.bs.modal", (event) => {
    const button = event.relatedTarget;
    const id = button.getAttribute("data-id");
    const detailsDiv = document.getElementById("detection-details");
    detailsDiv.innerHTML = "Loading...";
    openMapBtn.disabled = true;

    fetch(`/api/detection/${id}`)
      .then(res => res.json())
      .then(data => {
        detailsDiv.innerHTML = `
          <p><strong>Label:</strong> ${data.label}</p>
          <p><strong>Category:</strong> ${data.category}</p>
          <p><strong>Confidence:</strong> ${data.confidence}</p>
          <p><strong>Time:</strong> ${data.timestamp || ""}</p>
          ${data.snapshot_path ? `<img src="${data.snapshot_path}" class="img-fluid rounded mt-2">` : ""}
        `;
        currentCategory = data.category;
        openMapBtn.disabled = false;
      });
  });

  mapModal.addEventListener("shown.bs.modal", () => {
    initMap(currentCategory);
  });
});

// ----------------- Map Init -----------------
function initMap(category) {
  navigator.geolocation.getCurrentPosition((pos) => {
    userPos = { lat: pos.coords.latitude, lng: pos.coords.longitude };

    map = new google.maps.Map(document.getElementById("map"), {
      center: userPos,
      zoom: 13,
    });
    directionsService = new google.maps.DirectionsService();
    directionsRenderer = new google.maps.DirectionsRenderer({ map });
    streetView = new google.maps.StreetViewPanorama(
      document.getElementById("street-view"), {
        position: userPos,
        pov: { heading: 34, pitch: 10 },
        zoom: 1
      }
    );
    map.setStreetView(streetView);

    userMarker = new google.maps.Marker({
      position: userPos,
      map,
      title: "You are here",
      icon: {
        url: "http://maps.google.com/mapfiles/ms/icons/blue-dot.png",
        scaledSize: new google.maps.Size(40, 40)
      }
    });

    fetch(`/api/facilities?category=${category}`)
      .then(res => res.json())
      .then(facilities => {
        facilitiesData = facilities;
        renderFacilities();
      });

    loadFavorites();
  });
}

// ----------------- Render Facilities -----------------
function renderFacilities() {
  const filters = Array.from(document.querySelectorAll(".facility-filter:checked")).map(cb => cb.value);
  const list = document.getElementById("facility-list");
  list.innerHTML = "";
  facilityMarkers.forEach(m => m.setMap(null));
  facilityMarkers = [];

  facilitiesData.forEach((f, i) => {
    if (!filters.some(fl => f.accepts.includes(fl))) return;

    const icon = f.pickup
      ? "http://maps.google.com/mapfiles/ms/icons/truck.png"
      : "http://maps.google.com/mapfiles/ms/icons/recycle.png";

    const marker = new google.maps.Marker({
      position: { lat: f.lat, lng: f.lng },
      map,
      title: f.name,
      icon
    });
    facilityMarkers.push(marker);

    const li = document.createElement("li");
    li.className = "list-group-item d-flex justify-content-between align-items-center";
    li.innerHTML = `
      <div>
        <strong>${f.name}</strong><br>
        <small>${f.address || ""}</small><br>
        <span class="text-muted">${f.notes || ""}</span>
        <div id="eta-${f.id}" class="small text-primary"></div>
      </div>
      <button class="btn btn-sm btn-outline-warning btn-save" data-id="${f.id}">⭐</button>
    `;
    li.addEventListener("click", () => {
      focusFacility(f, marker);
    });
    list.appendChild(li);

    calcETA(f, `eta-${f.id}`);

    marker.addListener("click", () => {
      focusFacility(f, marker);
    });
  });
}

// ----------------- Render Favorites -----------------
function loadFavorites() {
  fetch("/api/favorites")
    .then(res => res.json())
    .then(data => {
      favoritesData = data;
      const list = document.getElementById("favorites-list");
      list.innerHTML = "";
      favoritesData.forEach(f => {
        const li = document.createElement("li");
        li.className = "list-group-item d-flex justify-content-between align-items-center";
        li.innerHTML = `
          <div>
            <strong>${f.name}</strong><br>
            <small>${f.address || ""}</small>
          </div>
          <button class="btn btn-sm btn-outline-danger btn-remove" data-id="${f.id}">❌</button>
        `;
        li.addEventListener("click", () => {
          focusFacility(f, null);
        });
        list.appendChild(li);
      });
    });
}

// ----------------- Focus Facility -----------------
function focusFacility(f, marker) {
  map.setCenter({ lat: f.lat, lng: f.lng });
  map.setZoom(15);

  const info = new google.maps.InfoWindow({
    content: `
      <div>
        <strong>${f.name}</strong><br>
        <em>${f.address || ""}</em><br>
        ${f.website ? `<a href="${f.website}" target="_blank">Website</a><br>` : ""}
        <a href="https://www.google.com/maps/dir/?api=1&origin=${userPos.lat},${userPos.lng}&destination=${f.lat},${f.lng}" target="_blank">🚗 Open in Google Maps</a>
      </div>
    `
  });
  if (marker) info.open(map, marker);

  drawRoute(userPos, f);
  streetView.setPosition({ lat: f.lat, lng: f.lng });
}

// ----------------- Draw Route -----------------
function drawRoute(userPos, facility) {
  directionsService.route({
    origin: userPos,
    destination: { lat: facility.lat, lng: facility.lng },
    travelMode: google.maps.TravelMode.DRIVING
  }).then((result) => {
    directionsRenderer.setDirections(result);
  });
}

// ----------------- ETA -----------------
function calcETA(facility, elementId) {
  const service = new google.maps.DistanceMatrixService();
  service.getDistanceMatrix({
    origins: [userPos],
    destinations: [{ lat: facility.lat, lng: facility.lng }],
    travelMode: "DRIVING"
  }, (response, status) => {
    if (status === "OK") {
      const res = response.rows[0].elements[0];
      document.getElementById(elementId).innerText =
        `🚗 ${res.duration.text}, ${res.distance.text}`;
    }
  });
}

// ----------------- Save Facility -----------------
document.addEventListener("click", (e) => {
  if (e.target.classList.contains("btn-save")) {
  const id = e.target.getAttribute("data-id");
  fetch(`/api/favorites/${id}`, { method: "POST" })
    .then(() => {
      e.target.innerText = "✅ Saved";
      e.target.disabled = true;
      loadFavorites();
    });
}

 if (e.target.classList.contains("btn-remove")) {
  const id = e.target.getAttribute("data-id");
  fetch(`/api/favorites/${id}`, { method: "DELETE" })
    .then(() => loadFavorites());
}
});

// ----------------- 📍 Recenter -----------------
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-my-location").addEventListener("click", () => {
    if (userPos && map) {
      map.setCenter(userPos);
      map.setZoom(15);
      if (userMarker) {
        userMarker.setAnimation(google.maps.Animation.BOUNCE);
        setTimeout(() => userMarker.setAnimation(null), 1500);
      }
    }
  });

  document.querySelectorAll(".facility-filter").forEach(cb => {
    cb.addEventListener("change", renderFacilities);
  });
});

