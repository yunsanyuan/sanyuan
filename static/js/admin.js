(function () {
  function unwrapActionSelects() {
    var $ = (window.django && django.jQuery) || window.jQuery;
    if (!$ || !$.fn) {
      return;
    }
    $(".actions select").each(function () {
      var $el = $(this);
      if ($.fn.select2 && $el.hasClass("select2-hidden-accessible")) {
        try {
          $el.select2("destroy");
        } catch (err) {
          /* ignore */
        }
      }
      $el.addClass("form-control");
    });
    $(".actions .select2-container").remove();
  }

  function bind() {
    unwrapActionSelects();
    window.setTimeout(unwrapActionSelects, 80);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
  window.addEventListener("load", bind);
})();
