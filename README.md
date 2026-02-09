# Influencer Product Matcher

Professional web-based tool for matching influencers to products based on historical collaboration data.

## Features

- 📂 **Data Upload**: Drag & drop CSV/Excel files with collaboration history
- 🔍 **Smart Search**: Fuzzy name matching finds influencers even with typos
- ✓ **Verification**: Check if product assignments match historical data
- 📊 **Batch Processing**: Verify entire lists at once
- 📥 **Export**: Download results as Excel for sharing with team
- 🌐 **Web Interface**: Clean, modern UI accessible from any browser
- 💻 **Local Deployment**: Runs entirely on your laptop, no cloud required

## Quick Start

### 1. Install Python (if not already installed)

Download from: https://www.python.org/downloads/

During installation, make sure to check "Add Python to PATH"

### 2. Setup Virtual Environment

```bash
# Navigate to project folder
cd influencer-matcher

# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the App

```bash
python app.py
```

Open your browser and go to: **http://localhost:5000**

## Usage Guide

### Step 1: Load Data

1. Upload CSV/Excel files containing past collaborations
2. Files should have at least two columns: Name and Product interactions
3. Multiple files can be uploaded (e.g., different collaboration types)

**Supported Files:**
- KOLLABORATIONEN_-_*.csv
- Any Excel files (.xlsx, .xls)

### Step 2: Search Influencers

- Enter name in search box
- System finds best match even with spelling variations
- Shows all products they've interacted with

### Step 3: Verify Assignments

**Single Check:**
- Enter influencer name and assigned product
- Get instant verification with match score

**Batch Verify:**
- Upload Excel/CSV with columns: Name, Product
- Get full verification report
- Export results for team review

## Data Format

### Input Files (Collaboration Data)

```
Name                | Product        | Details
-------------------|----------------|--------
Laura @laura       | Rohkakao Peru  | Posted recipe
Serap             | Kakao Ecuador  | Instagram story
```

### Verification File (Batch Check)

```
Name                | Product
-------------------|----------------
Laura Malina Seiler | Rohkakao Peru
Caroline Brunner    | Lions Mane
```

## Architecture

```
influencer-matcher/
├── app.py              # Flask web server
├── matcher.py          # Core matching algorithm
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html     # Web interface
├── static/
│   ├── css/
│   │   └── style.css  # Styling
│   └── js/
│       └── app.js     # Frontend logic
└── data/
    ├── uploads/       # Uploaded collaboration files
    └── exports/       # Generated reports
```

## Algorithm Details

The matcher uses:

1. **Name Normalization**: Converts names to lowercase, removes @ symbols and follower counts
2. **Fuzzy Matching**: Uses Levenshtein distance via `thefuzz` library
3. **Product Extraction**: Keyword matching for GMF products (Peru, Ecuador, Coco Aminos, etc.)
4. **Verification Scoring**: Returns VERIFIED, MISMATCH, or NO_DATA with confidence scores

## Technical Stack

- **Backend**: Flask (Python 3.x)
- **Data Processing**: pandas, openpyxl
- **Matching**: thefuzz (fuzzy string matching)
- **Frontend**: Vanilla JavaScript, modern CSS
- **Deployment**: Local web server (no external dependencies)

## Deployment Options

### Local (Current Setup)
Run on your laptop, access via browser. Good for:
- Testing and development
- Single-user use
- Data privacy (everything stays local)

### Network Deployment (Future)
To make accessible to team on local network:
```python
app.run(host='0.0.0.0', port=5000)
```
Then colleagues can access via: `http://your-ip:5000`

### Cloud Deployment (Advanced)
Deploy to Heroku, AWS, or similar for remote access.
Requires:
- Cloud hosting account
- Environment configuration
- Database for persistence (optional)

## Troubleshooting

**Port 5000 already in use:**
```python
app.run(port=5001)  # Change port in app.py
```

**Import errors:**
```bash
pip install --upgrade -r requirements.txt
```

**Files not loading:**
- Check file encoding (should be UTF-8)
- Verify column headers exist
- Ensure CSV uses comma separator

## Future Enhancements

- [ ] Email campaign integration (SendGrid API)
- [ ] Product recommendation engine
- [ ] Historical trend analysis
- [ ] Multi-language support
- [ ] Database persistence (SQLite/PostgreSQL)
- [ ] User authentication for team use

## Support

For issues or questions, contact Lisa @ goodmoodfood

---

Built with ❤️ for GMF testimonial campaigns
