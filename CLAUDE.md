# Influencer Product Matcher

## Was ist das?

Lokales Web-Tool fuer die goodmoodfood (GMF) Testimonial-Kampagne. Matcht 100+ Influencer automatisch mit dem richtigen "Hero-Produkt" basierend auf historischen Kollaborationsdaten.

## Tech-Stack

- **Backend**: Python 3.8+, Flask, pandas
- **Matching**: thefuzz (Levenshtein/Fuzzy-Matching), rapidfuzz (Performance-Backend)
- **Frontend**: Vanilla JavaScript, CSS (goodmoodfood-Branding)
- **Daten**: CSV/Excel-Import, Excel-Export

## Setup & Start

```bash
python -m venv venv
source venv/bin/activate  # Mac/Linux
# oder: venv\Scripts\activate  # Windows
pip install -r requirements.txt
python app.py
```

Browser: http://localhost:5001 (oder 5000 falls 5001 belegt)

## Projektstruktur

```
influencer-matcher/
├── app.py                 # Flask Server + API Endpoints
├── matcher.py             # Core Matching-Algorithmus
├── matcher_backup.py      # Backup vor Rewrite
├── requirements.txt       # Python Dependencies
├── CLAUDE.md              # Diese Datei
├── templates/
│   └── index.html         # Web UI
├── static/
│   ├── css/style.css      # goodmoodfood-Branding (CSS Variablen)
│   └── js/app.js          # Frontend-Logik
├── test_dateien/          # Echte Kollaborations-CSVs (11 Dateien)
│   ├── KOLLABORATIONEN - TESTIMONIALS.csv
│   ├── KOLLABORATIONEN - BARTER DEALS.csv
│   ├── KOLLABORATIONEN - Sponsored.csv
│   └── ... (8 weitere)
└── data/
    ├── uploads/           # Manuell hochgeladene Dateien
    └── exports/           # Generierte Excel-Reports
```

## Konventionen

- **UI-Sprache**: Deutsch (Subtitles, Labels)
- **Branding**: goodmoodfood Farben via CSS Variablen in style.css
  - Primary: `#693080` (Lila)
  - Secondary: `#a56e43` (Braun)
  - Accent: `#f29184` (Coral), `#efc15f` (Gold)
- **Font**: Montserrat (Google Fonts)

## Datenquellen (test_dateien/)

Die 11 CSV-Dateien haben unterschiedliche Spaltenstrukturen:
- **TESTIMONIALS.csv**: Mehrzeilige Zellen (Name + IG + Follower in einer Zelle)
- **BARTER DEALS.csv**: Name in Spalte 2 (Spalte 1 ist leer)
- **Sponsored.csv**: Separate Spalten fuer Name, IG, Follower
- Weitere: Food, Health, Yoga/Spiritual, Other, Gewinnspiel, Festivals, Spende, Archiv

Auto-Load: test_dateien/ wird beim App-Start automatisch geladen.

## Matching-Algorithmus

1. CSV laden -> Spalten intelligent erkennen
2. Namen normalisieren (lowercase, @-Zeichen entfernen, Follower-Counts entfernen)
3. Fuzzy Match mit thefuzz (token_set_ratio, min. 70% Score)
4. Produkt-Keywords in Zeilen-Text finden
5. Verification: Vergleich zugeordnetes Produkt vs. historische Daten

## Produkt-Keywords (erweiterbar in matcher.py)

Aktuell erkannte Produkte - in `matcher.py` unter `product_patterns` Dict erweiterbar:
- Kakao: Peru, Ecuador, Criollo, Nibs, Feel Good, Rise Up & Shine, Calm Down & Relax
- Pilze: Reishi, Lions Mane, Cordyceps, Chaga
- Superfoods: Coco Aminos, Ashwagandha, Matcha, Chlorella, Maca, Lucuma
- Weitere: Pure Power, Queen Beans, SinnPhonie, Cashew Cluster, etc.

## Verification-Status

- **VERIFIED**: Produkt in Historie gefunden
- **MISMATCH**: Person gefunden, aber anderes Produkt in Historie
- **NO_DATA**: Person nicht in Daten
- **NO_PRODUCTS**: Person gefunden, aber kein Produkt erkennbar
