(function () {
  var RECENT_ROUTES_KEY = "caltrain_recent_routes";
  var LEGACY_STORAGE_KEY = "caltrain_default";
  var MAX_RECENT_ROUTES = 5;
  var AUTO_LOAD_MAX_AGE_MS = 24 * 60 * 60 * 1000;
  var TRAINS_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
  var trainsCache = {};

  function el(id) {
    return document.getElementById(id);
  }

  function show(el, on) {
    if (el) el.style.display = on ? "" : "none";
  }

  function selectOrAddStation(stationSel, station) {
    if (!stationSel || !station) return;
    for (var i = 0; i < stationSel.options.length; i++) {
      if (stationSel.options[i].value === station) {
        stationSel.selectedIndex = i;
        return;
      }
    }
    var opt = document.createElement("option");
    opt.value = station;
    opt.textContent = station;
    stationSel.appendChild(opt);
    stationSel.selectedIndex = stationSel.options.length - 1;
  }

  function applyNearestStation(data) {
    var station = data.station;
    if (!station) return false;
    var override = el("stop-id-override");
    if (override && data.stop_id) override.value = data.stop_id;
    selectOrAddStation(el("station"), station);
    populateToSelect(station);
    var toSel = el("to-station");
    if (toSel) toSel.selectedIndex = 0;
    return true;
  }

  function safeJson(r, fallback) {
    return r.text().then(function (text) {
      try { return JSON.parse(text); } catch (e) { return fallback !== undefined ? fallback : null; }
    });
  }

  function displayNameFromStop(s) {
    return (s.Name || s.name || "").replace(/\s+Caltrain Station (Northbound|Southbound)$/i, "").trim();
  }

  function loadStations() {
    return fetch("/api/stops")
      .then(function (r) {
        if (!r.ok) throw new Error("Stations failed");
        return safeJson(r, []);
      })
      .then(function (stops) {
        var list = Array.isArray(stops) ? stops : [];
        var seen = {};
        var names = [];
        for (var i = 0; i < list.length; i++) {
          var name = displayNameFromStop(list[i]);
          if (name && !seen[name]) {
            seen[name] = true;
            names.push(name);
          }
        }
        allStationNames = names;
        return names;
      });
  }

  function loadStopsInDirection(fromStation, direction) {
    if (!fromStation || !direction) return Promise.resolve([]);
    var params = "from=" + encodeURIComponent(fromStation) + "&direction=" + encodeURIComponent(direction);
    return fetch("/api/stops_in_direction?" + params)
      .then(function (r) { return r.ok ? safeJson(r, []) : []; })
      .then(function (stops) {
        var list = Array.isArray(stops) ? stops : [];
        var names = [];
        for (var i = 0; i < list.length; i++) {
          var name = displayNameFromStop(list[i]);
          if (name) names.push(name);
        }
        return names;
      })
      .catch(function () { return []; });
  }

  var allStationNames = [];

  function populateToSelect(excludeFrom) {
    var sel = el("to-station");
    if (!sel) return;
    sel.innerHTML = "";
    var opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "Select destination";
    sel.appendChild(opt0);
    var names = (excludeFrom && allStationNames.length) ? allStationNames.filter(function (n) { return n !== excludeFrom; }) : [];
    for (var i = 0; i < names.length; i++) {
      var opt = document.createElement("option");
      opt.value = names[i];
      opt.textContent = names[i];
      sel.appendChild(opt);
    }
  }

  function getDirectionAndFetch() {
    var fromStation = el("station") && el("station").value;
    var toStation = el("to-station") && el("to-station").value;
    if (!fromStation || !toStation) return;
    if (fromStation === toStation) {
      show(el("error"), true);
      el("error").textContent = "From and To must be different stations.";
      return;
    }
    var params = "from=" + encodeURIComponent(fromStation) + "&to=" + encodeURIComponent(toStation);
    fetch("/api/direction?" + params)
      .then(function (r) { return safeJson(r, {}); })
      .then(function (data) {
        var dir = data.direction;
        if (!dir) {
          show(el("error"), true);
          el("error").textContent = "Could not determine direction. Please check your stations.";
          return;
        }
        var hidden = el("direction");
        if (hidden) hidden.value = dir;
        fetchTrains();
      })
      .catch(function () {
        show(el("error"), true);
        el("error").textContent = "Could not determine direction.";
      });
  }

  function populateStationSelect(names) {
    var sel = el("station");
    if (!sel) return;
    sel.innerHTML = "";
    var opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "Select station";
    sel.appendChild(opt0);
    for (var i = 0; i < names.length; i++) {
      var opt = document.createElement("option");
      opt.value = names[i];
      opt.textContent = names[i];
      sel.appendChild(opt);
    }
  }

  function routePairKey(from, to) {
    return from.toLowerCase() + "|" + to.toLowerCase();
  }

  function persistRecentRoutes(routes) {
    try {
      localStorage.setItem(RECENT_ROUTES_KEY, JSON.stringify({ routes: routes }));
    } catch (e) {}
  }

  function loadRecentRoutes() {
    try {
      var raw = localStorage.getItem(RECENT_ROUTES_KEY);
      if (raw) {
        var data = JSON.parse(raw);
        return Array.isArray(data.routes) ? data.routes : [];
      }
      var legacyRaw = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (legacyRaw) {
        var legacy = JSON.parse(legacyRaw);
        if (legacy.station && legacy.to_station) {
          var migrated = [{ from: legacy.station, to: legacy.to_station, usedAt: Date.now() }];
          persistRecentRoutes(migrated);
          return migrated;
        }
      }
    } catch (e) {}
    return [];
  }

  function saveRecentRoute(from, to) {
    if (!from || !to || from === to) return;
    var routes = loadRecentRoutes();
    var key = routePairKey(from, to);
    routes = routes.filter(function (r) {
      return routePairKey(r.from, r.to) !== key;
    });
    routes.unshift({ from: from, to: to, usedAt: Date.now() });
    if (routes.length > MAX_RECENT_ROUTES) {
      routes = routes.slice(0, MAX_RECENT_ROUTES);
    }
    persistRecentRoutes(routes);
    renderRecentRoutes();
  }

  function removeRecentRoute(from, to) {
    if (!from || !to) return;
    var key = routePairKey(from, to);
    var routes = loadRecentRoutes().filter(function (r) {
      return routePairKey(r.from, r.to) !== key;
    });
    persistRecentRoutes(routes);
    renderRecentRoutes();
  }

  function applyRoute(from, to) {
    if (!from || !to) return;
    clearStopIdOverride();
    selectOrAddStation(el("station"), from);
    populateToSelect(from);
    selectOrAddStation(el("to-station"), to);
    getDirectionAndFetch();
  }

  function renderRecentRoutes() {
    var container = el("recent-routes");
    var list = el("recent-routes-list");
    if (!container || !list) return;
    var routes = loadRecentRoutes();
    list.innerHTML = "";
    if (!routes.length) {
      show(container, false);
      return;
    }
    for (var i = 0; i < routes.length; i++) {
      var route = routes[i];
      if (!route.from || !route.to) continue;
      var wrap = document.createElement("div");
      wrap.className = "recent-route-chip-wrap";

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "recent-route-chip";
      btn.textContent = route.from + " \u2192 " + route.to;
      btn.setAttribute("aria-label", "Use route from " + route.from + " to " + route.to);

      var removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "recent-route-chip__remove";
      removeBtn.textContent = "\u00d7";
      removeBtn.setAttribute("aria-label", "Remove route from " + route.from + " to " + route.to);

      (function (from, to) {
        btn.addEventListener("click", function () {
          applyRoute(from, to);
        });
        removeBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          removeRecentRoute(from, to);
        });
      })(route.from, route.to);

      wrap.appendChild(btn);
      wrap.appendChild(removeBtn);
      list.appendChild(wrap);
    }
    show(container, list.children.length > 0);
  }

  function autoLoadRecentIfFresh(fromHint) {
    var routes = loadRecentRoutes();
    if (!routes.length) return;
    var latest = routes[0];
    if (!latest.from || !latest.to) return;
    if (Date.now() - latest.usedAt > AUTO_LOAD_MAX_AGE_MS) return;
    if (fromHint && latest.from.toLowerCase() !== fromHint.toLowerCase()) return;
    applyRoute(latest.from, latest.to);
  }

  function refreshedNow() {
    var now = new Date();
    var time = now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
    var date = now.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" });
    return "Last refreshed: " + date + " " + time;
  }

  function createTrainLi(t, opts) {
    opts = opts || {};
    var isFirstRow = opts.isFirstRow === true;
    var hasToStation = opts.hasToStation === true;
    var li = document.createElement("li");
    var minUntil = t.minutes_until;
    if (minUntil != null && minUntil >= 0 && minUntil <= 10) li.classList.add("train-row-soon");
    var tag = document.createElement("span");
    var slug = (t.service || "other").toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
    if (!slug) slug = "other";
    tag.className = "service-tag service-" + slug;
    tag.textContent = t.service || t.destination || "—";
    var timeEl = document.createElement("span");
    timeEl.className = "time";
    if (minUntil != null && minUntil >= 0 && minUntil <= 10) timeEl.classList.add("time-soon");
    var timeStr = (t.time || "—").replace(/\s+(PST|PDT)$/i, "");
    timeEl.textContent = timeStr;
    var travelEl = document.createElement("span");
    travelEl.className = "travel-minutes";
    if (t.travel_minutes != null && t.travel_minutes >= 0) {
      travelEl.textContent = t.travel_minutes + " min";
    } else if (isFirstRow && !hasToStation) {
      travelEl.textContent = "pick a To station above";
      travelEl.classList.add("travel-minutes--hint");
    } else {
      travelEl.classList.add("travel-minutes--placeholder");
    }
    li.appendChild(tag);
    li.appendChild(timeEl);
    li.appendChild(travelEl);
    return li;
  }

  function trainsCacheKey(station, direction, limit, toStation) {
    return station + "|" + (direction || "") + "|" + limit + "|" + (toStation || "");
  }

  function getCachedTrains(station, direction, limit, toStation) {
    var key = trainsCacheKey(station, direction, limit, toStation);
    var entry = trainsCache[key];
    if (!entry || Date.now() - entry.cachedAt > TRAINS_CACHE_TTL_MS) return null;
    return entry.data;
  }

  function setCachedTrains(station, direction, limit, toStation, data) {
    var key = trainsCacheKey(station, direction, limit, toStation);
    trainsCache[key] = { data: data, cachedAt: Date.now() };
  }

  function applyTrainResults(data, appendOnly, limit) {
    if (data.message) {
      el("message").textContent = data.message;
      show(el("message"), true);
      return;
    }
    if (!data.stop_id) {
      el("error").textContent = data.message || "Station not found.";
      show(el("error"), true);
      return;
    }
    var refreshed = el("refreshed");
    var list = el("train-list");
    var seeMore = el("see-more");
    var trains = data.trains || [];

    var toStation = el("to-station") && el("to-station").value;
    var hasToStation = !!toStation;
    if (appendOnly && list) {
      var currentCount = list.children.length;
      var newTrains = trains.slice(currentCount);
      for (var i = 0; i < newTrains.length; i++) {
        list.appendChild(createTrainLi(newTrains[i], { hasToStation: hasToStation }));
      }
    } else if (list) {
      list.innerHTML = "";
      for (var i = 0; i < trains.length; i++) {
        list.appendChild(createTrainLi(trains[i], { isFirstRow: i === 0, hasToStation: hasToStation }));
      }
    }

    var headerTime = el("results-header-time");
    if (headerTime) {
      var tz = "";
      try {
        var parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", timeZoneName: "short" }).formatToParts(new Date());
        var tzPart = parts.find(function (p) { return p.type === "timeZoneName"; });
        if (tzPart) tz = " (" + tzPart.value + ")";
      } catch (e) {}
      headerTime.textContent = "Departure Time" + tz;
    }
    if (refreshed) refreshed.textContent = refreshedNow();
    var sourceEl = el("data-source");
    if (sourceEl) {
      var labels = { gtfs_realtime: "Real-time", stop_timetable: "Scheduled", stop_monitoring: "Live" };
      var label = labels[data.data_source] || "";
      sourceEl.textContent = label ? "Source: " + label + " feed" : "";
      sourceEl.style.display = label ? "" : "none";
    }
    if (seeMore) {
      seeMore.style.display = trains.length >= limit ? "" : "none";
      seeMore.onclick = function () {
        var listEl = el("train-list");
        var currentCount = listEl ? listEl.children.length : 0;
        fetchTrains(currentCount + 5, { append: true });
      };
    }
    var dirLabel = el("direction-label");
    if (dirLabel) {
      var dir = el("direction") && el("direction").value;
      dirLabel.textContent = dir ? dir.charAt(0).toUpperCase() + dir.slice(1) : "";
      dirLabel.style.display = dir ? "" : "none";
    }
    show(el("results"), true);
    var fromStation = el("station") && el("station").value;
    var toStationVal = el("to-station") && el("to-station").value;
    if (fromStation && toStationVal) saveRecentRoute(fromStation, toStationVal);
  }

  function fetchTrains(limitOverride, opts) {
    opts = opts || {};
    var appendOnly = opts.append === true;
    var station = el("station") && el("station").value;
    var direction = el("direction") && el("direction").value;
    var toStation = el("to-station") && el("to-station").value;
    var limit = limitOverride != null ? limitOverride : 5;

    if (!station || !toStation) {
      show(el("error"), true);
      el("error").textContent = "Choose From and To stations.";
      show(el("message"), false);
      show(el("results"), false);
      return;
    }

    if (!appendOnly) {
      show(el("error"), false);
      show(el("message"), false);
      show(el("results"), false);
      var cached = getCachedTrains(station, direction, limit, toStation);
      if (cached) {
        applyTrainResults(cached, false, limit);
        return;
      }
      show(el("loading"), true);
    }

    var stopIdOverride = el("stop-id-override") && el("stop-id-override").value;
    var stopParam = stopIdOverride || station;
    var params = "stop=" + encodeURIComponent(stopParam) + "&limit=" + limit;
    if (direction) params += "&direction=" + encodeURIComponent(direction);
    if (toStation) params += "&to=" + encodeURIComponent(toStation);

    fetch("/api/next_trains?" + params)
      .then(function (r) { return safeJson(r, {}); })
      .then(function (data) {
        if (!appendOnly) show(el("loading"), false);
        setCachedTrains(station, direction, limit, toStation, data);
        applyTrainResults(data, appendOnly, limit);
      })
      .catch(function (err) {
        show(el("loading"), false);
        el("error").textContent = err.message || "Something went wrong.";
        show(el("error"), true);
      });
  }

  el("form").addEventListener("submit", function (e) {
    e.preventDefault();
    getDirectionAndFetch();
  });

  function clearStopIdOverride() {
    var o = el("stop-id-override");
    if (o) o.value = "";
  }

  function onFromChange() {
    clearStopIdOverride();
    var station = el("station") && el("station").value;
    populateToSelect(station);
    var toSel = el("to-station");
    if (toSel) toSel.selectedIndex = 0;
    if (station && (el("to-station") && el("to-station").value)) getDirectionAndFetch();
  }

  function onToChange() {
    clearStopIdOverride();
    if (el("station") && el("station").value && el("to-station") && el("to-station").value) {
      getDirectionAndFetch();
    }
  }

  var stationSel = el("station");
  if (stationSel) stationSel.addEventListener("change", onFromChange);
  var toSel = el("to-station");
  if (toSel) toSel.addEventListener("change", onToChange);

  var reverseBtn = el("reverse-btn");
  if (reverseBtn) {
    function doReverse() {
      var fromSel = el("station");
      var toSelEl = el("to-station");
      if (!fromSel || !toSelEl) return;
      var fromVal = fromSel.value;
      var toVal = toSelEl.value;
      if (!fromVal || !toVal) return;
      clearStopIdOverride();
      fromSel.value = toVal;
      populateToSelect(toVal);
      toSelEl.value = fromVal;
      getDirectionAndFetch();
    }
    reverseBtn.addEventListener("click", doReverse);
    reverseBtn.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        doReverse();
      }
    });
  }

  var useLocationBtn = el("use-location-btn");
  if (useLocationBtn) {
    useLocationBtn.addEventListener("click", function () {
      if (!navigator.geolocation) {
        show(el("message"), true);
        el("message").textContent = "Geolocation not supported. Please pick a station.";
        return;
      }
      useLocationBtn.disabled = true;
      show(el("error"), false);
      show(el("message"), true);
      el("message").textContent = "Getting location…";
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          var lat = Number(pos.coords.latitude).toFixed(6);
          var lon = Number(pos.coords.longitude).toFixed(6);
          var params = "lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lon) + "&max_miles=10";
          fetch("/api/nearest_station?" + params)
            .then(function (r) { return safeJson(r, { station: null, direction: null, stop_id: null }); })
            .then(function (data) {
              useLocationBtn.disabled = false;
              if (applyNearestStation(data)) {
                show(el("message"), false);
              } else {
                el("message").textContent = "No station within 10 miles. Please pick a station.";
                show(el("message"), true);
              }
            })
            .catch(function () {
              useLocationBtn.disabled = false;
              el("message").textContent = "Could not find nearest station. Please pick a station.";
              show(el("message"), true);
            });
        },
        function (err) {
          useLocationBtn.disabled = false;
          var msg = "Could not get location. Please pick a station.";
          if (err && err.code === 1) {
            msg = "Location permission was denied. You can enable it in your browser\u2019s settings for this site.";
          } else if (err && err.code === 3) {
            msg = "Location request timed out. Please try again or pick a station.";
          } else if (err && err.code === 2) {
            msg = "Location unavailable. Please pick a station.";
          }
          el("message").textContent = msg;
          show(el("message"), true);
        }
      );
    });
  }

  function updateApiStatus() {
    var dot = document.querySelector(".api-status-dot");
    var text = document.querySelector(".api-status-text");
    fetch("/api/health")
      .then(function (r) { return safeJson(r, {}); })
      .then(function (data) {
        var ok = data["511_api"] === "healthy";
        if (dot) {
          dot.className = "api-status-dot " + (ok ? "api-status-ok" : "api-status-down");
        }
        if (text) text.textContent = ok ? "511 API healthy" : "511 API unreachable";
      })
      .catch(function () {
        if (dot) dot.className = "api-status-dot api-status-down";
        if (text) text.textContent = "511 API unreachable";
      });
  }
  updateApiStatus();
  setInterval(updateApiStatus, 60000);

  function finishInitWithoutGeo() {
    clearStopIdOverride();
    autoLoadRecentIfFresh();
  }

  function tryLocationOnLoad() {
    if (!navigator.geolocation) {
      finishInitWithoutGeo();
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        var lat = Number(pos.coords.latitude).toFixed(6);
        var lon = Number(pos.coords.longitude).toFixed(6);
        var params = "lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lon) + "&max_miles=10";
        fetch("/api/nearest_station?" + params)
          .then(function (r) { return safeJson(r, { station: null, direction: null, stop_id: null }); })
          .then(function (data) {
            if (applyNearestStation(data)) {
              autoLoadRecentIfFresh(data.station);
            } else {
              finishInitWithoutGeo();
            }
          })
          .catch(function () {
            finishInitWithoutGeo();
          });
      },
      function () {
        finishInitWithoutGeo();
      },
      { timeout: 5000, maximumAge: 0 }
    );
  }

  loadStations()
    .then(function (names) {
      populateStationSelect(names);
      renderRecentRoutes();
      tryLocationOnLoad();
    })
    .catch(function () {
      var sel = el("station");
      if (sel) {
        sel.innerHTML = "";
        var opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "Could not load stations";
        sel.appendChild(opt);
      }
    });
})();
