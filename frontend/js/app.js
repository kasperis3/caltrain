(function () {
  var STORAGE_KEY = "caltrain_default";
  var TRAINS_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
  var trainsCache = {};

  function el(id) {
    return document.getElementById(id);
  }

  function show(el, on) {
    if (el) el.style.display = on ? "" : "none";
  }

  function displayNameFromStop(s) {
    return (s.Name || s.name || "").replace(/\s+Caltrain Station (Northbound|Southbound)$/i, "").trim();
  }

  function loadStations() {
    return fetch("/api/stops")
      .then(function (r) {
        if (!r.ok) throw new Error("Stations failed");
        return r.json();
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
        return names;
      });
  }

  function loadStopsInDirection(fromStation, direction) {
    if (!fromStation || !direction) return Promise.resolve([]);
    var params = "from=" + encodeURIComponent(fromStation) + "&direction=" + encodeURIComponent(direction);
    return fetch("/api/stops_in_direction?" + params)
      .then(function (r) { return r.ok ? r.json() : []; })
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

  function populateToSelect(names) {
    var sel = el("to-station");
    if (!sel) return;
    sel.innerHTML = "";
    var optAny = document.createElement("option");
    optAny.value = "";
    optAny.textContent = "Any";
    sel.appendChild(optAny);
    for (var i = 0; i < (names || []).length; i++) {
      var opt = document.createElement("option");
      opt.value = names[i];
      opt.textContent = names[i];
      sel.appendChild(opt);
    }
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

  var NORTH_TERMINUS = "San Francisco";
  var SOUTH_TERMINI = ["Tamien", "Gilroy"];

  var DIR_COLOR_NORTH = "#1565c0";
  var DIR_COLOR_SOUTH = "#e65100";

  function setDirection(value) {
    var hidden = el("direction");
    if (hidden) hidden.value = value;
    var btn = el("direction-btn");
    if (btn) {
      btn.textContent = value === "southbound" ? "↓" : "↑";
      btn.title = value === "southbound" ? "Southbound" : "Northbound";
      btn.setAttribute("aria-label", "Direction: " + (value === "southbound" ? "Southbound" : "Northbound"));
      btn.classList.remove("direction-northbound", "direction-southbound");
      btn.classList.add(value === "southbound" ? "direction-southbound" : "direction-northbound");
      btn.style.color = value === "southbound" ? DIR_COLOR_SOUTH : DIR_COLOR_NORTH;
    }
  }

  function isNorthTerminus(name) {
    return (name || "").trim().toLowerCase() === NORTH_TERMINUS.toLowerCase();
  }
  function isSouthTerminus(name) {
    var n = (name || "").trim().toLowerCase();
    for (var i = 0; i < SOUTH_TERMINI.length; i++) {
      if (SOUTH_TERMINI[i].toLowerCase() === n) return true;
    }
    return false;
  }

  function updateDirectionForStation(stationName) {
    if (!stationName) return;
    var btn = el("direction-btn");
    if (isNorthTerminus(stationName)) {
      setDirection("southbound");
      if (btn) {
        btn.classList.add("disabled");
        btn.setAttribute("aria-disabled", "true");
        btn.disabled = true;
      }
    } else if (isSouthTerminus(stationName)) {
      setDirection("northbound");
      if (btn) {
        btn.classList.add("disabled");
        btn.setAttribute("aria-disabled", "true");
        btn.disabled = true;
      }
    } else {
      if (btn) {
        btn.classList.remove("disabled");
        btn.removeAttribute("aria-disabled");
        btn.disabled = false;
      }
    }
  }

  function loadDefault() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      var data = JSON.parse(raw);
      var stationSel = el("station");
      if (stationSel && data.station) {
        for (var i = 0; i < stationSel.options.length; i++) {
          if (stationSel.options[i].value === data.station) {
            stationSel.selectedIndex = i;
            break;
          }
        }
      }
      var station = el("station") && el("station").value;
      updateDirectionForStation(station);
      var btn = el("direction-btn");
      if (station && btn && !btn.disabled && (data.direction === "northbound" || data.direction === "southbound")) {
        setDirection(data.direction);
      }
      var toSel = el("to-station");
      if (toSel && data.to_station) {
        for (var j = 0; j < toSel.options.length; j++) {
          if (toSel.options[j].value === data.to_station) {
            toSel.selectedIndex = j;
            break;
          }
        }
      }
    } catch (e) {}
  }

  function saveDefault() {
    var station = el("station");
    var direction = el("direction");
    var toStation = el("to-station");
    if (!station || !station.value) return;
    try {
      var saved = {
        station: station.value,
        direction: direction ? direction.value : "northbound"
      };
      if (toStation && toStation.value) saved.to_station = toStation.value;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    } catch (e) {}
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
    var tag = document.createElement("span");
    var slug = (t.service || "other").toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
    if (!slug) slug = "other";
    tag.className = "service-tag service-" + slug;
    tag.textContent = t.service || t.destination || "—";
    var timeEl = document.createElement("span");
    timeEl.className = "time";
    var minUntil = t.minutes_until;
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
    show(el("results"), true);
    saveDefault();
  }

  function fetchTrains(limitOverride, opts) {
    opts = opts || {};
    var appendOnly = opts.append === true;
    var station = el("station") && el("station").value;
    var direction = el("direction") && el("direction").value;
    var toStation = el("to-station") && el("to-station").value;
    var limit = limitOverride != null ? limitOverride : 5;

    if (!station) {
      show(el("error"), true);
      el("error").textContent = "Choose a station.";
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

    var params = "stop=" + encodeURIComponent(station) + "&limit=" + limit;
    if (direction) params += "&direction=" + encodeURIComponent(direction);
    if (toStation) params += "&to=" + encodeURIComponent(toStation);

    fetch("/api/next_trains?" + params)
      .then(function (r) { return r.json(); })
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
    fetchTrains();
  });

  function onStationDirectionOrLimitChange() {
    var station = el("station") && el("station").value;
    updateDirectionForStation(station);
    var direction = el("direction") && el("direction").value;
    if (station && direction) {
      loadStopsInDirection(station, direction).then(function (names) {
        populateToSelect(names);
        var toSel = el("to-station");
        if (toSel) toSel.selectedIndex = 0;
        fetchTrains();
      });
    } else {
      populateToSelect([]);
      if (station) fetchTrains();
    }
  }

  var stationSel = el("station");
  if (stationSel) stationSel.addEventListener("change", onStationDirectionOrLimitChange);
  (function () {
    var dirBtn = el("direction-btn");
    if (dirBtn) {
      dirBtn.addEventListener("click", function () {
        if (dirBtn.disabled) return;
        var next = el("direction").value === "northbound" ? "southbound" : "northbound";
        setDirection(next);
        var station = el("station") && el("station").value;
        var direction = el("direction") && el("direction").value;
        if (station && direction) {
          loadStopsInDirection(station, direction).then(function (names) {
            populateToSelect(names);
            var toSel = el("to-station");
            if (toSel) toSel.selectedIndex = 0;
            fetchTrains();
          });
        } else if (station) fetchTrains();
      });
    }
  })();
  var toSel = el("to-station");
  if (toSel) toSel.addEventListener("change", function () {
    if (el("station") && el("station").value) fetchTrains();
  });

  function updateApiStatus() {
    var dot = document.querySelector(".api-status-dot");
    var text = document.querySelector(".api-status-text");
    fetch("/api/health")
      .then(function (r) { return r.json(); })
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

  loadStations()
    .then(function (names) {
      populateStationSelect(names);
      loadDefault();
      var station = el("station") && el("station").value;
      updateDirectionForStation(station);
      var direction = el("direction") && el("direction").value || "northbound";
      setDirection(direction);
      if (station && direction) {
        loadStopsInDirection(station, direction).then(function (toNames) {
          populateToSelect(toNames);
          loadDefault();
          if (station) fetchTrains();
        });
      } else if (station) fetchTrains();
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
