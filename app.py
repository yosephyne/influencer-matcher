"""
Web interface for Influencer-Product Matching

Modern, clean web UI for office use - runs locally on laptop.
"""

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from pathlib import Path
import pandas as pd
import json
from matcher import InfluencerMatcher

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = Path('data/uploads')
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)

# Global matcher instance
matcher = None


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
    output_path = Path('data/exports/verification_results.xlsx')
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


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx', 'xls'}


if __name__ == '__main__':
    # Run on localhost, accessible from browser
    print("\n" + "="*60)
    print("🚀 Influencer Matcher starting...")
    print("="*60)
    print("\n📱 Open in browser: http://localhost:5000")
    print("\n⚠️  Press CTRL+C to stop the server\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
