// Global state
let currentResults = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    setupDropzone();
    setupFileInput();
    loadStats();
});

// Drag & drop file upload
function setupDropzone() {
    const dropzone = document.getElementById('dropzone');
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.add('highlight'), false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.remove('highlight'), false);
    });
    
    dropzone.addEventListener('drop', handleDrop, false);
    dropzone.addEventListener('click', () => document.getElementById('fileInput').click());
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    uploadFiles(files);
}

function setupFileInput() {
    document.getElementById('fileInput').addEventListener('change', function(e) {
        uploadFiles(e.target.files);
    });
}

// Upload collaboration data files
async function uploadFiles(files) {
    const formData = new FormData();
    
    for (let file of files) {
        formData.append('files', file);
    }
    
    const statusDiv = document.getElementById('uploadStatus');
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = '<div class="loading">Uploading and processing files...</div>';
    
    try {
        const response = await fetch('/api/upload-data', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            statusDiv.innerHTML = `
                <div class="success">
                    ✓ Loaded ${data.contacts_loaded} contacts and ${data.products_found} products
                    <br>Files: ${data.uploaded.join(', ')}
                </div>
            `;
            loadStats();
        } else {
            statusDiv.innerHTML = `<div class="error">Error: ${data.error}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="error">Upload failed: ${error.message}</div>`;
    }
}

// Load statistics
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        if (data.loaded) {
            document.getElementById('stats').style.display = 'flex';
            document.getElementById('stat-contacts').textContent = data.total_contacts;
            document.getElementById('stat-products').textContent = data.total_products;
        }
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// Search for influencer
async function searchInfluencer() {
    const name = document.getElementById('searchInput').value.trim();
    
    if (!name) {
        alert('Please enter a name');
        return;
    }
    
    const resultsDiv = document.getElementById('searchResults');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
    
    try {
        const response = await fetch('/api/search-influencer', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
        });
        
        const data = await response.json();
        
        if (data.found) {
            resultsDiv.innerHTML = `
                <div class="search-result">
                    <h3>✓ Found: ${data.matched_name}</h3>
                    <p class="match-score">Match Score: ${data.match_score}%</p>
                    <div class="products-list">
                        <strong>Product History:</strong>
                        ${data.products.length > 0 
                            ? '<ul>' + data.products.map(p => `<li>${p}</li>`).join('') + '</ul>'
                            : '<p class="no-data">No product interactions found</p>'}
                    </div>
                </div>
            `;
        } else {
            resultsDiv.innerHTML = `
                <div class="no-result">
                    <p>❌ No match found for "${name}"</p>
                    <p class="hint">Try a different spelling or check the uploaded data</p>
                </div>
            `;
        }
    } catch (error) {
        resultsDiv.innerHTML = `<div class="error">Search failed: ${error.message}</div>`;
    }
}

// Verify single assignment
async function verifySingle() {
    const name = document.getElementById('verifySingleName').value.trim();
    const product = document.getElementById('verifySingleProduct').value.trim();
    
    if (!name || !product) {
        alert('Please enter both name and product');
        return;
    }
    
    const resultDiv = document.getElementById('verifySingleResult');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="loading">Verifying...</div>';
    
    try {
        const response = await fetch('/api/verify-single', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, product})
        });
        
        const data = await response.json();
        
        const statusClass = data.verified ? 'verified' : data.status === 'NO_DATA' ? 'no-data' : 'mismatch';
        const icon = data.verified ? '✓' : data.status === 'NO_DATA' ? '❓' : '⚠';
        
        resultDiv.innerHTML = `
            <div class="verification-result ${statusClass}">
                <h3>${icon} ${data.message}</h3>
                ${data.matched_name ? `<p><strong>Matched as:</strong> ${data.matched_name} (${data.score}%)</p>` : ''}
                ${data.products && data.products.length > 0 
                    ? `<div class="products-list">
                        <strong>Historical Products:</strong>
                        <ul>${data.products.map(p => `<li>${p}</li>`).join('')}</ul>
                       </div>`
                    : ''}
            </div>
        `;
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Verification failed: ${error.message}</div>`;
    }
}

// Verify batch
async function verifyBatch() {
    const fileInput = document.getElementById('batchFile');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    const resultsDiv = document.getElementById('batchResults');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = '<div class="loading">Processing batch verification...</div>';
    
    try {
        const response = await fetch('/api/verify-batch', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        currentResults = data.results;
        
        // Show statistics
        const statsHtml = `
            <div class="batch-stats-grid">
                <div class="stat-box verified">
                    <div class="stat-number">${data.stats.verified}</div>
                    <div class="stat-label">✓ Verified</div>
                </div>
                <div class="stat-box mismatch">
                    <div class="stat-number">${data.stats.mismatches}</div>
                    <div class="stat-label">⚠ Mismatches</div>
                </div>
                <div class="stat-box no-data">
                    <div class="stat-number">${data.stats.no_data}</div>
                    <div class="stat-label">❓ No Data</div>
                </div>
                <div class="stat-box total">
                    <div class="stat-number">${data.stats.total}</div>
                    <div class="stat-label">Total</div>
                </div>
            </div>
        `;
        
        // Build table
        const tbody = document.querySelector('#resultsTable tbody');
        tbody.innerHTML = '';
        
        data.results.forEach(row => {
            const statusClass = row.Verified ? 'status-verified' : 
                              row.Status === 'NO_DATA' ? 'status-no-data' : 'status-mismatch';
            const statusIcon = row.Verified ? '✓' : row.Status === 'NO_DATA' ? '❓' : '⚠';
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${row.Name}</td>
                <td>${row['Assigned Product']}</td>
                <td><span class="${statusClass}">${statusIcon} ${row.Status}</span></td>
                <td class="products-cell">${row['Historical Products'] || '—'}</td>
                <td>${row['Match Score']}%</td>
            `;
            tbody.appendChild(tr);
        });
        
        resultsDiv.innerHTML = statsHtml + resultsDiv.innerHTML;
        
    } catch (error) {
        resultsDiv.innerHTML = `<div class="error">Batch verification failed: ${error.message}</div>`;
    }
}

// Export results to Excel
async function exportResults() {
    if (currentResults.length === 0) {
        alert('No results to export');
        return;
    }
    
    try {
        const response = await fetch('/api/export-results', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({results: currentResults})
        });
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'verification_results.xlsx';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } catch (error) {
        alert('Export failed: ' + error.message);
    }
}

// Tab switching
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.style.display = 'none';
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById('tab-' + tabName).style.display = 'block';
    
    // Add active class to clicked button
    event.target.classList.add('active');
}

// Enter key handlers
document.getElementById('searchInput')?.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') searchInfluencer();
});

document.getElementById('verifySingleName')?.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') document.getElementById('verifySingleProduct').focus();
});

document.getElementById('verifySingleProduct')?.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') verifySingle();
});
