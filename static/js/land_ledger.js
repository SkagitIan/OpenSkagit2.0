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
  var resultCurrentEl = document.getElementById("os-ll-result-current");
  var resultScenarioEl = document.getElementById("os-ll-result-scenario");
  var resultValueEl = document.getElementById("os-ll-result-value");
  var resultUnitsEl = document.getElementById("os-ll-result-units");
  var resultAnnualEl = document.getElementById("os-ll-result-annual");
  var result10yrEl = document.getElementById("os-ll-result-10yr");

  var toggleButtons = section.querySelectorAll("[data-revenue-view]");
  var modelButtons = section.querySelectorAll("[data-model-view]");
  var filterButtons = section.querySelectorAll("[data-land-filter]");

  var introEl = document.getElementById("os-ll-intro");
  var introDismissBtn = document.getElementById("os-ll-intro-dismiss");
  var INTRO_SEEN_KEY = "os_ll_intro_seen";
  var COLORS = { low: "#7a1f1f", medium: "#c9772e", high: "#5bbb2f", veryHigh: "#1aacb0" };

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

  function matchesFilter(props) {
    return state.landFilter === "all" || props.zone_group === state.landFilter;
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
    if (taxPerAcre < bp.p25) return COLORS.low;
    if (taxPerAcre < bp.p50) return COLORS.medium;
    if (taxPerAcre < bp.p75) return COLORS.high;
    return COLORS.veryHigh;
  }

  function revenueMultiplier(props) {
    return state.revenueView === "city" ? (props.city_tax_pct || 0) / 100 : 1;
  }

  function titleize(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
  }

  function scenarioKeysFor(props) {
    if (!props.zone_id) return [];
    return state.modelView === "policy" ? (props.policy_scenarios || []) : (props.allowed_scenarios || []);
  }

  function citywideOpportunity() {
    var total = 0;
    state.geoLayer.eachLayer(function (layer) {
      var props = layer.feature.properties;
      if (!matchesFilter(props)) return;
      var value;
      if (state.revenueView === "city") {
        value = state.modelView === "policy" ? props.city_policy_opportunity_10yr : props.city_current_opportunity_10yr;
      } else {
        value = state.modelView === "policy" ? props.policy_opportunity_10yr : props.current_opportunity_10yr;
      }
      total += Math.max(0, value || 0);
    });
    return total;
  }

  var FILTER_LABELS = {
    all: "land inside existing city limits",
    residential: "residentially zoned land",
    commercial: "commercially zoned land",
    industrial: "industrially zoned land",
    public: "public and open-space land",
  };

  function renderBigNumber() {
    bigNumberEl.textContent = money(citywideOpportunity()) + " over " + state.metadata.horizon_years + " years";
    captionEl.textContent = "Scenario-based estimate for " + FILTER_LABELS[state.landFilter] + " (" +
      (state.revenueView === "city" ? "City-only revenue" : "Total public revenue") + ", " +
      (state.modelView === "policy" ? "policy-change scenarios" : "current-zoning scenarios") + ").";
  }

  function renderScenarioButtons(props) {
    scenarioButtonsEl.innerHTML = "";
    resultEl.hidden = true;
    scenarioDescriptionEl.textContent = "Click a scenario above to see what it means and what it could generate.";

    var definitions = state.metadata.scenario_definitions || {};
    var keys = scenarioKeysFor(props);
    if (keys.length === 0) {
      var reasons = props.exclusion_reasons || (props.benchmark_source && props.benchmark_source.exclusion_reasons);
      scenarioDescriptionEl.textContent = reasons && reasons.length
        ? "Excluded from modeled opportunity: " + reasons.map(titleize).join(", ") + "."
        : "No development scenarios apply in this model for this parcel.";
      return;
    }

    keys.forEach(function (key) {
      var definition = definitions[key];
      var result = props.scenario_results && props.scenario_results[key];
      if (!definition || !result) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "os-ll-scenario-btn";
      btn.textContent = definition.label || result.label;
      btn.title = definition.description || result.description || "";
      btn.dataset.scenarioKey = key;
      btn.addEventListener("click", function () {
        state.selectedScenarioKey = key;
        Array.prototype.forEach.call(scenarioButtonsEl.children, function (child) {
          child.classList.toggle("is-active", child === btn);
        });
        scenarioDescriptionEl.textContent = (definition.label || result.label) + ": " + (definition.description || result.description || "");
        renderResult(props, key);
      });
      scenarioButtonsEl.appendChild(btn);
    });

    if (!scenarioButtonsEl.children.length) {
      scenarioDescriptionEl.textContent = "No benchmark is available yet for this zone and scenario.";
    }
  }

  function renderResult(props, scenarioKey) {
    var mult = revenueMultiplier(props);
    var scenario = props.scenario_results && props.scenario_results[scenarioKey];
    if (!scenario) return;
    resultCurrentEl.textContent = moneyExact(props.tax_per_acre * mult) + "/acre";
    resultScenarioEl.textContent = moneyExact(scenario.tax_per_acre * mult) + "/acre";
    resultValueEl.textContent = moneyExact(scenario.added_assessed_value || 0);
    resultUnitsEl.textContent = scenario.modeled_units
      ? Number(scenario.modeled_units).toLocaleString(undefined, { maximumFractionDigits: 1 })
      : "n/a";
    var annual = state.revenueView === "city" ? scenario.city_annual_gain : scenario.annual_gain;
    var tenYear = state.revenueView === "city" ? scenario.city_ten_year_gain : scenario.ten_year_gain;
    resultAnnualEl.textContent = (annual >= 0 ? "+" : "") + moneyExact(annual);
    result10yrEl.textContent = (tenYear >= 0 ? "+" : "") + moneyExact(tenYear);
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
    factTaxesEl.textContent = moneyExact(props.current_tax);
    factTaxAcreEl.textContent = moneyExact(props.tax_per_acre) + "/acre";
    factProductivityEl.textContent = props.productivity_percentile == null
      ? "Unavailable"
      : titleize(props.productivity_label) + " (" + Math.round(props.productivity_percentile * 100) + "th pct.)";
    factEligibilityEl.textContent = props.model_flags && props.model_flags.eligible ? "Eligible" : "Excluded";

    var zoneDescs = state.metadata.zone_descriptions || {};
    var zoneInfo = props.zone_id ? zoneDescs[props.zone_id] : null;
    factZoneEl.textContent = (zoneInfo ? zoneInfo.label : props.zone_id) || "Zoning unavailable";
    factZoneDescEl.textContent = zoneInfo ? zoneInfo.description : "";
    factZoneDescEl.hidden = !zoneInfo;
    underperformEl.textContent = props.model_flags && props.model_flags.eligible
      ? "This parcel has at least one modeled revenue scenario."
      : "This parcel is mapped for productivity, but excluded from modeled opportunity totals.";
    underperformEl.hidden = false;
    renderScenarioButtons(props);
  }

  function styleFeature(feature) {
    var visible = matchesFilter(feature.properties);
    return {
      color: visible ? "rgba(61,77,92,0.45)" : "rgba(61,77,92,0.08)",
      weight: 0.7,
      fillColor: colorFor(feature.properties.tax_per_acre),
      fillOpacity: visible ? 0.7 : 0.04,
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
      .map(function (feature) { return feature.properties.tax_per_acre || 0; })
      .sort(function (a, b) { return a - b; });
    state.breakpoints = {
      p25: percentile(taxPerAcreValues, 0.25),
      p50: percentile(taxPerAcreValues, 0.5),
      p75: percentile(taxPerAcreValues, 0.75),
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
    renderBigNumber();
    loadingEl.hidden = true;
  }).catch(function (err) {
    loadingEl.textContent = "Land Ledger data has not been rebuilt yet. Run python manage.py rebuild_land_ledger --city sedro-woolley.";
    console.error("Land Ledger: failed to load database-backed parcel data", err);
  });
})();
