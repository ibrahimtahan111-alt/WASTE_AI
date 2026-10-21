document.addEventListener("DOMContentLoaded", function () {
  // === Pie chart + Summary cards ===
  let pieChart = echarts.init(document.getElementById("impact-pie"));
  fetch("/api/impact")
    .then(res => res.json())
    .then(d => {
      // KPI cards
      document.getElementById("impact-total").innerText = d.total;
      document.getElementById("impact-kg").innerText = d.kg + " kg";
      document.getElementById("impact-co2").innerText = d.co2 + " kg";
      document.getElementById("impact-trees").innerText = d.trees;
      document.getElementById("impact-energy").innerText = d.energy + " kWh";
      document.getElementById("impact-water").innerText = d.water + " L";

      pieChart.setOption({
        tooltip: { trigger: "item" },
        legend: { bottom: 0 },
        series: [{
          type: "pie",
          radius: "60%",
          data: [
            { value: d.recyclable, name: "Recyclable" },
            { value: d.hazardous, name: "Hazardous" },
            { value: d.non, name: "Non-Recyclable" }
          ]
        }]
      });
    });

  // === Trend chart ===
  let trendChart = echarts.init(document.getElementById("impact-trend"));
  function loadTrend(period) {
    fetch(`/api/impact/trend?period=${period}`)
      .then(res => res.json())
      .then(data => {
        if (period === "week") {
          const days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
          let counts = Array(7).fill(0);
          data.forEach(r => counts[r.day] = r.count);
          trendChart.setOption({
            xAxis: { type: "category", data: days },
            yAxis: { type: "value" },
            series: [{ data: counts, type: "line", smooth: true }]
          });
        } else {
          const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
          let counts = Array(12).fill(0);
          data.forEach(r => counts[r.month - 1] = r.count);
          trendChart.setOption({
            xAxis: { type: "category", data: months },
            yAxis: { type: "value" },
            series: [{ data: counts, type: "bar" }]
          });
        }
      });
  }
  loadTrend("week");
  document.getElementById("trend-week").addEventListener("click", () => loadTrend("week"));
  document.getElementById("trend-month").addEventListener("click", () => loadTrend("month"));

  // === Category Stacked ===
  let stackedChart = echarts.init(document.getElementById("impact-stacked"));
  function loadCategoryStacked() {
    fetch("/api/history")
      .then(r => r.json())
      .then(rows => {
        let rec = Array(12).fill(0), haz = Array(12).fill(0), non = Array(12).fill(0);
        rows.forEach(r => {
          const iso = r.timestamp_iso || r.timestamp;
          const m = new Date(iso).getMonth();
          if (Number.isNaN(m)) return;
          if (r.category === "Recyclable") rec[m]++;
          else if (r.category === "Hazardous") haz[m]++;
          else non[m]++;
        });
        stackedChart.setOption({
          tooltip: { trigger: "axis" },
          legend: { top: 0 },
          xAxis: { type: "category", data: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"] },
          yAxis: { type: "value" },
          series: [
            { name:"Recyclable", type:"bar", stack:"total", data: rec },
            { name:"Hazardous", type:"bar", stack:"total", data: haz },
            { name:"Non-Recyclable", type:"bar", stack:"total", data: non }
          ]
        });
      });
  }
  loadCategoryStacked();

  // === Top Labels ===
  let topLabelsChart = echarts.init(document.getElementById("impact-toplabels"));
  function loadTopLabels() {
    fetch("/api/history")
      .then(r => r.json())
      .then(rows => {
        const counts = {};
        rows.forEach(r => counts[r.label] = (counts[r.label]||0)+1);
        const sorted = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,10);
        topLabelsChart.setOption({
          tooltip: {},
          xAxis: { type:"value" },
          yAxis: { type:"category", data: sorted.map(r=>r[0]) },
          series: [{ type:"bar", data: sorted.map(r=>r[1]) }]
        });
      });
  }
  loadTopLabels();

  // === Heatmap Calendar ===
  let heatmapChart = echarts.init(document.getElementById("impact-heatmap"));
  function loadHeatmap() {
    fetch("/api/history")
      .then(r => r.json())
      .then(rows => {
        const data = rows.map(r => {
          const iso = r.timestamp_iso || r.timestamp || "";
          let day = iso.includes("T") ? iso.slice(0, 10) : "";
          if (!day && /^\d{2}\/\d{2}\/\d{4}/.test(iso)) {
            const [dd, mm, yyyy] = iso.split(" ")[0].split("/");
            day = `${yyyy}-${mm}-${dd}`;
          }
          return [day, 1];
        }).filter(x => x[0]);
        heatmapChart.setOption({
          tooltip: {
            formatter: (p) => {
              const [y, m, d] = String(p.data[0] || "").split("-");
              return `${d}/${m}/${y}: ${p.data[1]} detection(s)`;
            }
          },
          visualMap: { min: 0, max: 10, calculable: true, orient:"horizontal", left:"center", bottom:0 },
          calendar: { range: new Date().getFullYear() },
          series: [{ type:"heatmap", coordinateSystem: "calendar", data }]
        });
      });
  }
  loadHeatmap();

  // === Fix hidden tab: resize all charts ===
  document.getElementById("tab-impact").addEventListener("shown.bs.tab", () => {
    pieChart.resize();
    trendChart.resize();
    stackedChart.resize();
    topLabelsChart.resize();
    heatmapChart.resize();
  });

  window.addEventListener("resize", () => {
    pieChart.resize();
    trendChart.resize();
    stackedChart.resize();
    topLabelsChart.resize();
    heatmapChart.resize();
  });
});
