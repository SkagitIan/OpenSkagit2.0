(function () {
  "use strict";

  var section = document.getElementById("land-ledger");
  if (!section) return;

  var geojsonUrl = section.getAttribute("data-geojson-url");
  var loadingEl = document.getElementById("os-ll-loading");
  var bigNumberEl = document.getElementById("os-ll-big-number");
  var captionEl = document.querySelector(".os-ll-panel__caption");

  var parcelDetailEl = document.getElementById("os-ll-parcel-detail");
  var addressEl = document.getElementById("os-ll-parcel-address");
  var factParcelEl = document.getElementById("os-ll-fact-parcel");
  var factAcresEl = document.getElementById("os-ll-fact-acres");
  var factUseEl = document.getElementById("os-ll-fact-use");
  var factTaxesEl = document.getElementById("os-ll-fact-taxes");
  var factTaxAcreEl = document.getElementById("os-ll-fact-tax-acre");
  var underperformEl = document.getElementById("os-ll-underperform");
  var scenarioButtonsEl = document.getElementById("os-ll-scenario-buttons");
  var resultEl = document.getElementById("os-ll-result");
  var resultCurrentEl = document.getElementById("os-ll-result-current");
  var resultScenarioEl = document.getElementById("os-ll-result-scenario");
  var resultAnnualEl = document.getElementById("os-ll-result-annual");
  var result10yrEl = document.getElementById("os-ll-result-10yr");

  var toggleButtons = section.querySelectorAll("[data-revenue-view]");
  var filterButtons = section.querySelectorAll("[data-land-filter]");

  var introEl = document.getElementById("os-ll-intro");
  var introDismissBtn = document.getElementById("os-ll-intro-dismiss");
  var INTRO_SEEN_KEY = "os_ll_intro_seen";

  var COLORS = { low: "#7a1f1f", medium: "#c9772e", high: "#5bbb2f", veryHigh: "#1aacb0" };

  var state = {
    revenueView: "total",
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
    return state.landFilter === "all" || props.land_use_group === state.landFilter;
  }

  function money(n) {
    var sign = n < 0 ? "-" : "";
    n = Math.abs(n);
    if (n >= 1000000) return sign + "$" + (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return sign + "$" + Math.round(n).toLocaleString();
    return sign + "$" + Math.round(n);
  }

  function moneyExact(n) {
    var sign = n < 0 ? "-" : "";
    return sign + "$" + Math.round(Math.abs(n)).toLocaleString();
  }

  function percentile(sorted, p) {
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
    return state.revenueView === "city" ? props.city_tax_pct / 100 : 1;
  }

  function bestGainPerAcre(props) {
    var scenarios = state.metadata.scenarios;
    var best = -Infinity;
    Object.keys(scenarios).forEach(function (key) {
      var gain = scenarios[key].tax_per_acre - props.tax_per_acre;
      if (gain > best) best = gain;
    });
    return best;
  }

  function citywideOpportunity() {
    var total = 0;
    state.geoLayer.eachLayer(function (layer) {
      var props = layer.feature.properties;
      if (!matchesFilter(props)) return;
      var gainPerAcre = bestGainPerAcre(props);
      if (gainPerAcre > 0) {
        var annual = gainPerAcre * props.acres * revenueMultiplier(props);
        total += annual * state.metadata.horizon_years * state.metadata.buildout_factor;
      }
    });
    return total;
  }

  var FILTER_LABELS = {
    all: "underused land inside existing city limits",
    residential: "underused residential land",
    commercial: "underused commercial land",
    industrial: "underused industrial land",
    vacant_other: "underused vacant and other land",
  };

  function renderBigNumber() {
    bigNumberEl.textContent = money(citywideOpportunity()) + " over " + state.metadata.horizon_years + " years";
    captionEl.textContent = "Based on " + FILTER_LABELS[state.landFilter] + " (" +
      (state.revenueView === "city" ? "City-only revenue" : "Total public revenue") + ").";
  }

  function renderScenarioButtons(props) {
    scenarioButtonsEl.innerHTML = "";
    var scenarios = state.metadata.scenarios;
    Object.keys(scenarios).forEach(function (key) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "os-ll-scenario-btn";
      btn.textContent = scenarios[key].label;
      btn.dataset.scenarioKey = key;
      btn.addEventListener("click", function () {
        state.selectedScenarioKey = key;
        Array.prototype.forEach.call(scenarioButtonsEl.children, function (c) {
          c.classList.toggle("is-active", c === btn);
        });
        renderResult(props, key);
      });
      scenarioButtonsEl.appendChild(btn);
    });
  }

  function renderResult(props, scenarioKey) {
    var mult = revenueMultiplier(props);
    var scenario = state.metadata.scenarios[scenarioKey];
    var currentTotal = props.tax_per_acre * props.acres * mult;
    var scenarioTotal = scenario.tax_per_acre * props.acres * mult;
    var annualGain = scenarioTotal - currentTotal;
    var tenYearGain = annualGain * state.metadata.horizon_years * state.metadata.buildout_factor;

    resultCurrentEl.textContent = moneyExact(props.tax_per_acre * mult) + "/acre";
    resultScenarioEl.textContent = moneyExact(scenario.tax_per_acre * mult) + "/acre";
    resultAnnualEl.textContent = (annualGain >= 0 ? "+" : "") + moneyExact(annualGain);
    result10yrEl.textContent = (tenYearGain >= 0 ? "+" : "") + moneyExact(tenYearGain);
    resultEl.hidden = false;
  }

  function selectFeature(layer) {
    if (!matchesFilter(layer.feature.properties)) return;
    if (state.activeLayer) {
      state.geoLayer.resetStyle(state.activeLayer);
    }
    state.activeLayer = layer;
    layer.setStyle({ weight: 3, color: "#ffffff", dashArray: null });
    layer.bringToFront();

    var props = layer.feature.properties;
    state.selectedFeature = props;
    state.selectedScenarioKey = null;

    parcelDetailEl.hidden = false;
    addressEl.textContent = props.address || "(no address on file)";
    factParcelEl.textContent = props.parcel_number;
    factAcresEl.textContent = props.acres.toFixed(2);
    factUseEl.textContent = props.land_use || "Unclassified";
    factTaxesEl.textContent = moneyExact(props.current_tax);
    factTaxAcreEl.textContent = moneyExact(props.tax_per_acre) + "/acre";

    underperformEl.hidden = !(props.tax_per_acre < state.breakpoints.p50);

    resultEl.hidden = true;
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
      if (layer !== state.activeLayer) {
        state.geoLayer.resetStyle(layer);
      }
    });
    if (state.activeLayer && !matchesFilter(state.activeLayer.feature.properties)) {
      deselectFeature();
    }
    renderBigNumber();
  }

  function deselectFeature() {
    if (state.activeLayer) {
      state.geoLayer.resetStyle(state.activeLayer);
    }
    state.activeLayer = null;
    state.selectedFeature = null;
    state.selectedScenarioKey = null;
    parcelDetailEl.hidden = true;
  }

  toggleButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      state.revenueView = btn.getAttribute("data-revenue-view");
      Array.prototype.forEach.call(toggleButtons, function (b) {
        b.classList.toggle("is-active", b === btn);
      });
      renderBigNumber();
      if (state.selectedFeature && state.selectedScenarioKey) {
        renderResult(state.selectedFeature, state.selectedScenarioKey);
      }
    });
  });

  filterButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      state.landFilter = btn.getAttribute("data-land-filter");
      Array.prototype.forEach.call(filterButtons, function (b) {
        b.classList.toggle("is-active", b === btn);
      });
      applyFilter();
    });
  });

  if (introEl) {
    var introAlreadySeen = false;
    try { introAlreadySeen = localStorage.getItem(INTRO_SEEN_KEY) === "1"; } catch (e) {}
    if (introAlreadySeen) {
      introEl.hidden = true;
    }
    introDismissBtn.addEventListener("click", function () {
      introEl.hidden = true;
      try { localStorage.setItem(INTRO_SEEN_KEY, "1"); } catch (e) {}
    });
  }

  fetch(geojsonUrl)
    .then(function (res) { return res.json(); })
    .then(function (data) {
      state.metadata = data.metadata;

      var taxPerAcreValues = data.features
        .map(function (f) { return f.properties.tax_per_acre; })
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
    })
    .catch(function (err) {
      loadingEl.textContent = "Could not load parcel data.";
      console.error("Land Ledger: failed to load parcel geojson", err);
    });
})();
