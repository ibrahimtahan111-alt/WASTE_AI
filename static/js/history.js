// static/js/history.js
document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.querySelector("#history-table tbody");
  const kTotal = document.getElementById("kpi-total");
  const kRe = document.getElementById("kpi-recyc");
  const kHaz = document.getElementById("kpi-haz");
  const kAct = document.getElementById("kpi-actions"); // for later (server-side count if needed)

  const selCat = document.getElementById("filter-category");
  const dtStart = document.getElementById("filter-start");
  const dtEnd = document.getElementById("filter-end");
  const btnApply = document.getElementById("filter-apply");

  // Charts
  const pie = echarts.init(document.getElementById("chart-cats"));
  const trend = echarts.init(document.getElementById("chart-trend"));

  let currentRows = [];
  let selected = null;

  function badge(c) {
    if (c === "Recyclable") return `<span class="badge bg-success">${c}</span>`;
    if (c === "Hazardous") return `<span class="badge bg-danger">${c}</span>`;
    if (c === "Non-Recyclable") return `<span class="badge bg-secondary">${c}</span>`;
    return `<span class="badge bg-dark">${c}</span>`;
  }

  function loadHistory() {
    const p = new URLSearchParams();
    if (selCat.value) p.set("category", selCat.value);
    if (dtStart.value) p.set("start", dtStart.value);
    if (dtEnd.value) p.set("end", dtEnd.value);
    fetch(`/api/history?${p}`)
      .then(r => r.json())
      .then(rows => {
        currentRows = rows;
        renderTable(rows);
        renderKpis(rows);
        renderCharts(rows);
      });
  }

  function renderTable(rows) {
    tbody.innerHTML = rows.map(r => `
      <tr data-id="${r.id}">
        <td>${r.timestamp || ""}</td>
        <td>${r.label}</td>
        <td>${r.confidence}%</td>
        <td>${badge(r.category)}</td>
        <td>${r.snapshot ? `<img src="${r.snapshot}" style="max-width:70px" class="rounded">` : `<span class="text-muted">Live</span>`}</td>
        <td><button class="btn btn-sm btn-outline-primary btn-details">Details</button></td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".btn-details").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const tr = e.target.closest("tr");
        const id = parseInt(tr.dataset.id, 10);
        const r = currentRows.find(x => x.id === id);
        openDetails(r);
      });
    });
  }

  function renderKpis(rows) {
    kTotal.textContent = rows.length;
    const byCat = rows.reduce((m, r) => (m[r.category] = (m[r.category]||0)+1, m), {});
    const pct = (n) => rows.length ? Math.round((n/rows.length)*100) : 0;
    kRe.textContent = `${pct(byCat["Recyclable"]||0)}%`;
    kHaz.textContent = `${pct(byCat["Hazardous"]||0)}%`;
    // Actions KPI is optional; keep 0 for now.
    kAct.textContent = "0";
  }

  function renderCharts(rows) {
    // Pie by category
    const cats = ["Recyclable","Non-Recyclable","Hazardous","Unknown"];
    const counts = cats.map(c => rows.filter(r => r.category===c).length);
    pie.setOption({
      tooltip: { trigger: 'item' },
      series: [{ type:'pie', radius:'65%', data: cats.map((c,i)=>({name:c, value:counts[i]})) }]
    });

    // Trend by date
    const byDay = {};
    rows.forEach(r => {
      const iso = r.timestamp_iso || r.timestamp;
      const d = (iso || "").includes("T") ? iso.slice(0, 10) : (iso || "").split(" ")[0];
      // Convert yyyy-mm-dd or dd/mm/yyyy to dd/mm/yyyy for axis labels
      let label = d;
      if (/^\d{4}-\d{2}-\d{2}$/.test(d)) {
        const [y, m, day] = d.split("-");
        label = `${day}/${m}/${y}`;
      }
      byDay[label] = (byDay[label] || 0) + 1;
    });
    const days = Object.keys(byDay);
    trend.setOption({
      xAxis: { type:'category', data: days },
      yAxis: { type:'value' },
      tooltip: { trigger: 'axis' },
      series: [{ type:'line', data: days.map(d=>byDay[d]) }]
    });
  }

  // Details modal
  const detModal = new bootstrap.Modal(document.getElementById("detailsModal"));
  const detTitle = document.getElementById("det-title");
  const detLabel = document.getElementById("det-label");
  const detCat = document.getElementById("det-category");
  const detConf = document.getElementById("det-conf");
  const detTime = document.getElementById("det-time");
  const detSnap = document.getElementById("det-snapshot");
  const detInfo = document.getElementById("det-info");
  const btnFind = document.getElementById("btn-find-facility");

  function infoFor(label, category) {
    if (category === "Recyclable") return "Sort clean & dry. Remove liquids; compress where possible. Dropping off helps keep value in the local recycling market.";
    if (category === "Hazardous") return "Handle with care. Keep away from water/heat. Take to certified e-waste / hazardous handlers to avoid toxins in the environment.";
    if (category === "Non-Recyclable") return "Avoid/replace where possible. If no dedicated program exists, dispose with general waste; never burn or dump in nature.";
    return "Ensure responsible handling. Check local guidance.";
  }

  function openDetails(r) {
    selected = r;
    detTitle.textContent = `${r.label}`;
    detLabel.textContent = r.label;
    detCat.innerHTML = badge(r.category);
    detConf.textContent = `${r.confidence}%`;
    detTime.textContent = r.timestamp || "";
    detSnap.src = r.snapshot || "";
    detSnap.style.display = r.snapshot ? "block" : "none";
    detInfo.textContent = infoFor(r.label, r.category);
    detModal.show();
  }

  // Map modal + directions
  const mapModalEl = document.getElementById("mapModal");
  const mapModal = new bootstrap.Modal(mapModalEl);
  const mapCtx = document.getElementById("map-context");
  let map, userMarker, dirService, dirRenderer;

  btnFind.addEventListener("click", async () => {
    detModal.hide();
    if (!selected) return;
    mapCtx.textContent = `Filtering facilities for: ${selected.label} (${selected.category})`;
    mapModal.show();

    await new Promise(r => setTimeout(r, 200)); // let modal render
    initMap(selected);
  });

  function initMap(sel) {
    map = new google.maps.Map(document.getElementById("map"), { center: {lat:33.8886, lng:35.4955}, zoom: 12 });
    dirService = new google.maps.DirectionsService();
    dirRenderer = new google.maps.DirectionsRenderer({ map });

    // user location
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(pos => {
        const me = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        map.setCenter(me);
        userMarker = new google.maps.Marker({ position: me, map, title: "You are here" });
      });
    }

    // fetch facilities
    const p = new URLSearchParams({ label: sel.label, category: sel.category });
    fetch(`/api/facilities?${p}`).then(r => r.json()).then(list => {
      const geocoder = new google.maps.Geocoder();
      list.forEach(f => {
        geocoder.geocode({ address: f.address }, (res, status) => {
          if (status !== "OK" || !res[0]) return;
          const loc = res[0].geometry.location;
          const mk = new google.maps.Marker({ position: loc, map, title: f.name });
          const inf = new google.maps.InfoWindow({
            content: `
              <div style="max-width:260px">
                <strong>${f.name}</strong><br>
                <small>${f.address}</small><br>
                <small>Accepts: ${f.accepts}</small><br>
                ${f.phone ? `<small>Phone: ${f.phone}</small><br>` : ""}
                ${f.website ? `<a href="${f.website}" target="_blank">Website</a><br>` : ""}
                <button class="btn btn-sm btn-success mt-1" id="route-btn">Route here</button>
                <button class="btn btn-sm btn-outline-secondary mt-1" id="log-btn">Mark as dropped off</button>
              </div>`
          });
          mk.addListener("click", () => {
            inf.open({ anchor: mk, map });
            // delegate after open
            setTimeout(() => {
              const rt = document.getElementById("route-btn");
              if (rt) rt.onclick = () => routeTo(loc);
              const lg = document.getElementById("log-btn");
              if (lg) lg.onclick = () => logAction(sel.id, f.id);
            }, 50);
          });
        });
      });
    });
  }

  function routeTo(dest) {
    if (!userMarker) return;
    dirService.route({
      origin: userMarker.getPosition(),
      destination: dest,
      travelMode: google.maps.TravelMode.DRIVING
    }, (res, status) => {
      if (status === "OK") dirRenderer.setDirections(res);
    });
  }

  function logAction(detId, facId) {
    const pos = userMarker ? userMarker.getPosition() : null;
    fetch("/api/actions/log", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        detection_id: detId,
        facility_id: facId,
        action_type: "dropoff",
        user_lat: pos ? pos.lat() : null,
        user_lng: pos ? pos.lng() : null
      })
    }).then(()=>alert("✅ Logged drop-off. Thank you!"));
  }

  btnApply.addEventListener("click", loadHistory);
  loadHistory();
});
