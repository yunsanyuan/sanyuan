(function () {
  var body = document.body;
  if (!body.classList.contains("member-stage")) return;

  var tabs = document.querySelectorAll("[data-preview]");
  if (!tabs.length) return;

  function applyPreview(code) {
    ["lv-normal", "lv-silver", "lv-gold", "lv-diamond"].forEach(function (name) {
      body.classList.remove(name);
    });
    body.classList.add("lv-" + code);

    document.querySelectorAll("[data-level-pane]").forEach(function (pane) {
      pane.hidden = pane.getAttribute("data-level-pane") !== code;
    });

    tabs.forEach(function (tab) {
      tab.classList.toggle("is-on", tab.getAttribute("data-preview") === code);
    });

    var banner = document.querySelector("[data-preview-banner]");
    if (banner) {
      banner.hidden = code === banner.getAttribute("data-mine");
    }
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function (event) {
      event.preventDefault();
      var code = tab.getAttribute("data-preview");
      var mine = tab.getAttribute("data-mine");
      applyPreview(code);
      var url = new URL(window.location.href);
      if (code === mine) {
        url.searchParams.delete("preview");
      } else {
        url.searchParams.set("preview", code);
      }
      window.history.replaceState({}, "", url);
    });
  });
})();
