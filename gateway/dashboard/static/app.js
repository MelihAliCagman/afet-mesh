"use strict";

const STATUS_TEXT = {canli: "canlı", gecikmis: "gecikmiş", kayip: "kayıp"};
let serverNow = Date.now() / 1000;      // sunucu saati (demo modunda gerçek saatten farklı olabilir)
let serverNowAt = Date.now();           // bu değerin alındığı tarayıcı zamanı
let nodes = [];
const markers = new Map();
let sosNodes = new Set();

function nowS() { return serverNow + (Date.now() - serverNowAt) / 1000; }
function ago(t) {
  const s = Math.max(0, Math.round(nowS() - t));
  if (s < 60) return s + " sn önce";
  if (s < 3600) return Math.round(s / 60) + " dk önce";
  return Math.round(s / 3600) + " sa önce";
}
async function getJSON(url) { const r = await fetch(url); return r.json(); }
function esc(t) { return String(t ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }
function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

// ---------- harita (çevrimdışı koordinat düzlemi) ----------
const map = L.map("map", {crs: L.CRS.Simple, minZoom: -3, maxZoom: 1, zoomSnap: 0.25, attributionControl: false});
const bounds = [[-120, -120], [1120, 1120]];
for (let v = 0; v <= 1000; v += 250) {
  L.polyline([[v, -120], [v, 1120]], {color: css("--grid"), weight: 1, interactive: false}).addTo(map);
  L.polyline([[-120, v], [1120, v]], {color: css("--grid"), weight: 1, interactive: false}).addTo(map);
  if (v > 0) {
    L.marker([-60, v], {interactive: false, icon: L.divIcon({className: "node-label", html: v + " m", iconSize: [40, 14]})}).addTo(map);
    L.marker([v, -80], {interactive: false, icon: L.divIcon({className: "node-label", html: v + " m", iconSize: [40, 14]})}).addTo(map);
  }
}
map.fitBounds(bounds);
L.marker([0, 0], {icon: L.divIcon({className: "", html: '<div style="width:14px;height:14px;background:' + css("--accent") + ';transform:rotate(45deg);margin:-7px 0 0 -7px"></div>', iconSize: [0, 0]})})
  .bindTooltip("Gateway", {permanent: true, direction: "right", className: "node-label"}).addTo(map);

function statusColor(s) { return css(s === "canli" ? "--ok" : s === "gecikmis" ? "--warn" : "--bad"); }

function drawNodes() {
  for (const n of nodes) {
    if (n.x == null) continue;
    let m = markers.get(n.node_id);
    const sos = sosNodes.has(n.node_id);
    const style = {radius: 9, color: sos ? css("--bad") : statusColor(n.status), weight: sos ? 4 : 2,
                   fillColor: statusColor(n.status), fillOpacity: 0.85};
    const tip = "#" + n.node_id;
    if (!m) {
      m = L.circleMarker([n.y, n.x], style).addTo(map);
      m.bindTooltip(tip, {permanent: true, direction: "top", className: "node-label", offset: [0, -6]});
      markers.set(n.node_id, m);
    } else { m.setStyle(style); }
    m.bindPopup("<b>Düğüm " + n.node_id + "</b><br>durum: " + STATUS_TEXT[n.status] + "<br>pil: %" + n.battery +
                "<br>konum: " + n.x + ", " + n.y + " m<br>son görülme: " + ago(n.last_seen));
  }
}

// ---------- üst özet ----------
function chip(text, cls) { return '<span class="chip ' + (cls || "") + '">' + text + "</span>"; }
function renderHealth(h) {
  serverNow = h.now; serverNowAt = Date.now();
  const lost = h.gecikmis + h.kayip;
  const age = h.last_message_age == null ? "-" : Math.round(h.last_message_age) + " sn";
  document.getElementById("chips").innerHTML =
    chip("Canlı düğüm <b>" + h.canli + "/" + h.nodes_total + "</b>", lost ? "warn" : "ok") +
    chip("Mesaj/dk <b>" + h.messages_last_min + "</b>") +
    chip("Toplam mesaj <b>" + h.messages_total + "</b>") +
    chip("Son mesaj <b>" + age + "</b>") +
    chip("Köprü kuyruğu <b>" + h.outbox_pending + "</b>", h.outbox_pending > 0 ? "warn" : "ok") +
    chip("Güvenlik olayı (10 dk) <b>" + h.alarms_last_10min + "</b>", h.alarms_last_10min ? "bad" : "ok");
  const bar = document.getElementById("alarmbar");
  if (h.alarms_last_10min > 0) { bar.hidden = false; bar.textContent = "Son 10 dakikada " + h.alarms_last_10min + " güvenlik olayı kaydedildi. Ayrıntı: Güvenlik olayları."; }
  else bar.hidden = true;
  document.getElementById("demo").hidden = !h.demo;
}

// ---------- düğüm tablosu ----------
function renderNodes() {
  const tb = document.querySelector("#nodetable tbody");
  tb.innerHTML = nodes.map(n => {
    const low = (n.battery ?? 100) < 25;
    return "<tr><td>#" + n.node_id + "</td>" +
      '<td><span class="badge ' + n.status + '">' + STATUS_TEXT[n.status] + "</span></td>" +
      '<td><span class="batt ' + (low ? "low" : "") + '"><i style="width:' + (n.battery ?? 0) + '%"></i></span>' + (n.battery ?? "-") + "%</td>" +
      "<td>" + (n.x ?? "-") + ", " + (n.y ?? "-") + "</td><td>" + ago(n.last_seen) + "</td><td>" + n.msg_count + "</td></tr>";
  }).join("");
  document.getElementById("nodecount").textContent = nodes.length + " düğüm";
  const sel = document.getElementById("killsel");
  if (sel.options.length !== nodes.length) sel.innerHTML = nodes.map(n => '<option value="' + n.node_id + '">#' + n.node_id + "</option>").join("");
}

// ---------- mesaj ve alarm akışı ----------
const KIND_CLASS = {"SOS": "sos", "durum": "durum", "sensör": "sensor"};
const feed = document.getElementById("feed");
function addMessage(m, prepend) {
  const li = document.createElement("li");
  if (m.kind_name === "SOS") { li.className = "sos"; sosNodes.add(m.src); }
  li.innerHTML = '<span class="badge ' + KIND_CLASS[m.kind_name] + '">' + esc(m.kind_name) + "</span><b>#" + m.src + "</b><span>" +
    esc(m.text || "") + '</span><span class="t" data-t="' + m.received_at + '">' + ago(m.received_at) + "</span>";
  if (prepend) feed.prepend(li); else feed.append(li);
  while (feed.children.length > 60) feed.lastChild.remove();
}
const alarmList = document.getElementById("alarms");
const ALARM_TEXT = {bad_tag: "Geçersiz etiket (sahte veya bozuk paket)", replay: "Tekrar oynatma (eski paket)", regression: "Sayaç geriledi (klon veya sıfırlanma)",
                    jump: "Sayaç aşırı ilerledi", klon_alarmi: "KLON ŞÜPHESİ ALARMI", rapor_hatasi: "Geçersiz rapor içeriği"};
function addAlarm(a, prepend) {
  const li = document.createElement("li");
  li.innerHTML = '<span class="badge ' + (a.kind === "klon_alarmi" ? "sos" : "gecikmis") + '">' + esc(a.kind) + "</span><b>" + (a.src == null ? "" : "#" + a.src) +
    "</b><span>" + esc(ALARM_TEXT[a.kind] || a.kind) + '</span><span class="t">' + ago(a.ts) + "</span>";
  if (prepend) alarmList.prepend(li); else alarmList.append(li);
  while (alarmList.children.length > 40) alarmList.lastChild.remove();
  document.getElementById("alarmcount").textContent = alarmList.children.length + " olay";
}

async function refreshNodes() { nodes = await getJSON("/api/nodes"); renderNodes(); drawNodes(); }

let polling = false;
function startPolling(msgs, alarms) {
  if (polling) return;
  polling = true;
  let lastMsg = msgs.length ? Math.max(...msgs.map(m => m.id)) : 0;
  let lastAlarm = alarms.length ? Math.max(...alarms.map(a => a.id)) : 0;
  setInterval(async () => {
    try {
      const [h, nm, na] = await Promise.all([getJSON("/api/health"), getJSON("/api/messages?after_id=" + lastMsg + "&limit=100"), getJSON("/api/alarms?limit=50")]);
      renderHealth(h);
      for (const m of nm.reverse()) { addMessage(m, true); lastMsg = Math.max(lastMsg, m.id); }
      for (const a of na.filter(a => a.id > lastAlarm).reverse()) { addAlarm(a, true); lastAlarm = Math.max(lastAlarm, a.id); }
    } catch (e) { /* bağlantı yoksa sonraki turda tekrar dener */ }
  }, 2000);
}

async function init() {
  const [h, msgs, alarms] = await Promise.all([getJSON("/api/health"), getJSON("/api/messages?limit=40"), getJSON("/api/alarms?limit=20")]);
  renderHealth(h);
  for (const m of msgs.reverse()) addMessage(m, true);
  for (const a of alarms.reverse()) addAlarm(a, true);
  await refreshNodes();
  if (new URLSearchParams(location.search).has("poll") || typeof EventSource === "undefined") startPolling(msgs, alarms);
  else {
    const es = new EventSource("/api/stream");
    es.addEventListener("message", e => { addMessage(JSON.parse(e.data), true); });
    es.addEventListener("alarm", e => addAlarm(JSON.parse(e.data), true));
    es.addEventListener("health", e => renderHealth(JSON.parse(e.data)));
    es.onerror = () => { es.close(); startPolling(msgs, alarms); };
  }
  setInterval(refreshNodes, 3000);
  setInterval(() => document.querySelectorAll("[data-t]").forEach(el => el.textContent = ago(parseFloat(el.dataset.t))), 1000);
}

document.getElementById("killbtn").onclick = () => fetch("/api/demo/kill/" + document.getElementById("killsel").value, {method: "POST"});
document.querySelectorAll("[data-attack]").forEach(b => b.onclick = () => fetch("/api/demo/attack/" + b.dataset.attack, {method: "POST"}));
init();
