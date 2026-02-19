"""
Web interface for Influencer-Product Matching

Modern, clean web UI for office use.
"""

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import os
import pandas as pd
import socket
from matcher import InfluencerMatcher
from database import Database
from ai_service import AIService, AINotConfiguredError
from notion_service import NotionService

# Absolute base path — works for local dev and WSGI servers (e.g. PythonAnywhere)
APP_ROOT = Path(__file__).parent.absolute()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # No caching for static files
app.config['UPLOAD_FOLDER'] = APP_ROOT / 'data' / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)

# Session security — use Fernet key as fallback secret
_fernet_key_path = APP_ROOT / 'data' / '.fernet_key'
if _fernet_key_path.exists():
    _fallback_secret = _fernet_key_path.read_text().strip()
else:
    _fallback_secret = os.urandom(32).hex()
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', _fallback_secret)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Global instances
matcher = None
db = Database()
ai = AIService(db)
notion = NotionService(db)


DEFAULT_PASSWORD = 'goodmoodfood2025'
DEFAULT_ADMIN_PASSWORD = 'gmf-admin-2026'


def _ensure_password():
    """Set default password on first run if none exists."""
    if not db.get_setting('app_password_hash'):
        pw_hash = generate_password_hash(DEFAULT_PASSWORD)
        db.set_setting('app_password_hash', pw_hash)
    if not db.get_setting('admin_password_hash'):
        pw_hash = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
        db.set_setting('admin_password_hash', pw_hash)


@app.before_request
def require_login():
    """Block unauthenticated access to all routes except login and static."""
    allowed = ('/login', '/logout', '/static/')
    if any(request.path.startswith(p) for p in allowed):
        return
    if not session.get('authenticated'):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Nicht angemeldet'}), 401
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page — team password or admin password."""
    if session.get('authenticated'):
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')

        # Check admin password first
        admin_hash = db.get_setting('admin_password_hash')
        if admin_hash and check_password_hash(admin_hash, password):
            session['authenticated'] = True
            session['is_admin'] = True
            return redirect(url_for('index'))

        # Then check team password
        pw_hash = db.get_setting('app_password_hash')
        if pw_hash and check_password_hash(pw_hash, password):
            session['authenticated'] = True
            session['is_admin'] = False
            return redirect(url_for('index'))

        error = 'Falsches Passwort'

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """Return authentication status and admin flag."""
    return jsonify({
        'authenticated': bool(session.get('authenticated')),
        'is_admin': bool(session.get('is_admin')),
    })


@app.route('/api/settings/password', methods=['POST'])
def change_password():
    """Change the shared app password (admin-only)."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Nur Admins koennen das Passwort aendern'}), 403

    data = request.get_json()
    old_pw = data.get('old_password', '')
    new_pw = data.get('new_password', '')

    if not new_pw or len(new_pw) < 4:
        return jsonify({'error': 'Neues Passwort muss mindestens 4 Zeichen haben'}), 400

    pw_hash = db.get_setting('app_password_hash')
    if not check_password_hash(pw_hash, old_pw):
        return jsonify({'error': 'Altes Passwort ist falsch'}), 400

    db.set_setting('app_password_hash', generate_password_hash(new_pw))
    return jsonify({'success': True})


def auto_load_test_data():
    """Auto-load test_dateien/ on startup if available"""
    global matcher
    test_dir = APP_ROOT / 'test_dateien'
    if test_dir.exists() and any(test_dir.glob('*.csv')):
        print("Auto-loading test data from test_dateien/...")
        matcher = InfluencerMatcher(test_dir)
        matcher.load_collaboration_files()
        print(f"Ready: {len(matcher.collaboration_data)} contacts, {len(matcher.all_products)} products\n")


@app.route('/')
def index():
    """Main page with upload and matching interface"""
    return render_template('index.html')


@app.route('/api/upload-data', methods=['POST'])
def upload_data():
    """Upload collaboration data files (CSV/Excel)"""
    global matcher
    
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    uploaded = []
    
    for file in files:
        if file.filename == '':
            continue
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = app.config['UPLOAD_FOLDER'] / filename
            file.save(filepath)
            uploaded.append(filename)
    
    # Initialize matcher with uploaded data
    matcher = InfluencerMatcher(app.config['UPLOAD_FOLDER'])
    matcher.load_collaboration_files()
    
    return jsonify({
        'success': True,
        'uploaded': uploaded,
        'contacts_loaded': len(matcher.collaboration_data),
        'products_found': len(matcher.all_products)
    })


@app.route('/api/verify-single', methods=['POST'])
def verify_single():
    """Verify a single influencer-product assignment"""
    global matcher
    
    if not matcher:
        return jsonify({'error': 'No data loaded. Upload files first.'}), 400
    
    data = request.get_json()
    name = data.get('name')
    product = data.get('product')
    
    if not name or not product:
        return jsonify({'error': 'Name and product required'}), 400
    
    result = matcher.verify_assignment(name, product)
    return jsonify(result)


@app.route('/api/verify-batch', methods=['POST'])
def verify_batch():
    """Verify multiple assignments from uploaded file or JSON"""
    global matcher
    
    if not matcher:
        return jsonify({'error': 'No data loaded. Upload collaboration data first.'}), 400
    
    # Check if file upload
    if 'file' in request.files:
        file = request.files['file']
        if file and allowed_file(file.filename):
            # Read file
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            # Expect columns: Name, Product (or similar)
            name_col = next((c for c in df.columns if 'name' in c.lower()), df.columns[0])
            product_col = next((c for c in df.columns if 'product' in c.lower()), None)
            
            if not product_col:
                return jsonify({'error': 'Could not find product column'}), 400
            
            assignments = dict(zip(df[name_col], df[product_col]))
    else:
        # JSON data
        data = request.get_json()
        assignments = data.get('assignments', {})
    
    if not assignments:
        return jsonify({'error': 'No assignments provided'}), 400
    
    # Run batch verification
    results_df = matcher.batch_verify(assignments)
    
    # Convert to JSON-friendly format
    results = results_df.to_dict('records')
    
    # Statistics
    stats = {
        'total': len(results),
        'verified': sum(1 for r in results if r['Verified']),
        'mismatches': sum(1 for r in results if r['Status'] == 'MISMATCH'),
        'no_data': sum(1 for r in results if r['Status'] == 'NO_DATA')
    }
    
    return jsonify({
        'results': results,
        'stats': stats
    })


@app.route('/api/search-influencer', methods=['POST'])
def search_influencer():
    """Search for an influencer and get their product history"""
    global matcher
    
    if not matcher:
        return jsonify({'error': 'No data loaded'}), 400
    
    data = request.get_json()
    name = data.get('name')
    
    if not name:
        return jsonify({'error': 'Name required'}), 400
    
    # Find match
    match = matcher.find_best_match(name)
    
    if not match:
        return jsonify({
            'found': False,
            'message': 'No match found in database'
        })
    
    matched_name, score = match
    products = matcher.get_products_for_influencer(name)
    
    return jsonify({
        'found': True,
        'matched_name': matched_name,
        'match_score': score,
        'products': products
    })


@app.route('/api/export-results', methods=['POST'])
def export_results():
    """Export verification results as Excel"""
    data = request.get_json()
    results = data.get('results', [])
    
    if not results:
        return jsonify({'error': 'No results to export'}), 400
    
    df = pd.DataFrame(results)
    
    # Save to file
    output_path = APP_ROOT / 'data' / 'exports' / 'verification_results.xlsx'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)
    
    return send_file(output_path, as_attachment=True)


@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    """Get all contact names from matcher data (for autocomplete)."""
    if not matcher:
        return jsonify([])
    return jsonify(sorted(matcher.collaboration_data.keys()))


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get current matcher statistics"""
    global matcher

    if not matcher:
        return jsonify({'loaded': False})

    return jsonify({
        'loaded': True,
        'total_contacts': len(matcher.collaboration_data),
        'total_products': len(matcher.all_products),
        'products': sorted(list(matcher.all_products))
    })


@app.route('/api/products/overview', methods=['GET'])
def get_products_overview():
    """Get all products with influencer counts (for Produkte tab)."""
    if not matcher:
        return jsonify([])

    product_map = {}
    for name, products in matcher.collaboration_data.items():
        for product in products:
            if product not in product_map:
                product_map[product] = []
            product_map[product].append(name)

    result = []
    for product in sorted(product_map.keys()):
        result.append({
            'name': product,
            'influencer_count': len(product_map[product]),
            'influencers': sorted(product_map[product])
        })
    return jsonify(result)


@app.route('/api/products/lookup', methods=['POST'])
def product_lookup():
    """Reverse lookup: find influencers for a product (fuzzy match)."""
    if not matcher:
        return jsonify({'error': 'Keine Daten geladen'}), 400

    from thefuzz import fuzz as _fuzz

    data = request.get_json()
    query = data.get('product', '').strip()
    if not query:
        return jsonify({'error': 'Produkt erforderlich'}), 400

    # Fuzzy match against all known products
    best_product = None
    best_score = 0
    for product in matcher.all_products:
        score = _fuzz.token_set_ratio(query.lower(), product.lower())
        if score > best_score:
            best_score = score
            best_product = product

    if best_score < 55:
        return jsonify({'found': False, 'message': f'Kein Produkt gefunden fuer "{query}"'})

    # Find all influencers with this product
    influencers = []
    for name, products in matcher.collaboration_data.items():
        if best_product in products:
            influencers.append(name)

    return jsonify({
        'found': True,
        'product': best_product,
        'match_score': best_score,
        'influencers': sorted(influencers),
        'influencer_count': len(influencers),
    })


def seed_profiles_from_matcher():
    """Create DB profiles from matcher data on startup."""
    if not matcher:
        return
    count = 0
    for name in matcher.collaboration_data:
        existing = db.get_profile(name)
        if not existing:
            db.upsert_profile(name, display_name=name)
            count += 1
    if count:
        print(f"Seeded {count} new influencer profiles into DB")


# --- Auto-Rating Computation ---

# Product category mapping for auto-tagging
PRODUCT_CATEGORIES = {
    'Kakao': ['Rohkakao Peru', 'Rohkakao Ecuador', 'Rohkakao Criollo', 'Kakao Nibs',
              'Feel Good Kakao', 'Rise Up & Shine', 'Calm Down & Relax',
              'The Wholy Bean', 'SinnPhonie', 'Queen Beans'],
    'Vitalpilze': ['Reishi', 'Lions Mane', 'Cordyceps', 'Chaga', 'Pure Power',
                   'Vitalpilz Extrakte', 'Vitalpilz Kakao'],
    'Superfoods': ['Coco Aminos', 'Ashwagandha', 'Matcha', 'Chlorella', 'Maca', 'Lucuma'],
    'Snacks': ['Cashew Cluster', 'Peru Butter Drops'],
}


def compute_auto_ratings(profile, product_count):
    """Compute data-driven star ratings (1-5) from available data."""
    # 1) Produkt-Erfahrung: based on product count
    if product_count >= 6:
        r_experience = 5
    elif product_count >= 4:
        r_experience = 4
    elif product_count >= 3:
        r_experience = 3
    elif product_count >= 2:
        r_experience = 2
    elif product_count >= 1:
        r_experience = 1
    else:
        r_experience = 0

    # 2) Reichweite: based on follower count
    followers = profile.get('notion_follower', 0) or 0
    if followers >= 100000:
        r_reach = 5
    elif followers >= 25000:
        r_reach = 4
    elif followers >= 5000:
        r_reach = 3
    elif followers >= 1000:
        r_reach = 2
    elif followers > 0:
        r_reach = 1
    else:
        r_reach = 0

    # 3) Kooperations-Status: based on kontakt + status fields
    kontakt = (profile.get('notion_kontakt', '') or '').lower()
    status = (profile.get('notion_status', '') or '').lower()

    r_status = 0
    # Map known status values to ratings
    status_map = {
        'abgeschlossen': 5, 'done': 5, 'versendet': 5,
        'zugesagt': 4, 'agreed': 4, 'kooperation': 4,
        'in verhandlung': 3, 'negotiation': 3, 'in bearbeitung': 3,
        'antwort': 2, 'antwort erhalten': 2, 'replied': 2,
        'angeschrieben': 1, 'kontaktiert': 1, 'gesendet': 1,
    }
    for key, val in status_map.items():
        if key in kontakt or key in status:
            r_status = max(r_status, val)

    return {
        'auto_rating_reliability': r_experience,
        'auto_rating_content_quality': r_reach,
        'auto_rating_communication': r_status,
    }


def _auto_tag_profile(name, notion_entry=None):
    """Generate tags for a profile from Notion rolle + product categories."""
    import json

    profile = db.get_profile(name)
    if not profile:
        return

    # Start with existing manual tags
    try:
        existing_tags = set(json.loads(profile.get('tags', '[]')))
    except (json.JSONDecodeError, TypeError):
        existing_tags = set()

    # Add tags from Notion rolle
    if notion_entry and notion_entry.get('rolle'):
        rolle = notion_entry['rolle'].strip()
        if rolle:
            # Split on common separators
            import re as _re
            parts = _re.split(r'[,;/&]+', rolle)
            for part in parts:
                tag = part.strip()
                if tag and len(tag) > 1:
                    existing_tags.add(tag)

    # Add tags from product categories
    if matcher:
        products = matcher.get_products_for_influencer(name)
        for cat_name, cat_products in PRODUCT_CATEGORIES.items():
            if any(p in cat_products for p in products):
                existing_tags.add(cat_name)

    db.upsert_profile(name, tags=json.dumps(sorted(existing_tags), ensure_ascii=False))


# --- OAuth Routes ---

@app.route('/oauth/connect')
def oauth_connect():
    """Redirect user to OpenRouter login page."""
    callback_url = request.url_root.rstrip('/') + url_for('oauth_callback')
    auth_url = ai.get_oauth_url(callback_url)
    return redirect(auth_url)


@app.route('/oauth/callback')
def oauth_callback():
    """Handle OpenRouter OAuth callback."""
    code = request.args.get('code')
    if not code:
        return redirect('/?settings=error&msg=Kein+Code+erhalten')

    result = ai.handle_oauth_callback(code)
    if result['success']:
        return redirect('/?settings=connected')
    else:
        error_msg = result.get('error', 'Unbekannter Fehler')
        return redirect(f'/?settings=error&msg={error_msg}')


# --- Settings Routes ---

@app.route('/api/settings/ai', methods=['GET'])
def get_ai_settings():
    """Get current AI connection status."""
    return jsonify(ai.get_status())


@app.route('/api/settings/ai', methods=['POST'])
def save_ai_settings():
    """Save manual API key (admin-only)."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Nur Admins koennen KI-Einstellungen aendern'}), 403
    data = request.get_json()
    provider = data.get('provider')
    api_key = data.get('api_key')

    if not provider or not api_key:
        return jsonify({'error': 'Provider und API-Key erforderlich'}), 400

    # Validate key first
    validation = ai.validate_api_key(provider, api_key)
    if not validation['valid']:
        return jsonify({'error': f'Key ungueltig: {validation["error"]}'}), 400

    model = data.get('model') or ''
    db.save_ai_provider(provider, api_key, model)
    return jsonify({'success': True, 'status': ai.get_status()})


@app.route('/api/settings/ai/disconnect', methods=['POST'])
def disconnect_ai():
    """Remove AI connection (admin-only)."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Nur Admins koennen KI-Einstellungen aendern'}), 403
    db.clear_ai_provider()
    return jsonify({'success': True})


# --- Notion Routes ---

@app.route('/api/settings/notion', methods=['GET'])
def get_notion_settings():
    """Get Notion connection status."""
    return jsonify(notion.get_status())


@app.route('/api/settings/notion', methods=['POST'])
def save_notion_settings():
    """Save and validate Notion integration token (admin-only)."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Nur Admins koennen Notion-Einstellungen aendern'}), 403
    data = request.get_json()
    token = data.get('token', '').strip()

    if not token:
        return jsonify({'error': 'Token erforderlich'}), 400

    result = notion.test_connection(token)
    if not result['valid']:
        return jsonify({'error': result['error']}), 400

    notion.save_token(token)
    return jsonify({'success': True, 'status': notion.get_status()})


@app.route('/api/settings/notion/disconnect', methods=['POST'])
def disconnect_notion():
    """Remove Notion connection (admin-only)."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Nur Admins koennen Notion-Einstellungen aendern'}), 403
    notion.clear_token()
    return jsonify({'success': True})


@app.route('/api/notion/sync', methods=['POST'])
def sync_notion():
    """Pull all entries from Notion TM-DB and merge with local profiles."""
    if not notion.is_connected():
        return jsonify({'error': 'Notion nicht verbunden'}), 400

    try:
        entries = notion.fetch_all_entries()
    except Exception as e:
        return jsonify({'error': f'Notion Fehler: {str(e)}'}), 500

    # Get existing local profile names for fuzzy matching
    local_profiles = db.get_all_profiles()
    local_names = [p['name'] for p in local_profiles]

    synced = 0
    created = 0

    from thefuzz import fuzz

    for entry in entries:
        notion_name = entry.get('name', '')
        if not notion_name:
            continue

        # Fuzzy-match against local profiles (prefer exact case-insensitive match)
        best_match = None
        best_score = 0
        for local_name in local_names:
            if local_name.lower() == notion_name.lower():
                best_match = local_name
                best_score = 100
                break
            score = fuzz.token_set_ratio(notion_name.lower(), local_name.lower())
            if score > best_score and score >= 80:
                best_score = score
                best_match = local_name

        if best_match:
            target_name = best_match
        else:
            # Create new profile from Notion data
            db.upsert_profile(notion_name, display_name=notion_name,
                              instagram_handle=entry.get('instagram', ''))
            target_name = notion_name
            local_names.append(notion_name)
            created += 1

        # Update Notion-specific fields
        db.update_notion_data(
            target_name,
            notion_page_id=entry['notion_page_id'],
            notion_status=entry.get('status', ''),
            notion_produkt=entry.get('produkt', ''),
            notion_follower=entry.get('follower', 0),
            notion_kontakt=entry.get('kontakt', ''),
            notion_rolle=entry.get('rolle', ''),
            email=entry.get('email', ''),
            icon_url=entry.get('icon_url', ''),
        )

        # Import Matcher-Notiz from Notion if local notes are empty
        notion_notiz = entry.get('matcher_notiz', '')
        if notion_notiz:
            local_profile = db.get_profile(target_name)
            if local_profile and not local_profile.get('notes'):
                db.upsert_profile(target_name, notes=notion_notiz)

        # Auto-generate tags from Notion rolle + product categories
        _auto_tag_profile(target_name, entry)
        synced += 1

    return jsonify({
        'success': True,
        'synced': synced,
        'created': created,
        'total_notion': len(entries),
    })


@app.route('/api/profiles/<path:name>/notion', methods=['GET'])
def get_profile_notion(name):
    """Fetch Notion page content for a profile (email draft, context)."""
    profile = db.get_profile(name)
    if not profile or not profile.get('notion_page_id'):
        return jsonify({'error': 'Kein Notion-Eintrag verknuepft'}), 404

    if not notion.is_connected():
        return jsonify({'error': 'Notion nicht verbunden'}), 400

    try:
        content = notion.fetch_page_content(profile['notion_page_id'])
        email_draft = notion.extract_email_draft(content)
        collab_history = notion.extract_collab_history(content)
        return jsonify({
            'email_draft': email_draft,
            'collab_history': collab_history,
            'full_content': content,
        })
    except Exception as e:
        return jsonify({'error': f'Notion Fehler: {str(e)}'}), 500


# --- Profile Routes ---

@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    """Get all influencer profiles with product counts and auto-ratings."""
    import json as _json
    profiles = db.get_all_profiles()

    for p in profiles:
        if matcher:
            products = matcher.get_products_for_influencer(p['name'])
            p['product_count'] = len(products)
        else:
            p['product_count'] = 0

        # Auto-ratings for sorting/display in list
        auto = compute_auto_ratings(p, p['product_count'])
        p.update(auto)

        # Parse tags
        try:
            p['tags'] = _json.loads(p.get('tags', '[]'))
        except (ValueError, TypeError):
            p['tags'] = []

    return jsonify(profiles)


@app.route('/api/profiles/<path:name>', methods=['GET'])
def get_profile(name):
    """Get single profile, auto-create from matcher data if needed."""
    import json as _json

    profile = db.get_profile(name)

    if not profile:
        profile = db.upsert_profile(name, display_name=name)

    # Add products from matcher
    products = []
    if matcher:
        products = matcher.get_products_for_influencer(name)

    profile['products'] = products
    profile['product_count'] = len(products)

    # Compute auto-ratings from data
    auto_ratings = compute_auto_ratings(profile, len(products))
    profile.update(auto_ratings)

    # Parse tags from JSON string to list
    try:
        profile['tags'] = _json.loads(profile.get('tags', '[]'))
    except (ValueError, TypeError):
        profile['tags'] = []

    # Auto-load Notion page content if available (collab history + email draft)
    if profile.get('notion_page_id') and notion.is_connected():
        try:
            content = notion.fetch_page_content(profile['notion_page_id'])
            profile['email_draft'] = notion.extract_email_draft(content)
            profile['collab_history'] = notion.extract_collab_history(content)
        except Exception:
            profile['email_draft'] = None
            profile['collab_history'] = None

    # Let frontend know if AI is available
    profile['ai_configured'] = ai.get_status().get('configured', False)

    return jsonify(profile)


@app.route('/api/profiles/<path:name>/photo', methods=['POST'])
def upload_profile_photo(name):
    """Upload a profile photo (max 2MB, jpg/png/webp)."""
    if 'photo' not in request.files:
        return jsonify({'error': 'Kein Foto hochgeladen'}), 400

    photo = request.files['photo']
    if photo.filename == '':
        return jsonify({'error': 'Keine Datei ausgewaehlt'}), 400

    ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else ''
    if ext not in ('jpg', 'jpeg', 'png', 'webp'):
        return jsonify({'error': 'Nur JPG, PNG oder WebP erlaubt'}), 400

    # Check size (2MB)
    photo.seek(0, 2)
    size = photo.tell()
    photo.seek(0)
    if size > 2 * 1024 * 1024:
        return jsonify({'error': 'Datei zu gross (max 2MB)'}), 400

    photos_dir = APP_ROOT / 'data' / 'photos'
    photos_dir.mkdir(parents=True, exist_ok=True)

    filename = secure_filename(name) + '.' + ext
    filepath = photos_dir / filename
    photo.save(filepath)

    db.upsert_profile(name, profile_photo=filename)
    return jsonify({'success': True, 'filename': filename})


@app.route('/api/profiles/<path:name>/photo', methods=['GET'])
def get_profile_photo(name):
    """Serve a profile photo."""
    profile = db.get_profile(name)
    if not profile or not profile.get('profile_photo'):
        return jsonify({'error': 'Kein Foto vorhanden'}), 404

    filepath = APP_ROOT / 'data' / 'photos' / profile['profile_photo']
    if not filepath.exists():
        return jsonify({'error': 'Foto-Datei nicht gefunden'}), 404

    return send_file(filepath)


@app.route('/api/profiles/<path:name>', methods=['PUT'])
def update_profile(name):
    """Update profile ratings/notes. Syncs notes to Notion as comment."""
    data = request.get_json()

    allowed_fields = {
        'rating_reliability', 'rating_content_quality',
        'rating_communication', 'notes', 'instagram_handle',
        'display_name', 'email',
    }
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if not updates:
        return jsonify({'error': 'Keine gueltigen Felder'}), 400

    profile = db.upsert_profile(name, **updates)

    # Sync notes to Notion as "Matcher-Notiz" property
    notion_synced = False
    notion_error = ''
    if 'notes' in updates:
        has_notion = notion.is_connected()
        has_page_id = bool(profile.get('notion_page_id'))
        print(f'[Notion] Saving notes for "{name}": connected={has_notion}, page_id={profile.get("notion_page_id", "NONE")}')
        if has_notion and has_page_id:
            try:
                notion.update_property(
                    profile['notion_page_id'],
                    'Matcher-Notiz',
                    updates['notes']
                )
                notion_synced = True
                print(f'[Notion] Notes synced OK for "{name}"')
            except Exception as e:
                notion_error = str(e)
                print(f'[Notion] Notiz-Sync FEHLER: {e}')

    result = dict(profile)
    result['notion_synced'] = notion_synced
    if notion_error:
        result['notion_error'] = notion_error
    return jsonify(result)


# --- Tags Routes ---

@app.route('/api/tags', methods=['GET'])
def get_tags():
    """Get all unique tags used across profiles."""
    return jsonify(db.get_all_tags())


@app.route('/api/profiles/<path:name>/tags', methods=['POST'])
def update_profile_tags(name):
    """Add or remove a tag from a profile."""
    import json as _json

    data = request.get_json()
    action = data.get('action', 'add')  # 'add' or 'remove'
    tag = data.get('tag', '').strip()

    if not tag:
        return jsonify({'error': 'Tag erforderlich'}), 400

    profile = db.get_profile(name)
    if not profile:
        return jsonify({'error': 'Profil nicht gefunden'}), 404

    try:
        tags = set(_json.loads(profile.get('tags', '[]')))
    except (ValueError, TypeError):
        tags = set()

    if action == 'add':
        tags.add(tag)
    elif action == 'remove':
        tags.discard(tag)

    db.upsert_profile(name, tags=_json.dumps(sorted(tags), ensure_ascii=False))
    return jsonify({'success': True, 'tags': sorted(tags)})


# --- AI Routes ---

@app.route('/api/ai/explain-match', methods=['POST'])
def explain_match():
    """AI explains why an influencer fits a product."""
    data = request.get_json()
    name = data.get('name')
    product = data.get('product')

    if not name or not product:
        return jsonify({'error': 'Name und Produkt erforderlich'}), 400

    # Get products from matcher
    products = []
    match_score = 0
    if matcher:
        products = matcher.get_products_for_influencer(name)
        result = matcher.verify_assignment(name, product)
        match_score = result.get('match_score', 0)

    try:
        explanation = ai.explain_match(name, products, product, match_score)
        return jsonify({'explanation': explanation})
    except AINotConfiguredError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'AI Fehler: {str(e)}'}), 500


@app.route('/api/profiles/<path:name>/ai-analysis', methods=['POST'])
def profile_ai_analysis(name):
    """AI generates a comprehensive profile analysis."""
    profile = db.get_profile(name)
    if not profile:
        return jsonify({'error': 'Profil nicht gefunden'}), 404

    # Get products from matcher
    products = []
    if matcher:
        products = matcher.get_products_for_influencer(name)

    try:
        analysis = ai.analyze_profile(dict(profile), products)
        return jsonify({'analysis': analysis})
    except AINotConfiguredError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'AI Fehler: {str(e)}'}), 500


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx', 'xls'}


def find_available_port():
    """Find available port: prefer 5001 (macOS AirPlay blocks 5000), fallback 5000"""
    for port in [5001, 5000]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('localhost', port))
            s.close()
            return port
        except OSError:
            continue
    return 5001  # Default


# --- Startup (runs on import by WSGI and on direct execution) ---
_ensure_password()
auto_load_test_data()
seed_profiles_from_matcher()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', find_available_port()))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'

    print("\n" + "="*60)
    print("Influencer Matcher starting...")
    print("="*60)
    print(f"\nOpen in browser: http://localhost:{port}")
    print("\nPress CTRL+C to stop the server\n")

    app.run(host='0.0.0.0', port=port, debug=debug)
