/* Questionnaire progress and duration tracking. No dependencies. */
(function () {
  "use strict";

  var form = document.querySelector("[data-survey]");
  if (!form) return;

  var started = Date.now();
  var total = Number(form.getAttribute("data-total") || 0);
  var buffer = form.querySelector('input[name="duration_seconds"]');
  var bar = document.querySelector("[data-progress-bar]");
  var label = document.querySelector("[data-progress-text]");
  var sections = Array.prototype.slice.call(
    document.querySelectorAll("[data-section]")
  );
  var radios = Array.prototype.slice.call(
    form.querySelectorAll('input[type="radio"]')
  );
  var itemNames = [];
  radios.forEach(function (input) {
    if (itemNames.indexOf(input.name) === -1) itemNames.push(input.name);
  });
  var selects = Array.prototype.slice.call(form.querySelectorAll("select"));
  var channels = Array.prototype.slice.call(
    form.querySelectorAll('input[name="channels"]')
  );
  var consent = form.querySelector('input[name="consent"]');
  var softwareDetails = form.querySelector("[data-software-details]");
  var softwareRadios = Array.prototype.slice.call(
    form.querySelectorAll('input[name="needs_software"]')
  );

  function syncSoftware() {
    if (!softwareDetails) return;
    var chosen = null;
    softwareRadios.forEach(function (input) {
      if (input.checked) chosen = input.value;
    });
    var show = chosen === "yes";
    softwareDetails.hidden = !show;
    var textarea = softwareDetails.querySelector("textarea");
    if (textarea) textarea.required = show;
  }

  function answered() {
    var count = 0;
    itemNames.forEach(function (name) {
      if (form.querySelector('input[name="' + name + '"]:checked')) count += 1;
    });
    selects.forEach(function (select) {
      if (select.value) count += 1;
    });
    if (channels.some(function (box) { return box.checked; })) count += 1;
    if (consent && consent.checked) count += 1;
    return count;
  }

  function update() {
    syncSoftware();
    var done = answered();
    var pct = total ? Math.round((100 * done) / total) : 0;
    if (bar) bar.style.width = pct + "%";
    if (label) label.textContent = done + " of " + total + " answered";

    sections.forEach(function (section) {
      var group = Array.prototype.slice.call(
        section.querySelectorAll('input[type="radio"]')
      );
      var names = [];
      group.forEach(function (input) {
        if (names.indexOf(input.name) === -1) names.push(input.name);
      });
      if (!names.length) return;
      var complete = names.every(function (name) {
        return section.querySelector('input[name="' + name + '"]:checked');
      });
      section.classList.toggle("done", complete);
    });
  }

  form.addEventListener("change", update);
  form.addEventListener("input", update);

  form.addEventListener("submit", function () {
    if (buffer) buffer.value = Math.round((Date.now() - started) / 1000);
  });

  update();

  var firstProblem = form.querySelector(".missing");
  if (firstProblem) {
    firstProblem.scrollIntoView({ block: "center", behavior: "smooth" });
  }
})();
