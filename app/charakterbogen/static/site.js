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

// MCP-Link kopieren: Clipboard-API (https) mit Fallback auf Auswahl+execCommand (http/alt).
(function () {
  var knopf = document.getElementById("kopieren");
  var feld = document.getElementById("mcp-url");
  if (!knopf || !feld) return;

  function bestaetigt() {
    knopf.textContent = "Kopiert ✓";
    setTimeout(function () { knopf.textContent = "Kopieren"; }, 2000);
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
})();
