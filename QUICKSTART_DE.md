# Quick Start Guide - Influencer Matcher

## Was ist das?

Ein Tool, das Influencer automatisch mit den passenden GMF-Produkten matcht, basierend auf vergangenen Kollaborationen.

## Setup (5 Minuten)

### Windows:
1. Doppelklick auf `setup.bat`
2. Warten bis Installation fertig ist
3. Doppelklick auf `run.bat`
4. Browser öffnet sich automatisch

### Mac/Linux:
```bash
./setup.sh
./run.sh
```

Browser öffnen: http://localhost:5000

## Wie benutzen?

### 1. Daten hochladen
- Drag & Drop deine CSV/Excel Dateien ins Upload-Feld
- z.B. alle KOLLABORATIONEN_-_*.csv Dateien
- System lädt automatisch alle Kontakte und Produkte

### 2. Einzelne Person checken
- Name eingeben (z.B. "Laura Malina Seiler")
- System findet Person auch bei Tippfehlern
- Zeigt alle Produkte mit denen sie gearbeitet hat

### 3. Ganze Liste verifizieren
- Excel-Datei hochladen mit Spalten: Name | Produkt
- Klick auf "Verify All"
- Bekommst Report:
  - ✓ VERIFIED: Product passt zur Historie
  - ⚠ MISMATCH: Anderes Produkt wäre besser
  - ❓ NO DATA: Keine Kollaboration gefunden

### 4. Ergebnisse exportieren
- Klick auf "Export Results"
- Excel-Datei wird runtergeladen
- Kannst du mit Alice/Fabian teilen

## Beispiel Workflow

```
1. Upload: KOLLABORATIONEN_-_TESTIMONIALS.csv
           KOLLABORATIONEN_-_BARTER_DEALS.csv
           etc.

2. Single Check:
   Name: "Serap"
   → Findet: "@serap.cacao, 3K followers"
   → Produkte: Rohkakao Peru, Kakao Ecuador

3. Batch Verify:
   Hochladen: testimonial_assignments.xlsx
   → 114 contacts processed
   → 89 verified ✓
   → 15 mismatches ⚠
   → 10 no data ❓
```

## Tipps

- **Fuzzy Matching**: System findet auch "Lara" wenn du "Laura" eingibst
- **@ Handles**: "@serap" und "Serap" werden gleich behandelt
- **Follower Counts**: "Serap 3K" wird automatisch bereinigt
- **Multiple Produkte**: Person kann mit mehreren Produkten gearbeitet haben

## Troubleshooting

**"Port 5000 already in use":**
→ Anderes Programm nutzt Port 5000
→ Lösung: In `app.py` Zeile 166 ändern: `port=5001`

**"No module named flask":**
→ Virtual environment nicht aktiviert
→ Lösung: `setup.bat` nochmal ausführen

**"Cannot find file":**
→ CSV nicht UTF-8 encoded
→ Lösung: Excel → "Save As" → UTF-8 CSV

## Was macht das Tool technisch?

1. **Name Normalisierung**: Lowercase, @ entfernen, Leerzeichen trimmen
2. **Fuzzy Matching**: Levenshtein distance für Namenssuche
3. **Produkt Extraktion**: Keyword matching (Peru, Ecuador, Coco Aminos, etc.)
4. **Scoring**: 0-100% Match-Qualität

## Python vs. Web App - Warum Web?

**Vorteil Web:**
- ✓ Läuft lokal auf deinem Laptop (keine Cloud nötig)
- ✓ Cooles Interface für Office
- ✓ Kann später für Team freigegeben werden
- ✓ Drag & Drop statt Python Code
- ✓ Export-Buttons statt File-Pfade

**Wenn Team-Access gewünscht:**
- App auf Server deployen (Heroku, AWS)
- Oder: Netzwerk-Modus aktivieren → Kollegen können zugreifen

## Nächste Schritte

Wenn du willst, können wir noch hinzufügen:
- [ ] Email-Kampagnen direkt aus Tool versenden
- [ ] Produkt-Empfehlungs-Engine (ML-basiert)
- [ ] Historische Trend-Analyse
- [ ] Datenbank für Persistenz
- [ ] User Login für Team

---

**Fragen?** Schreib mir einfach im Chat! 🚀
