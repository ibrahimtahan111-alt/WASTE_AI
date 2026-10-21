document.addEventListener("DOMContentLoaded", () => {
  if (!document.getElementById("badges-list")) return;

  const list = document.getElementById("badges-list");
  const tbody = document.querySelector("#leaderboard-table tbody");

  function loadBadges() {
    fetch("/api/badges").then(r=>r.json()).then(badges=>{
      list.innerHTML = badges.map(b=>`
        <div class="card p-2 text-center" style="width:120px">
          <div style="font-size:2em">${b.icon}</div>
          <div class="small">${b.name}</div>
        </div>`).join("");
    });
  }

  function loadLeaderboard() {
    fetch("/api/leaderboard").then(r=>r.json()).then(rows=>{
      tbody.innerHTML = rows.map(r=>`
        <tr><td>${r.user}</td><td>${r.detections}</td><td>${r.points}</td></tr>
      `).join("");
    });
  }

  document.getElementById("tab-badges").addEventListener("shown.bs.tab", ()=>{
    loadBadges();
    loadLeaderboard();
  });
});
