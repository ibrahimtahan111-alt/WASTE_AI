// static/js/history_facilities.js
document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.querySelector("#facilities-table tbody");
  const search = document.getElementById("facility-search");
  if (!tbody) return;

  let allFacilities = [];

  function render(list) {
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-muted text-center">No facilities found.</td></tr>`;
      return;
    }
    tbody.innerHTML = list.map((f) => `
      <tr>
        <td>
          <strong>${f.name || "—"}</strong>
          <div class="small text-muted">${f.address || ""}</div>
        </td>
        <td>${f.city || "—"}</td>
        <td><small>${f.accepts || "—"}</small></td>
        <td>${f.phone || "—"}</td>
        <td>${f.pickup ? '<span class="badge bg-success">Yes</span>' : '<span class="badge bg-secondary">No</span>'}</td>
        <td class="text-nowrap">
          ${f.lat != null && f.lng != null
            ? `<a class="btn btn-sm btn-outline-success" target="_blank"
                 href="https://www.google.com/maps/dir/?api=1&destination=${f.lat},${f.lng}">Route</a>`
            : ""}
          ${f.website
            ? `<a class="btn btn-sm btn-outline-primary" target="_blank" href="${f.website}">Site</a>`
            : ""}
        </td>
      </tr>
    `).join("");
  }

  function applyFilter() {
    const q = (search?.value || "").trim().toLowerCase();
    if (!q) {
      render(allFacilities);
      return;
    }
    render(allFacilities.filter((f) => {
      const blob = `${f.name || ""} ${f.city || ""} ${f.address || ""} ${f.accepts || ""} ${f.notes || ""}`.toLowerCase();
      return blob.includes(q);
    }));
  }

  fetch("/api/facilities")
    .then((r) => r.json())
    .then((list) => {
      allFacilities = Array.isArray(list) ? list : [];
      render(allFacilities);
    })
    .catch(() => {
      tbody.innerHTML = `<tr><td colspan="6" class="text-danger text-center">Failed to load facilities.</td></tr>`;
    });

  search?.addEventListener("input", applyFilter);
});
