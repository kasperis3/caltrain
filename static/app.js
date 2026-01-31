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

  function loadStations() {
    return fetch("/stops")
      .then(function (r) {
        if (!r.ok) throw new Error("Stations failed");
        return r.json();
      })
      .then(function (stops) {
        var list = Array.isArray(stops) ? stops : [];
        var seen = {};
        var names = [];
        for (var i = 0; i < list.length; i++) {
          var s = list[i];
          var name = (s.Name || s.name || "").replace(/\s+Caltrain Station (Northbound|Southbound)$/i, "");
          if (name && !seen[name]) {
            seen[name] = true;
            names.push(name);
          }
        }
        return names;
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
    } catch (e) {}
  }

  function saveDefault() {
    var station = el("station");
    var direction = el("direction");
    if (!station || !station.value) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        station: station.value,
        direction: direction ? direction.value : "northbound"
      }));
    } catch (e) {}
  }

  function refreshedNow() {
    var now = new Date();
    var time = now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
    var date = now.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" });
    return "Last refreshed: " + date + " " + time;
  }

  function createTrainLi(t) {
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
    timeEl.textContent = t.time || "—";
    li.appendChild(tag);
    li.appendChild(timeEl);
    return li;
  }

  function trainsCacheKey(station, direction, limit) {
    return station + "|" + (direction || "") + "|" + limit;
  }

  function getCachedTrains(station, direction, limit) {
    var key = trainsCacheKey(station, direction, limit);
    var entry = trainsCache[key];
    if (!entry || Date.now() - entry.cachedAt > TRAINS_CACHE_TTL_MS) return null;
    return entry.data;
  }

  function setCachedTrains(station, direction, limit, data) {
    var key = trainsCacheKey(station, direction, limit);
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

    if (appendOnly && list) {
      var currentCount = list.children.length;
      var newTrains = trains.slice(currentCount);
      for (var i = 0; i < newTrains.length; i++) {
        list.appendChild(createTrainLi(newTrains[i]));
      }
    } else if (list) {
      list.innerHTML = "";
      for (var i = 0; i < trains.length; i++) {
        list.appendChild(createTrainLi(trains[i]));
      }
    }

    if (refreshed) refreshed.textContent = refreshedNow();
    if (seeMore) {
      seeMore.style.display = trains.length >= limit ? "" : "none";
      seeMore.onclick = function () {
        var listEl = el("train-list");
        var currentCount = listEl ? listEl.children.length : 0;
        fetchTrains(currentCount + 5, { append: true });
      };
    }
    var countNote = el("count-note");
    if (countNote) {
      var totalShown = list ? list.children.length : trains.length;
      if (trains.length < limit) {
        countNote.textContent = "Showing " + totalShown + " train" + (totalShown !== 1 ? "s" : "") + " (all predictions available for this stop right now).";
        countNote.style.display = "";
      } else {
        countNote.textContent = "";
        countNote.style.display = "none";
      }
    }
    show(el("results"), true);
    saveDefault();
  }

  function fetchTrains(limitOverride, opts) {
    opts = opts || {};
    var appendOnly = opts.append === true;
    var station = el("station") && el("station").value;
    var direction = el("direction") && el("direction").value;
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
      var cached = getCachedTrains(station, direction, limit);
      if (cached) {
        applyTrainResults(cached, false, limit);
        return;
      }
      show(el("loading"), true);
    }

    var params = "stop=" + encodeURIComponent(station) + "&limit=" + limit;
    if (direction) params += "&direction=" + encodeURIComponent(direction);

    fetch("/next_trains?" + params)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!appendOnly) show(el("loading"), false);
        setCachedTrains(station, direction, limit, data);
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
    if (station) fetchTrains();
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
        if (el("station") && el("station").value) fetchTrains();
      });
    }
  })();

  loadStations()
    .then(function (names) {
      populateStationSelect(names);
      loadDefault();
      var station = el("station") && el("station").value;
      updateDirectionForStation(station);
      setDirection(el("direction") && el("direction").value || "northbound");
      if (station) fetchTrains();
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
