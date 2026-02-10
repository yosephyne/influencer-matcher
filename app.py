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


def _ensure_password():
    """Set default password on first run if none exists."""
    if not db.get_setting('app_password_hash'):
        pw_hash = generate_password_hash(DEFAULT_PASSWORD)
        db.set_setting('app_password_hash', pw_hash)


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
    """Login page with shared password."""
    if session.get('authenticated'):
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        pw_hash = db.get_setting('app_password_hash')
        if pw_hash and check_password_hash(pw_hash, password):
            session['authenticated'] = True
            return redirect(url_for('index'))
        error = 'Falsches Passwort'

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/api/settings/password', methods=['POST'])
def change_password():
    """Change the shared app password."""
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


def seed_profiles_from_matcher():
    """Create DB profiles from matcher data on startup."""
    if not matcher:
        return
    count = 0
    for name in matcher.collaboration_data:
        existing = db.get_profile(name)
        if not existing:
            products = matcher.get_products_for_influencer(name)
            db.upsert_profile(name, display_name=name)
            count += 1
    if count:
        print(f"Seeded {count} new influencer profiles into DB")


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
    """Save manual API key (fallback method)."""
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
    """Remove AI connection."""
    db.clear_ai_provider()
    return jsonify({'success': True})


# --- Notion Routes ---

@app.route('/api/settings/notion', methods=['GET'])
def get_notion_settings():
    """Get Notion connection status."""
    return jsonify(notion.get_status())


@app.route('/api/settings/notion', methods=['POST'])
def save_notion_settings():
    """Save and validate Notion integration token."""
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
    """Remove Notion connection."""
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

        # Fuzzy-match against local profiles
        best_match = None
        best_score = 0
        for local_name in local_names:
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
        )
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
        page_id_clean = profile['notion_page_id'].replace('-', '')
        return jsonify({
            'email_draft': email_draft,
            'full_content': content,
            'notion_url': f'https://www.notion.so/{page_id_clean}',
        })
    except Exception as e:
        return jsonify({'error': f'Notion Fehler: {str(e)}'}), 500


# --- Profile Routes ---

@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    """Get all influencer profiles with product counts."""
    profiles = db.get_all_profiles()

    # Enrich with product count from matcher
    for p in profiles:
        if matcher:
            products = matcher.get_products_for_influencer(p['name'])
            p['product_count'] = len(products)
        else:
            p['product_count'] = 0

    return jsonify(profiles)


@app.route('/api/profiles/<path:name>', methods=['GET'])
def get_profile(name):
    """Get single profile, auto-create from matcher data if needed."""
    profile = db.get_profile(name)

    if not profile:
        profile = db.upsert_profile(name, display_name=name)

    # Add products from matcher
    products = []
    if matcher:
        products = matcher.get_products_for_influencer(name)

    profile['products'] = products
    profile['product_count'] = len(products)

    return jsonify(profile)


@app.route('/api/profiles/<path:name>', methods=['PUT'])
def update_profile(name):
    """Update profile ratings/notes."""
    data = request.get_json()

    allowed_fields = {
        'rating_reliability', 'rating_content_quality',
        'rating_communication', 'notes', 'instagram_handle',
        'display_name',
    }
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if not updates:
        return jsonify({'error': 'Keine gueltigen Felder'}), 400

    profile = db.upsert_profile(name, **updates)
    return jsonify(profile)


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
