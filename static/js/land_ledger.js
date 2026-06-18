(function () {
  "use strict";

  var section = document.getElementById("land-ledger");
  if (!section) return;

  var parcelsUrl = section.getAttribute("data-parcels-url");
  var summaryUrl = section.getAttribute("data-summary-url");
  var loadingEl = document.getElementById("os-ll-loading");
  var bigNumberEl = document.getElementById("os-ll-big-number");
  var captionEl = document.querySelector(".os-ll-panel__caption");

  var parcelDetailEl = document.getElementById("os-ll-parcel-detail");
  var addressEl = document.getElementById("os-ll-parcel-address");
  var factParcelEl = document.getElementById("os-ll-fact-parcel");
  var factAcresEl = document.getElementById("os-ll-fact-acres");
  var factUseEl = document.getElementById("os-ll-fact-use");
  var factZoneEl = document.getElementById("os-ll-fact-zone");
  var factZoneDescEl = document.getElementById("os-ll-zone-description");
  var factTaxesEl = document.getElementById("os-ll-fact-taxes");
  var factTaxAcreEl = document.getElementById("os-ll-fact-tax-acre");
  var factProductivityEl = document.getElementById("os-ll-fact-productivity");
  var factEligibilityEl = document.getElementById("os-ll-fact-eligibility");
  var underperformEl = document.getElementById("os-ll-underperform");
  var scenarioButtonsEl = document.getElementById("os-ll-scenario-buttons");
  var scenarioDescriptionEl = document.getElementById("os-ll-scenario-description");
  var resultEl = document.getElementById("os-ll-result");
  var resultScenarioEl = document.getElementById("os-ll-result-scenario");
  var resultAnnualEl = document.getElementById("os-ll-result-annual");
  var result10yrEl = document.getElementById("os-ll-result-10yr");
  var residentialSummaryEl = document.getElementById("os-ll-residential-summary");

  var toggleButtons = section.querySelectorAll("[data-revenue-view]");
  var modelButtons = section.querySelectorAll("[data-model-view]");
  var filterButtons = section.querySelectorAll("[data-land-filter]");

  var introEl = document.getElementById("os-ll-intro");
  var introDismissBtn = document.getElementById("os-ll-intro-dismiss");
  var INTRO_SEEN_KEY = "os_ll_intro_seen";
  var COLORS = { low: "#8d2f2f", typical: "#d39b3d", high: "#2f8f69", excluded: "#9aa5ad" };

  var state = {
    revenueView: "city",
    modelView: "current",
    landFilter: "all",
    metadata: null,
    breakpoints: null,
    selectedFeature: null,
    selectedScenarioKey: null,
    map: null,
    geoLayer: null,
    activeLayer: null,
  };

  function matchesFilter() {
    return true;
  }

  function money(n) {
    var sign = n < 0 ? "-" : "";
    n = Math.abs(n || 0);
    if (n >= 1000000) return sign + "$" + (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return sign + "$" + Math.round(n).toLocaleString();
    return sign + "$" + Math.round(n);
  }

  function moneyExact(n) {
    var sign = n < 0 ? "-" : "";
    return sign + "$" + Math.round(Math.abs(n || 0)).toLocaleString();
  }

  function percentile(sorted, p) {
    if (!sorted.length) return 0;
    var idx = (sorted.length - 1) * p;
    var lo = Math.floor(idx), hi = Math.ceil(idx);
    if (lo === hi) return sorted[lo];
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }

  function colorFor(taxPerAcre) {
    var bp = state.breakpoints;
    if (taxPerAcre < bp.p33) return COLORS.low;
    if (taxPerAcre < bp.p66) return COLORS.typical;
    return COLORS.high;
  }

  function revenueMultiplier(props) {
    return state.revenueView === "city" ? (props.city_tax_pct || 0) / 100 : 1;
  }

  function cityRevenuePerAcre(props) {
    return (props.tax_per_acre || 0) * ((props.city_tax_pct || 0) / 100);
  }

  function titleize(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
  }

  function bestScenario(props) {
    var results = props.scenario_results || {};
    var current = (props.allowed_scenarios || [])
      .map(function (key) { return { key: key, result: results[key], kind: "current" }; })
      .filter(function (item) { return item.result; });
    var policy = (props.policy_scenarios || [])
      .map(function (key) { return { key: key, result: results[key], kind: "policy" }; })
      .filter(function (item) { return item.result; });
    var candidates = current.length ? current : policy;
    candidates.sort(function (a, b) {
      return (b.result.city_ten_year_gain || 0) - (a.result.city_ten_year_gain || 0);
    });
    return candidates[0] || null;
  }

  function renderBigNumber() {
    bigNumberEl.textContent = "Click a parcel";
    captionEl.textContent = "See what each parcel contributes to the city today.";
  }

  function renderScenarioButtons(props) {
    scenarioButtonsEl.innerHTML = "";
    scenarioButtonsEl.hidden = true;
    resultEl.hidden = true;
    var scenario = bestScenario(props);
    if (!scenario) {
      var reasons = props.exclusion_reasons || (props.benchmark_source && props.benchmark_source.exclusion_reasons);
      scenarioDescriptionEl.textContent = reasons && reasons.length
        ? "Not modeled for development opportunity. Reason: " + titleize(reasons[0]) + ". Still shown because it affects current city revenue."
        : "Not modeled for development opportunity. Still shown because it affects current city revenue.";
      return;
    }
    state.selectedScenarioKey = scenario.key;
    scenarioDescriptionEl.textContent = "Potential scenario: " + scenario.result.label + ".";
    renderResult(props, scenario.key);
  }

  function renderResult(props, scenarioKey) {
    var scenario = props.scenario_results && props.scenario_results[scenarioKey];
    if (!scenario) return;
    resultScenarioEl.textContent = scenario.label;
    resultAnnualEl.textContent = "+" + moneyExact(scenario.city_annual_gain || 0);
    result10yrEl.textContent = "+" + moneyExact(scenario.city_ten_year_gain || 0);
    resultEl.hidden = false;
  }

  function selectFeature(layer) {
    if (!matchesFilter(layer.feature.properties)) return;
    if (state.activeLayer) state.geoLayer.resetStyle(state.activeLayer);
    state.activeLayer = layer;
    layer.setStyle({ weight: 3, color: "#ffffff", dashArray: null });
    layer.bringToFront();

    var props = layer.feature.properties;
    state.selectedFeature = props;
    state.selectedScenarioKey = null;
    parcelDetailEl.hidden = false;
    addressEl.textContent = props.address || "(no address on file)";
    factParcelEl.textContent = props.parcel_number;
    factAcresEl.textContent = Number(props.acres || 0).toFixed(2);
    factUseEl.textContent = props.land_use || "Unclassified";
    var cityTax = (props.current_tax || 0) * ((props.city_tax_pct || 0) / 100);
    var cityTaxPerAcre = cityRevenuePerAcre(props);
    var comparison = cityTaxPerAcre < state.breakpoints.p33 ? "Low" : (cityTaxPerAcre < state.breakpoints.p66 ? "Typical" : "High");
    factTaxesEl.textContent = moneyExact(cityTax);
    factTaxAcreEl.textContent = moneyExact(cityTaxPerAcre) + "/acre";
    factProductivityEl.textContent = comparison;
    factEligibilityEl.textContent = bestScenario(props) ? "Eligible for scenario" : "Not modeled";

    var zoneDescs = state.metadata.zone_descriptions || {};
    var zoneInfo = props.zone_id ? zoneDescs[props.zone_id] : null;
    factZoneEl.textContent = (zoneInfo ? zoneInfo.label : props.zone_id) || "Zoning unavailable";
    factZoneDescEl.textContent = zoneInfo ? zoneInfo.description : "";
    factZoneDescEl.hidden = !zoneInfo;
    underperformEl.textContent = props.model_flags && props.model_flags.eligible
      ? "This parcel may reasonably produce more city revenue under the model."
      : "This parcel is mapped for current city revenue, but not counted as a development opportunity.";
    underperformEl.hidden = false;
    renderScenarioButtons(props);
  }

  function styleFeature(feature) {
    var visible = matchesFilter(feature.properties);
    var modeled = Boolean(bestScenario(feature.properties));
    return {
      color: visible ? "rgba(61,77,92,0.45)" : "rgba(61,77,92,0.08)",
      weight: 0.7,
      fillColor: modeled ? colorFor(cityRevenuePerAcre(feature.properties)) : COLORS.excluded,
      fillOpacity: visible ? (modeled ? 0.72 : 0.42) : 0.04,
    };
  }

  function applyFilter() {
    state.geoLayer.eachLayer(function (layer) {
      if (layer !== state.activeLayer) state.geoLayer.resetStyle(layer);
    });
    if (state.activeLayer && !matchesFilter(state.activeLayer.feature.properties)) {
      deselectFeature();
    }
    renderBigNumber();
  }

  function deselectFeature() {
    if (state.activeLayer) state.geoLayer.resetStyle(state.activeLayer);
    state.activeLayer = null;
    state.selectedFeature = null;
    state.selectedScenarioKey = null;
    parcelDetailEl.hidden = true;
  }

  toggleButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      state.revenueView = btn.getAttribute("data-revenue-view");
      Array.prototype.forEach.call(toggleButtons, function (item) {
        item.classList.toggle("is-active", item === btn);
      });
      renderBigNumber();
      if (state.selectedFeature && state.selectedScenarioKey) renderResult(state.selectedFeature, state.selectedScenarioKey);
    });
  });

  modelButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      state.modelView = btn.getAttribute("data-model-view");
      Array.prototype.forEach.call(modelButtons, function (item) {
        item.classList.toggle("is-active", item === btn);
      });
      renderBigNumber();
      if (state.selectedFeature) renderScenarioButtons(state.selectedFeature);
    });
  });

  filterButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      state.landFilter = btn.getAttribute("data-land-filter");
      Array.prototype.forEach.call(filterButtons, function (item) {
        item.classList.toggle("is-active", item === btn);
      });
      applyFilter();
    });
  });

  if (introEl && introDismissBtn) {
    var introAlreadySeen = false;
    try { introAlreadySeen = localStorage.getItem(INTRO_SEEN_KEY) === "1"; } catch (e) {}
    introEl.hidden = introAlreadySeen;
    introDismissBtn.addEventListener("click", function () {
      introEl.hidden = true;
      try { localStorage.setItem(INTRO_SEEN_KEY, "1"); } catch (e) {}
    });
  }

  Promise.all([
    fetch(summaryUrl).then(function (res) {
      if (!res.ok) throw new Error("summary not ready");
      return res.json();
    }),
    fetch(parcelsUrl).then(function (res) {
      if (!res.ok) throw new Error("parcels not ready");
      return res.json();
    })
  ]).then(function (responses) {
    var summary = responses[0];
    var data = responses[1];
    state.metadata = {
      scenario_definitions: summary.scenario_definitions || {},
      zone_descriptions: summary.zone_descriptions || {},
      buildout_factor: Number(summary.buildout_factor || 0.5),
      horizon_years: Number(summary.horizon_years || 10),
      diagnostics: summary.diagnostics || {},
    };

    var taxPerAcreValues = data.features
      .map(function (feature) { return cityRevenuePerAcre(feature.properties); })
      .sort(function (a, b) { return a - b; });
    state.breakpoints = {
      p33: percentile(taxPerAcreValues, 0.33),
      p66: percentile(taxPerAcreValues, 0.66),
    };

    state.map = L.map("os-ll-map", { scrollWheelZoom: false });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
      maxZoom: 19,
      detectRetina: true,
    }).addTo(state.map);

    state.geoLayer = L.geoJSON(data, {
      style: styleFeature,
      onEachFeature: function (feature, layer) {
        layer.on("click", function () { selectFeature(layer); });
        layer.on("mouseover", function () {
          if (layer !== state.activeLayer && matchesFilter(feature.properties)) {
            layer.setStyle({ weight: 2, color: "#3D4D5C" });
          }
        });
        layer.on("mouseout", function () {
          if (layer !== state.activeLayer) state.geoLayer.resetStyle(layer);
        });
      },
    }).addTo(state.map);

    state.map.fitBounds(state.geoLayer.getBounds(), { padding: [16, 16] });
    var residentialTotal = (summary.scenario_totals && summary.scenario_totals.small_infill || 0) +
      (summary.scenario_totals && summary.scenario_totals.townhomes || 0) +
      (summary.scenario_totals && summary.scenario_totals.small_multifamily || 0);
    var cityRatio = summary.current_opportunity_10yr
      ? (summary.city_current_opportunity_10yr || 0) / summary.current_opportunity_10yr
      : 0;
    if (residentialSummaryEl && residentialTotal && cityRatio) {
      residentialSummaryEl.textContent = money(residentialTotal * cityRatio) + " more city revenue";
    }
    renderBigNumber();
    loadingEl.hidden = true;
  }).catch(function (err) {
    loadingEl.textContent = "Land Ledger data has not been rebuilt yet. Run python manage.py rebuild_land_ledger --city sedro-woolley.";
    console.error("Land Ledger: failed to load database-backed parcel data", err);
  });
})();
