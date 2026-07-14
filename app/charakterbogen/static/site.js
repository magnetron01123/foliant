// Minimal (AUFTRAG §6.2): sperrt den Knopf und zeigt den Arbeitsstatus. Das Formular
// funktioniert grundsätzlich auch ohne JavaScript.
(function () {
  var form = document.getElementById("form");
  var knopf = document.getElementById("knopf");
  var status = document.getElementById("status");
  if (!form) return;
  form.addEventListener("submit", function () {
    knopf.disabled = true;
    if (status) status.hidden = false;
  });
})();
