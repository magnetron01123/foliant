"""Sicherer Buch-Download + ZIP-Verarbeitung (Vorschlag §10) und readonly-Lesen der
verschluesselten Buch-DB (SQLCipher v3, Parameter wie tests/test_ddb_sqlcipher_spike.py).

Haertung: gestreamter Download nach *.part mit Groessenlimit und atomarem Rename;
ZIP-Signaturpruefung; Ablehnung von Zip-Slip (absolute Pfade, '..'), Symlinks und
Zip-Bombs (Entpack-Limit); es wird NUR die eine erwartete .db3 extrahiert. Aufraeumen
von ZIP/DB3 uebernimmt der Aufrufer (cli) auf Erfolgs- UND Fehlerpfaden."""
from __future__ import annotations

import zipfile
from pathlib import Path

_ZIP_MAGIC = b"PK\x03\x04"
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024      # 512 MB - Buecher liegen weit darunter
MAX_ENTPACKT_BYTES = 1024 * 1024 * 1024     # Zip-Bomb-Deckel


class ArchivFehler(RuntimeError):
    """Download-/Archivfehler - Meldungen sind secret-frei (keine signierten URLs)."""


def lade_archiv(transport, signierte_url: str, ziel: Path) -> Path:
    """Streamt das Bucharchiv nach <ziel>.part und benennt erst nach Pruefung atomar um.
    Die signierte URL wird nie geloggt; Fehlermeldungen bleiben generisch."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    part = ziel.with_suffix(ziel.suffix + ".part")
    gesamt = 0
    try:
        with transport.stream("GET", signierte_url) as antwort:
            if antwort.status_code != 200:
                raise ArchivFehler(f"Buch-Download fehlgeschlagen "
                                   f"(HTTP {antwort.status_code}).")
            with open(part, "wb") as f:
                for block in antwort.iter_bytes():
                    gesamt += len(block)
                    if gesamt > MAX_DOWNLOAD_BYTES:
                        raise ArchivFehler("Download ueberschreitet das Groessenlimit - "
                                           "Abbruch (unplausibel grosses Archiv).")
                    f.write(block)
        with open(part, "rb") as f:
            if f.read(4) != _ZIP_MAGIC:
                raise ArchivFehler("Download ist kein ZIP-Archiv (Signatur fehlt).")
        if gesamt == 0:
            raise ArchivFehler("Download ist leer.")
        part.replace(ziel)
        return ziel
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def extrahiere_buch_db(archiv: Path, arbeitsverzeichnis: Path) -> Path:
    """Extrahiert GENAU EINE .db3 aus dem Archiv - alles andere wird nicht angefasst.
    Zip-Slip/Symlinks/Bomben werden abgelehnt; bei fehlender/mehrdeutiger DB Abbruch."""
    arbeitsverzeichnis.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archiv) as z:
        db3 = []
        entpackt = 0
        for info in z.infolist():
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts:
                raise ArchivFehler(f"ZIP-Slip-Verdacht im Archiv ({name!r}) - Abbruch.")
            # Symlink-Eintraege (Unix-Mode im external_attr) niemals entpacken.
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ArchivFehler(f"Symlink im Archiv ({name!r}) - Abbruch.")
            entpackt += info.file_size
            if entpackt > MAX_ENTPACKT_BYTES:
                raise ArchivFehler("Archiv ueberschreitet das Entpack-Limit (Zip-Bomb?).")
            if name.lower().endswith(".db3"):
                db3.append(info)
        if len(db3) != 1:
            raise ArchivFehler(f"Erwartet genau EINE .db3 im Archiv, gefunden: "
                               f"{len(db3)} - Abbruch statt raten.")
        ziel = arbeitsverzeichnis / Path(db3[0].filename).name
        with z.open(db3[0]) as quelle, open(ziel, "wb") as f:
            rest = MAX_ENTPACKT_BYTES
            for block in iter(lambda: quelle.read(1 << 16), b""):
                rest -= len(block)
                if rest < 0:
                    ziel.unlink(missing_ok=True)
                    raise ArchivFehler("DB3 groesser als deklariert (Zip-Bomb?).")
                f.write(block)
        return ziel


def _oeffne_readonly(db3_pfad: Path, schluessel: str):
    """READONLY-Verbindung mit expliziten SQLCipher-v3-Parametern; erste Leseabfrage
    beweist die Entschluesselung. Aufrufer schliesst die Verbindung."""
    import apsw  # nur der Exporter braucht SQLite3MC (nie Runtime-Abhaengigkeit)

    con = apsw.Connection(str(db3_pfad), flags=apsw.SQLITE_OPEN_READONLY)
    con.pragma("cipher", "sqlcipher")
    con.pragma("legacy", 3)
    con.pragma("key", schluessel)
    try:
        con.execute("SELECT count(*) FROM sqlite_master").fetchone()   # Entschluesselung
    except Exception:
        con.close()
        raise ArchivFehler("Buch-DB nicht lesbar - falscher Schluessel oder Format.") \
            from None
    return con


def lies_content(db3_pfad: Path, schluessel: str) -> list[dict]:
    """Content-Zeilen (gerenderter Buchtext) READONLY lesen. Leere/fehlende Content-
    Tabelle -> leere Liste (dann greifen die Detailtabellen, lies_detailtabellen)."""
    con = _oeffne_readonly(db3_pfad, schluessel)
    try:
        try:
            zeilen = con.execute(
                "SELECT ID AS id, CobaltID AS cobalt_id, ParentID AS parent_id, "
                "Slug AS slug, Title AS title, RenderedHTML AS html "
                "FROM Content").fetchall()
        except Exception:
            return []                                    # keine Content-Tabelle
        spalten = ["id", "cobalt_id", "parent_id", "slug", "title", "html"]
        return [dict(zip(spalten, z)) for z in zeilen]
    finally:
        con.close()


def lies_edition(db3_pfad: Path, schluessel: str, buch_id: int) -> str | None:
    """AUTORITATIVE Regelversion aus der Buch-DB selbst (nicht raten, V1/Q3):
    RPGSource[buch_id].RPGSourceCategoryID -> RPGSourceCategory.Name. Der Name traegt die
    Edition explizit ('2014 ...'/'5e ...' -> 2014; '5.5e ...'/'2024 ...' -> 2024). Fehlt
    das, entscheidet das ReleaseDate: Jahr < 2024 -> definitiv 2014 (die 2024-Regeln gab
    es davor nicht). Sonst None (mehrdeutig -> Buch wird NICHT mit geratener Edition
    importiert). Rueckgabe: '2024' | '2014' | None."""
    con = _oeffne_readonly(db3_pfad, schluessel)
    try:
        vorhanden = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "RPGSource" not in vorhanden:
            return None
        zeile = con.execute(
            "SELECT RPGSourceCategoryID, ReleaseDate FROM RPGSource WHERE ID=?",
            (buch_id,)).fetchone()
        if not zeile:
            return None
        kat_id, release = zeile
        kat_name = ""
        if kat_id is not None and "RPGSourceCategory" in vorhanden:
            r = con.execute("SELECT Name FROM RPGSourceCategory WHERE ID=?",
                            (kat_id,)).fetchone()
            kat_name = (r[0] if r else "") or ""
        e = _edition_aus_text(kat_name)
        if e:
            return e
        # ReleaseDate: 'M/D/YYYY ...' -> Jahr. Vor 2024 = sicher 2014.
        import re as _re
        m = _re.search(r"\b(19|20)\d{2}\b", str(release or ""))
        if m and int(m.group(0)) < 2024:
            return "2014"
        return None
    finally:
        con.close()


def _edition_aus_text(text: str) -> str | None:
    t = (text or "").lower()
    if "5.5e" in t or "2024" in t:
        return "2024"
    if "2014" in t or t.startswith("5e ") or " 5e " in t:
        return "2014"
    return None


def inspiziere_tabellen(db3_pfad: Path, schluessel: str) -> list[dict]:
    """Diagnose (secret-frei): Tabellenname, Zeilenzahl, Spalten - fuer die Analyse von
    Buechern OHNE Content-Text. Gibt KEINE Zellwerte aus."""
    con = _oeffne_readonly(db3_pfad, schluessel)
    try:
        namen = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        info = []
        for name in namen:
            try:
                n = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                spalten = [r[1] for r in con.execute(f'PRAGMA table_info("{name}")')]
            except Exception:
                n, spalten = -1, []
            info.append({"tabelle": name, "zeilen": n, "spalten": spalten})
        return info
    finally:
        con.close()


def inspiziere_entitaeten(db3_pfad: Path, schluessel: str) -> dict:
    """Diagnose fuer den HTMLDescription/ContentDetail-Aufbau: EntityType-Namen je ID,
    und welche EntityTypeIDs wie viel Text tragen. Secret-frei (nur IDs/Namen/Counts)."""
    con = _oeffne_readonly(db3_pfad, schluessel)
    try:
        vorhanden = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        typen = {}
        if "EntityType" in vorhanden:
            typen = {r[0]: r[1] for r in con.execute("SELECT ID, Name FROM EntityType")}
        verteilung = {}
        for tab in ("HTMLDescription", "ContentDetail"):
            if tab in vorhanden:
                spalten = {r[1] for r in con.execute(f'PRAGMA table_info("{tab}")')}
                if "EntityTypeID" in spalten:
                    verteilung[tab] = [
                        {"typ_id": r[0], "typ": typen.get(r[0], "?"), "zeilen": r[1]}
                        for r in con.execute(
                            f'SELECT EntityTypeID, count(*) FROM "{tab}" '
                            f'GROUP BY EntityTypeID ORDER BY count(*) DESC')]
        return {"typen": typen, "text_verteilung": verteilung}
    finally:
        con.close()


# DDB-Entitaetstabelle (EntityType.Name) -> Foliant-Kategorie. Fuer Buecher ohne
# Content-Text; der eigentliche Text kommt aus HTMLDescription/ContentDetail (join).
_ENTITAET_KATEGORIE = {
    "RPGSpell": "zauber",
    "RPGMonster": "monster",
    "RPGMagicItem": "gegenstand", "RPGItem": "gegenstand", "RPGGear": "gegenstand",
    "RPGWeapon": "gegenstand", "RPGArmor": "gegenstand",
    "RPGFeat": "talent",
    "RPGRace": "spezies", "RPGSubRace": "spezies",
    "RPGBackground": "hintergrund",
    "RPGClass": "klasse", "RPGSubclass": "klasse", "RPGClassFeature": "klasse",
}


def _erste(spalten, kandidaten) -> str | None:
    for k in kandidaten:
        if k in spalten:
            return k
    return None


def lies_strukturierte_eintraege(db3_pfad: Path, schluessel: str) -> list[dict]:
    """Fuer Buecher OHNE Content-Text (z. B. aeltere 2014-Ergaenzungen): baut je Entitaet
    (Zauber/Monster/Talent/Spezies/...) EINEN Eintrag aus Name + zugehoerigem Text.
    Der Text liegt in HTMLDescription (primaer) bzw. ContentDetail (Fallback), verknuepft
    ueber EntityTypeID (aus EntityType) + EntityID. Rueckgabe: content-zeilen-formige
    dicts MIT vorbelegter 'category' - readonly, keine Zellwert-Ausgabe."""
    con = _oeffne_readonly(db3_pfad, schluessel)
    try:
        vorhanden = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "EntityType" not in vorhanden or not (
                {"HTMLDescription", "ContentDetail"} & vorhanden):
            return []
        typ_id = {name: tid for tid, name in con.execute("SELECT ID, Name FROM EntityType")}
        hat_html = "HTMLDescription" in vorhanden
        hat_detail = "ContentDetail" in vorhanden

        eintraege: list[dict] = []
        for tabelle, kategorie in _ENTITAET_KATEGORIE.items():
            if tabelle not in vorhanden or tabelle not in typ_id:
                continue
            spalten = {r[1] for r in con.execute(f'PRAGMA table_info("{tabelle}")')}
            name_sp = _erste(spalten, ("Name", "Title"))
            if "ID" not in spalten or not name_sp:
                continue
            tid = typ_id[tabelle]
            for eid, name in con.execute(f'SELECT ID, "{name_sp}" FROM "{tabelle}"'):
                name = (name or "").strip()
                if not name:
                    continue
                teile: list[str] = []
                if hat_html:
                    teile += [str(r[0]) for r in con.execute(
                        "SELECT Text FROM HTMLDescription WHERE EntityTypeID=? AND "
                        "EntityID=? ORDER BY DisplayOrder", (tid, eid)) if r[0]]
                if not teile and hat_detail:
                    teile += [str(r[0]) for r in con.execute(
                        "SELECT Value FROM ContentDetail WHERE EntityTypeID=? AND "
                        "EntityID=? ORDER BY DisplayOrder", (tid, eid)) if r[0]]
                body = "\n\n".join(t for t in teile if t.strip())
                if body.strip():
                    eintraege.append({
                        "id": f"{tabelle}:{eid}", "cobalt_id": None, "parent_id": None,
                        "slug": None, "title": name, "category": kategorie, "html": body})
        return eintraege
    finally:
        con.close()
