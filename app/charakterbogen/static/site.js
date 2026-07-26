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

// Kopier-Knoepfe: 'data-kopieren="<ziel-id>"' statt fester IDs - so teilen sich
// MCP-Link und Projektanweisung EINE Logik. Clipboard-API (https) mit Fallback auf
// Auswahl+execCommand (http/alt).
(function () {
  function verdrahte(knopf) {
    var feld = document.getElementById(knopf.getAttribute("data-kopieren"));
    if (!feld) return;

    function bestaetigt() {
      var vorher = knopf.textContent;
      knopf.textContent = "Kopiert \u2713";
      setTimeout(function () { knopf.textContent = vorher; }, 2000);
    }
    function fallback() {
      feld.focus();
      feld.select();
      try { document.execCommand("copy"); bestaetigt(); } catch (e) { /* Auswahl bleibt stehen */ }
    }
    knopf.addEventListener("click", function () {
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(feld.value).then(bestaetigt, fallback);
      } else {
        fallback();
      }
    });
  }
  var knoepfe = document.querySelectorAll("[data-kopieren]");
  for (var i = 0; i < knoepfe.length; i++) verdrahte(knoepfe[i]);
})();
