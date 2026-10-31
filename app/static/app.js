// Small progressive enhancements. The site works without this file.
document.addEventListener("DOMContentLoaded", function () {
  var range = document.getElementById("radius_km");
  var output = document.getElementById("radius-value");
  if (range && output) {
    var update = function () {
      output.textContent = range.value + " km";
      var pct = ((range.value - range.min) / (range.max - range.min)) * 100;
      range.style.setProperty("--fill", pct + "%");
    };
    range.addEventListener("input", update);
    update();
  }
});

// After a submit with errors, bring the error summary into view.
document.addEventListener("DOMContentLoaded", function () {
  var banner = document.querySelector("form.signup .error.banner");
  if (banner) banner.scrollIntoView({ block: "start" });
});
