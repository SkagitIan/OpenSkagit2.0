(function () {
  "use strict";

  var section = document.getElementById("tax-compare-map-section");
  if (!section) return;

  var areasUrl = section.getAttribute("data-levy-areas-url");
  var currentLevyCode = section.getAttribute("data-current-levy-code") || "";
  var loadingEl = document.getElementById("os-tcm-loading");
  var legendMinEl = document.getElementById("os-tcm-legend-min");
  var legendMaxEl = document.getElementById("os-tcm-legend-max");
  var legendMedianEl = document.getElementById("os-tcm-legend-median");
  var legendGradientEl = document.getElementById("os-tcm-legend-gradient");

  // Validated sequential teal ramp (dataviz skill: light->dark, ordinal check passes).
  var RAMP = ["#4fbcb9", "#2fa6a3", "#1c8688", "#106466", "#08484a"];
  var MUTED = "#9aa5ad";
  var MIN_SAMPLE = 5;

  var state = {
    map: null,
    geoLayer: null,
    activeLayer: null,
    domain: null, // { min, max }
  };

  function percentile(sorted, p) {
    if (!sorted.length) return 0;
    var idx = (sorted.length - 1) * p;
    var lo = Math.floor(idx), hi = Math.ceil(idx);
    if (lo === hi) return sorted[lo];
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }

  function hexToRgb(hex) {
    var n = parseInt(hex.replace("#", ""), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function rgbToHex(rgb) {
    return "#" + rgb.map(function (v) {
      return Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
    }).join("");
  }

  function rampColor(t) {
    t = Math.max(0, Math.min(1, t));
    var steps = RAMP.length - 1;
    var pos = t * steps;
    var lo = Math.floor(pos), hi = Math.ceil(pos);
    if (lo === hi) return RAMP[lo];
    var loRgb = hexToRgb(RAMP[lo]), hiRgb = hexToRgb(RAMP[hi]);
    var frac = pos - lo;
    return rgbToHex(loRgb.map(function (v, i) { return v + (hiRgb[i] - v) * frac; }));
  }

  function colorFor(rate) {
    if (rate === null || rate === undefined || !state.domain) return MUTED;
    var span = state.domain.max - state.domain.min;
    var t = span > 0 ? (rate - state.domain.min) / span : 0.5;
    return rampColor(t);
  }

  function styleFeature(feature) {
    var props = feature.properties;
    var lowSample = (props.parcel_count || 0) < MIN_SAMPLE;
    var isCurrent = currentLevyCode && props.levy_code === currentLevyCode;
    return {
      color: isCurrent ? "#ffffff" : "rgba(61,77,92,0.35)",
      weight: isCurrent ? 3 : 0.7,
      fillColor: lowSample ? MUTED : colorFor(props.median_rate),
      fillOpacity: lowSample ? 0.35 : 0.78,
    };
  }

  function popupHtml(props) {
    var tone = props.verdict_tone || "typical";
    var toneLabel = tone === "high" ? "Above county median" : tone === "low" ? "Below county median" : "About typical";
    var lowSample = (props.parcel_count || 0) < MIN_SAMPLE;
    var html = '<div class="os-tcm-popup">';
    html += '<strong>' + (props.area_label || props.levy_code) + '</strong>';
    html += '<span class="os-tcm-popup__code">Levy ' + props.levy_code + '</span>';
    if (lowSample) {
      html += '<p class="os-tcm-popup__note">Only ' + props.parcel_count + ' parcels in this levy area &mdash; too few for a reliable comparison.</p>';
    } else {
      html += '<p class="os-tcm-popup__rate">' + (props.median_rate_fmt || "N/A") + ' <span>per $1,000</span></p>';
      html += '<p class="os-tax-rate-verdict--' + tone + ' os-tcm-popup__tone">' + toneLabel;
      if (props.delta_fmt) html += ' &mdash; ' + props.delta_fmt + ' vs county median';
      html += '</p>';
    }
    html += '</div>';
    return html;
  }

  function selectFeature(layer) {
    if (state.activeLayer && state.activeLayer !== layer) {
      state.geoLayer.resetStyle(state.activeLayer);
    }
    state.activeLayer = layer;
    layer.bringToFront();
  }

  fetch(areasUrl).then(function (res) {
    if (!res.ok) throw new Error("levy areas request failed with HTTP " + res.status);
    return res.json();
  }).then(function (data) {
    var rates = data.features
      .map(function (f) { return f.properties.median_rate; })
      .filter(function (v) { return v !== null && v !== undefined; })
      .sort(function (a, b) { return a - b; });

    // Tight p10-p90 clip: a few extreme outlier levy codes otherwise stretch the
    // ramp domain so wide that the bulk of ordinary areas cluster in one band.
    state.domain = { min: percentile(rates, 0.10), max: percentile(rates, 0.90) };

    state.map = L.map("os-tcm-map", { scrollWheelZoom: false });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
      maxZoom: 19,
      detectRetina: true,
    }).addTo(state.map);

    state.geoLayer = L.geoJSON(data, {
      style: styleFeature,
      onEachFeature: function (feature, layer) {
        layer.bindPopup(popupHtml(feature.properties));
        layer.on("click", function () { selectFeature(layer); });
      },
    }).addTo(state.map);

    var currentLayer = null;
    state.geoLayer.eachLayer(function (layer) {
      if (currentLevyCode && layer.feature.properties.levy_code === currentLevyCode) {
        currentLayer = layer;
      }
    });
    if (currentLayer) {
      state.map.fitBounds(currentLayer.getBounds(), { padding: [40, 40], maxZoom: 13 });
    } else {
      state.map.fitBounds(state.geoLayer.getBounds(), { padding: [16, 16] });
    }

    if (legendMinEl) legendMinEl.textContent = "$" + state.domain.min.toFixed(2);
    if (legendMaxEl) legendMaxEl.textContent = "$" + state.domain.max.toFixed(2);
    if (legendMedianEl && data.county_median_rate_fmt) {
      legendMedianEl.textContent = "County median " + data.county_median_rate_fmt;
      var span = state.domain.max - state.domain.min;
      if (span > 0 && data.county_median_rate !== null && data.county_median_rate !== undefined) {
        var pct = Math.max(0, Math.min(100, (data.county_median_rate - state.domain.min) / span * 100));
        legendMedianEl.style.left = pct + "%";
      }
    }
    if (legendGradientEl) {
      legendGradientEl.style.background = "linear-gradient(90deg, " + RAMP.join(", ") + ")";
    }

    if (loadingEl) loadingEl.hidden = true;
  }).catch(function (err) {
    if (loadingEl) loadingEl.textContent = "The comparison map could not be loaded.";
    console.error("Tax compare map: failed to load levy area data", err);
  });
})();
