// Article Reels Dashboard - client-side JS
// Reads window.__dashboardData (embedded by generate_dashboard.py)
// and powers live countdown timers, post age updates, and refresh.

(function () {
  "use strict";

  var state = {
    reels: [],
    pages: {},
    recent_posts: []
  };

  // Populate state from the embedded JSON object.
  function initState(data) {
    if (!data) return;
    if (Array.isArray(data.reels)) state.reels = data.reels;
    if (data.pages_data) state.pages = data.pages_data;
    if (Array.isArray(data.recent_posts)) {
      state.recent_posts = data.recent_posts;
    }
  }

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function formatCountdown(dtStr) {
    var dt = new Date(dtStr);
    if (isNaN(dt.getTime())) return "-";
    var diff = dt.getTime() - Date.now();
    if (diff <= 0) {
      return '<span style="color:#f87171;font-weight:700;">now</span>';
    }
    var days = Math.floor(diff / 86400000);
    var hours = Math.floor((diff % 86400000) / 3600000);
    var mins = Math.floor((diff % 3600000) / 60000);
    var secs = Math.floor((diff % 60000) / 1000);
    var parts = [];
    if (days > 0) parts.push(days + "d");
    if (hours > 0) parts.push(hours + "h");
    if (mins > 0) parts.push(mins + "m");
    parts.push(secs + "s");
    var color = (days > 0 || hours > 0) ? "#fbbf24" : "#34d399";
    return '<span style="color:' + color + ';font-weight:600;">in '
      + parts.join(" ") + "</span>";
  }

  // Reel countdown ids are 1-based (cd-1, cd-2, ...).
  function updateCountdowns() {
    var els = document.querySelectorAll(".countdown");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var idx = parseInt(el.id.replace("cd-", ""), 10);
      var reel = state.reels[idx - 1];
      if (reel) {
        el.innerHTML = formatCountdown(reel.when);
      }
    }
  }

  function timeAgo(dt) {
    if (isNaN(dt.getTime())) return "-";
    var diff = Date.now() - dt.getTime();
    if (diff < 0) return "future";
    if (diff < 60000) return "just now";
    var m = Math.floor(diff / 60000);
    if (m < 60) return m + "m ago";
    var h = Math.floor(m / 60);
    if (h < 24) return h + "h ago";
    var d = Math.floor(h / 24);
    if (d < 30) return d + "d ago";
    return Math.floor(d / 30) + "mo ago";
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }


  function reRenderPosts() {
    var cards = document.querySelectorAll(".page-card");
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var key = card.getAttribute("data-page-key");
      var data = state.pages[key];
      if (!data) continue;
      var list = card.querySelector(".post-list");
      if (!list) continue;
      var posts = (data.posts || []).slice(0, 8);
      if (!posts.length) {
        list.innerHTML = '<p class="empty">No posts scraped yet.</p>';
        continue;
      }
      var html = "";
      for (var j = 0; j < posts.length; j++) {
        var p = posts[j];
        var msg = (p.message || "").trim().slice(0, 200);
        var permalink = p.permalink_url || "#";
        var age = timeAgo(new Date(p.created_time || ""));
        var reaction = (p.reactions && p.reactions.summary)
          ? p.reactions.summary.total_count || 0 : 0;
        var shares = (p.shares && p.shares.count)
          ? p.shares.count : 0;
        html += '<div class="post-item">'
          + '<div class="post-body">'
          + '<div class="post-message">'
          + (msg ? escapeHtml(msg) : "<i>[no message]</i>")
          + "</div>"
          + '<div class="post-meta">'
          + '<a href="' + escapeHtml(permalink)
          + '" target="_blank" rel="noopener">'
          + escapeHtml(p.id || "unknown") + "</a>"
          + '<span class="post-age">' + escapeHtml(age) + "</span>"
          + '<span class="post-reactions"><i class="heart"></i> '
          + reaction + "</span>"
          + '<span class="post-shares"><i class="share"></i>'
          + shares + "</span>"
          + "</div></div></div>";
      }
      list.innerHTML = html;
    }
  }

  function refreshClock() {
    var el = document.getElementById("last-updated-time");
    if (el) {
      var now = new Date();
      el.textContent = now.getUTCFullYear() + "-"
        + pad(now.getUTCMonth() + 1) + "-"
        + pad(now.getUTCDate()) + " "
        + pad(now.getUTCHours()) + ":"
        + pad(now.getUTCMinutes()) + ":"
        + pad(now.getUTCSeconds()) + " UTC";
    }
    updateCountdowns();
    reRenderPosts();
  }

  function refreshData() {
    var btn = document.getElementById("refresh-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Updating...";
    }
    fetch("dashboard.html?_=" + Date.now())
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var m = html.match(
          /window\.__dashboardData = (\{[\s\S]*?\});\s*<\/script>/);
        if (m) {
          try {
            var data = JSON.parse(m[1]);
            initState(data);
            refreshClock();
          } catch (e) { /* keep current view */ }
        }
      })
      .catch(function () { /* offline: keep current view */ })
      .then(function () {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Refresh data";
        }
      });
  }

  function initDashboard() {
    initState(window.__dashboardData);
    refreshClock();
    setInterval(refreshClock, 1000);
    setInterval(reRenderPosts, 30000);
    var btn = document.getElementById("refresh-btn");
    if (btn) btn.addEventListener("click", refreshData);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDashboard);
  } else {
    initDashboard();
  }
})();
