(function () {
  "use strict";
  var app = document.getElementById("routing-app");
  if (!app || typeof L === "undefined") return;
  var form = document.getElementById("routing-import-form"), status = document.getElementById("routing-import-status");
  var summary = document.getElementById("routing-summary"), create = document.getElementById("routing-create");
  var optimize = document.getElementById("routing-optimize"), target = document.getElementById("routing-target");
  var mode = document.getElementById("routing-mode"), results = document.getElementById("routing-results");
  var map = L.map("routing-map").setView([48.42, -122.35], 11), layers = {}, currentImport = null, currentPlan = null;
  L.tileLayer("https://gis.skagitcountywa.gov/arcgis/rest/services/Assessor/PropertyMap/MapServer/tile/{z}/{y}/{x}", {maxZoom: 19, attribution: "Skagit County GIS"}).addTo(map);
  function csrf() { var m = document.cookie.match(/csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : ""; }
  function clear() { Object.keys(layers).forEach(function (key) { map.removeLayer(layers[key]); }); layers = {}; results.innerHTML = ""; }
  function draw(data) {
    clear(); var bounds = [];
    data.routes.forEach(function (route, index) {
      var color = ["#d05a3a", "#287c72", "#6d54a3", "#bc7d2d", "#2b6ca3", "#a33d72"][index % 6], group = L.layerGroup();
      route.stops.forEach(function (stop) { L.circleMarker([stop.latitude, stop.longitude], {radius: 7, color: color, fillColor: color, fillOpacity: .9, weight: 2}).bindTooltip(route.route_number + "." + stop.sequence + " " + (stop.parcel_id || "stop")).addTo(group); bounds.push([stop.latitude, stop.longitude]); });
      group.addTo(map); layers[route.route_number] = group;
      var html = '<article class="routing-result" style="border-left-color:' + color + '"><strong>Route ' + route.route_number + '</strong> · ' + route.stop_count + ' stops<ol>';
      route.stops.forEach(function (stop) { html += '<li>' + String(stop.parcel_id || "") + (stop.address ? " — " + String(stop.address) : "") + '</li>'; });
      results.insertAdjacentHTML("beforeend", html + "</ol></article>");
    });
    if (bounds.length) map.fitBounds(bounds, {padding: [20, 20]});
  }
  function request(url, options) {
    options = options || {}; options.credentials = "same-origin"; options.headers = options.headers || {}; options.headers["X-CSRFToken"] = csrf();
    return fetch(url, options).then(function (response) { return response.text().then(function (text) { var data; try { data = JSON.parse(text); } catch (_) { throw Error("Server returned an HTML error page. Check the Railway logs."); } if (!response.ok) throw Error(data.error || "Request failed"); return data; }); });
  }
  form.addEventListener("submit", function (event) { event.preventDefault(); status.textContent = "Importing and validating…"; request(app.dataset.importUrl, {method: "POST", body: new FormData(form)}).then(function (data) { currentImport = data.import_id; create.disabled = false; summary.textContent = data.unique_stop_count + " unique stops from " + data.row_count + " source rows; " + data.summary.duplicate_rows + " duplicates, " + data.summary.missing_coordinates + " missing coordinates, " + data.summary.addressless_rows + " addressless rows."; status.textContent = "Import ready. Create clusters now; optimize later."; }).catch(function (error) { status.textContent = error.message; }); });
  create.addEventListener("click", function () { if (!currentImport) return; create.disabled = true; status.textContent = "Creating geographic clusters…"; request(app.dataset.planUrl, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({import_id: currentImport, target_stop_count: Number(target.value), mode: mode.value})}).then(function (data) { currentPlan = data.plan_id; optimize.disabled = false; summary.textContent = data.route_count + " clusters created; " + data.summary.valid_stops + " stops assigned. Stop order is not optimized yet."; draw(data); status.textContent = "Clusters saved. You can optimize this plan later."; create.disabled = false; }).catch(function (error) { status.textContent = error.message; create.disabled = false; }); });
  optimize.addEventListener("click", function () { if (!currentPlan) return; optimize.disabled = true; status.textContent = "Optimizing saved stop order with the routing server…"; request("/field/routes/plan/" + currentPlan + "/optimize/", {method: "POST"}).then(function (data) { summary.textContent = data.route_count + " optimized " + data.mode + " routes; " + data.summary.valid_stops + " stops assigned."; draw(data); status.textContent = "Optimization complete."; optimize.disabled = false; }).catch(function (error) { status.textContent = error.message; optimize.disabled = false; }); });
}());
