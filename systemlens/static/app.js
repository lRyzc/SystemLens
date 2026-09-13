"use strict";
const $ = (id) => document.getElementById(id);
let data = null, paused = false, windowSeconds = 60, sort = "cpu", descending = true;
const number = (value, digits = 1) => value == null ? "—" : value.toLocaleString("pt-BR", {maximumFractionDigits: digits, minimumFractionDigits: digits});
const text = (id, value) => { $(id).textContent = value; };
function bytes(value) {
  if (value == null) return ["—", "B"];
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
  return [number(value, unit === 0 ? 0 : 1), units[unit]];
}
const size = (value) => bytes(value).join(" ");
const speed = (value) => value == null ? "Indisponível" : size(value) + "/s";
const timeLabel = (value) => new Date(value).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit", second: "2-digit"});
function status(label, state) { $("status").dataset.state = state; $("status").querySelector("span").textContent = label; }
function svgElement(tag, attributes) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}
function chart(id, samples, fields, width, height, maximum, grid = true) {
  const svg = $(id);
  svg.replaceChildren();
  if (grid) for (let i = 0; i <= 4; i++) svg.append(svgElement("line", {x1: 0, x2: width, y1: height * i / 4, y2: height * i / 4, stroke: "#303328", "stroke-dasharray": "3 5", "stroke-width": .7}));
  if (!samples.length) return;
  const end = Date.parse(samples.at(-1).timestamp), start = end - windowSeconds * 1000;
  fields.forEach((field, index) => {
    const points = samples.filter(s => s[field] != null).map(s => [Math.max(0, (Date.parse(s.timestamp) - start) / (windowSeconds * 1000) * width), height - Math.min(maximum, s[field]) / maximum * (height - 4) - 2]);
    if (!points.length) return;
    const d = points.map((point, i) => `${i ? "L" : "M"}${point[0].toFixed(2)},${point[1].toFixed(2)}`).join(" ");
    const color = index ? "#9ba68e" : "#c9ab70";
    if (!index && points.length > 1) svg.append(svgElement("path", {d: `${d} L${points.at(-1)[0]},${height} L${points[0][0]},${height} Z`, fill: color, opacity: .06}));
    svg.append(svgElement("path", {d, fill: "none", stroke: color, "stroke-width": 1.7, "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round"}));
    svg.append(svgElement("circle", {cx: points.at(-1)[0], cy: points.at(-1)[1], r: 2.3, fill: color}));
  });
}
function renderProcesses() {
  if (!data?.latest) return;
  const query = $("search").value.trim().toLocaleLowerCase();
  const all = data.latest.processes.filter(p => p.name.toLocaleLowerCase().includes(query) || String(p.pid).includes(query));
  all.sort((a, b) => (descending ? -1 : 1) * (a[sort] - b[sort]) || a.pid - b.pid);
  const rows = all.slice(0, 12).map(p => {
    const row = document.createElement("tr");
    const name = document.createElement("td"), inner = document.createElement("span"), icon = document.createElement("span");
    inner.className = "process-name"; icon.className = "process-icon"; icon.textContent = p.name.slice(0, 1).toUpperCase();
    inner.append(icon, document.createTextNode(p.name)); name.append(inner); row.append(name);
    for (const value of [p.pid, number(p.cpu) + "%", size(p.memory)]) { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }
    return row;
  });
  if (!rows.length) { const row = document.createElement("tr"), cell = document.createElement("td"); cell.colSpan = 4; cell.className = "empty"; cell.textContent = "Nenhum processo encontrado."; row.append(cell); rows.push(row); }
  $("process-rows").replaceChildren(...rows);
  text("process-shown", `Exibindo ${Math.min(12, all.length)} de ${all.length} processos${query ? " encontrados" : " acessíveis"}`);
  text("cpu-sort", sort === "cpu" ? descending ? "↓" : "↑" : "");
  text("memory-sort", sort === "memory" ? descending ? "↓" : "↑" : "");
  for (const field of ["cpu", "memory"]) document.querySelector(`[data-sort="${field}"]`).closest("th").setAttribute("aria-sort", sort === field ? descending ? "descending" : "ascending" : "none");
}
function render() {
  if (!data?.latest) return;
  const s = data.latest, system = data.system;
  text("cpu", number(s.cpu)); text("memory", number(s.memory_percent));
  text("cpu-caption", `${system.logical_cores} threads · ${s.frequency_mhz ? number(s.frequency_mhz / 1000, 2) + " GHz" : "Frequência indisponível"}`);
  text("memory-caption", `${size(s.memory_used)} de ${size(s.memory_total)}`);
  const disk = s.partitions[0];
  text("disk", disk ? number(disk.percent) : "—");
  text("disk-caption", disk ? `${size(disk.total - disk.used)} livres · ${disk.mount}` : "Volume indisponível");
  for (const [id, value] of [["cpu", s.cpu], ["memory", s.memory_percent], ["disk", disk?.percent || 0]]) $(id + "-meter").style.width = `${value}%`;
  const [value, unit] = bytes(s.download);
  text("network", value); text("network-unit", unit + "/s"); text("network-caption", `↑ ${speed(s.upload)} de saída`);
  text("cpu-legend", number(s.cpu) + "%"); text("memory-legend", number(s.memory_percent) + "%");
  const end = Date.parse(s.timestamp), samples = data.samples.filter(item => Date.parse(item.timestamp) >= end - windowSeconds * 1000);
  chart("performance-chart", samples, ["cpu", "memory_percent"], 1000, 200, 100);
  text("sample-count", `${samples.length} amostras · intervalo de ${data.interval}s`);
  text("chart-start", timeLabel(end - windowSeconds * 1000)); text("chart-mid", timeLabel(end - windowSeconds * 500)); text("chart-end", timeLabel(end));
  const maximum = Math.max(1024, ...samples.flatMap(item => [item.download || 0, item.upload || 0])) * 1.15;
  chart("network-chart", samples, ["download", "upload"], 600, 95, maximum);
  chart("network-mini", samples, ["download"], 300, 20, maximum, false);
  text("network-scale", `Topo: ${speed(maximum)}`); text("download", speed(s.download)); text("upload", speed(s.upload));
  text("core-count", `${s.cores.length} THREADS`);
  $("cores").replaceChildren(...s.cores.map((value, index) => {
    const box = document.createElement("div"), label = document.createElement("span"), count = document.createElement("strong"), meter = document.createElement("div"), bar = document.createElement("i");
    box.className = "core"; label.textContent = `CPU ${String(index).padStart(2, "0")}`; count.textContent = number(value, 0) + "%";
    meter.className = "meter"; bar.style.width = value + "%"; meter.append(bar); box.append(label, count, meter); return box;
  }));
  text("frequency", s.frequency_mhz ? number(s.frequency_mhz / 1000, 2) + " GHz" : "Indisponível");
  text("temperature", s.temperature == null ? "Indisponível" : number(s.temperature) + " °C");
  text("process-count", s.process_count); renderProcesses();
  $("volumes").replaceChildren(...s.partitions.map(p => {
    const volume = document.createElement("div"), heading = document.createElement("div"), label = document.createElement("strong"), usage = document.createElement("span"), meter = document.createElement("div"), bar = document.createElement("i"), note = document.createElement("p");
    volume.className = "volume"; heading.className = "volume-head"; label.textContent = p.mount; usage.textContent = `${size(p.used)} / ${size(p.total)}`;
    heading.append(label, usage); meter.className = "meter"; bar.style.width = p.percent + "%"; meter.append(bar); note.textContent = `${number(p.percent)}% utilizado${p.filesystem ? " · " + p.filesystem : ""}`;
    volume.append(heading, meter, note); return volume;
  }));
  text("disk-read", speed(s.disk_read)); text("disk-write", speed(s.disk_write)); text("os", system.os); text("architecture", system.architecture);
  text("system-cores", `${system.physical_cores ?? "—"} / ${system.logical_cores}`);
  text("uptime", `${Math.floor(s.uptime / 86400)}d ${Math.floor(s.uptime % 86400 / 3600)}h ${Math.floor(s.uptime % 3600 / 60)}min`);
  text("battery", s.battery ? `${number(s.battery.percent, 0)}% · ${s.battery.plugged ? "Na tomada" : "Em uso"}` : "Não detectada");
  text("updated", `Última leitura ${timeLabel(s.timestamp)} · intervalo de ${data.interval}s`);
}
$("pause").addEventListener("click", () => {
  paused = !paused;
  $("pause").querySelector("span").textContent = paused ? "Retomar" : "Pausar";
  $("pause").setAttribute("aria-pressed", String(paused));
  status(paused ? "Visualização pausada" : "Reconectando", paused ? "paused" : "loading");
  $("notice").hidden = !paused;
  if (paused) text("notice", "Visualização pausada. A coleta e a exportação do histórico continuam em segundo plano.");
});
document.querySelectorAll("[data-window]").forEach(button => button.addEventListener("click", () => {
  windowSeconds = Number(button.dataset.window);
  document.querySelectorAll("[data-window]").forEach(item => item.setAttribute("aria-pressed", String(item === button)));
  render();
}));
document.querySelectorAll("[data-sort]").forEach(button => button.addEventListener("click", () => {
  descending = sort === button.dataset.sort ? !descending : true; sort = button.dataset.sort; renderProcesses();
}));
$("search").addEventListener("input", renderProcesses);
document.querySelectorAll("nav a").forEach(link => link.addEventListener("click", () => {
  document.querySelectorAll("nav a").forEach(item => item.classList.toggle("active", item === link));
}));
async function poll() {
  if (!paused) {
    try {
      const response = await fetch("/api/metrics", {signal: AbortSignal.timeout(5000)});
      if (!response.ok) throw new Error("HTTP " + response.status);
      const incoming = await response.json();
      // A pause clicked during an in-flight request must freeze the visible values.
      if (!paused) {
        data = incoming;
        const stale = data.latest && Date.now() - Date.parse(data.latest.timestamp) > 5000;
        if (data.error || stale) throw new Error("Stale sample");
        status(data.latest ? "Ao vivo · 1s" : "Coletando", "live"); $("notice").hidden = true; render();
      }
    } catch (_) {
      if (!paused) { status("Sem conexão", "error"); $("notice").hidden = false; text("notice", "Não foi possível atualizar. Verifique se o SystemLens está aberto. A conexão será retomada automaticamente."); }
    }
  }
  setTimeout(poll, 1000);
}
poll();
