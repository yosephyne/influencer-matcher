// Global state
let currentResults = [];
let allProfiles = [];
let currentProfileName = null;
let notionConnected = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    setupDropzone();
    setupFileInput();
    loadStats();
    loadAISettings();
    loadNotionSettings();
    handleURLParams();
});

// --- URL Parameter Handling (OAuth callback) ---

function handleURLParams() {
    const params = new URLSearchParams(window.location.search);
    const settings = params.get('settings');

    if (settings === 'connected') {
        switchMainTab('settings');
        loadAISettings();
        showToast('KI erfolgreich verbunden!', 'success');
        window.history.replaceState({}, '', '/');
    } else if (settings === 'error') {
        switchMainTab('settings');
        const msg = params.get('msg') || 'Verbindungsfehler';
        showToast(msg, 'error');
        window.history.replaceState({}, '', '/');
    }
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// --- Main Navigation ---

function switchMainTab(tabName) {
    // Hide all main tabs
    document.querySelectorAll('.main-tab-content').forEach(tab => {
        tab.style.display = 'none';
    });
    // Remove active from all nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    // Show selected tab
    document.getElementById('main-' + tabName).style.display = 'block';
    // Set active button
    document.querySelectorAll('.nav-btn').forEach(btn => {
        if (btn.textContent.trim().toLowerCase().startsWith(tabName.substring(0, 4))) {
            btn.classList.add('active');
        }
    });
    // Load data for tab
    if (tabName === 'profiles') loadProfiles();
    if (tabName === 'settings') { loadAISettings(); loadNotionSettings(); }
}

// --- AI Settings ---

async function loadAISettings() {
    try {
        const response = await fetch('/api/settings/ai');
        const data = await response.json();
        const statusDiv = document.getElementById('connectionStatus');
        const connectSection = document.getElementById('connectSection');
        const disconnectSection = document.getElementById('disconnectSection');
        const dot = document.getElementById('aiStatusDot');

        if (data.configured) {
            statusDiv.innerHTML = `
                <div class="status-connected">
                    <span class="status-icon">&#x2713;</span>
                    <div>
                        <strong>${data.provider_name}</strong>
                        <span class="key-preview">${data.key_preview}</span>
                        ${data.model ? `<span class="model-info">Modell: ${data.model}</span>` : ''}
                    </div>
                </div>
            `;
            connectSection.style.display = 'none';
            disconnectSection.style.display = 'block';
            dot.classList.add('connected');
            dot.classList.remove('disconnected');
        } else {
            statusDiv.innerHTML = `
                <div class="status-disconnected">
                    Keine KI verbunden
                </div>
            `;
            connectSection.style.display = 'block';
            disconnectSection.style.display = 'none';
            dot.classList.add('disconnected');
            dot.classList.remove('connected');
        }
    } catch (error) {
        console.error('Failed to load AI settings:', error);
    }
}

function connectOpenRouter() {
    window.open('/oauth/connect', '_blank');
}

async function disconnectAI() {
    if (!confirm('KI-Verbindung wirklich trennen?')) return;

    try {
        await fetch('/api/settings/ai/disconnect', { method: 'POST' });
        loadAISettings();
        showToast('Verbindung getrennt', 'success');
    } catch (error) {
        showToast('Fehler beim Trennen', 'error');
    }
}

async function saveManualKey() {
    const provider = document.getElementById('manualProvider').value;
    const apiKey = document.getElementById('manualApiKey').value.trim();
    const statusDiv = document.getElementById('manualKeyStatus');

    if (!apiKey) {
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = '<div class="error">Bitte API-Key eingeben</div>';
        return;
    }

    statusDiv.style.display = 'block';
    statusDiv.innerHTML = '<div class="loading">Key wird getestet...</div>';

    try {
        const response = await fetch('/api/settings/ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: apiKey })
        });

        const data = await response.json();

        if (data.success) {
            statusDiv.innerHTML = '<div class="success">Key gespeichert!</div>';
            document.getElementById('manualApiKey').value = '';
            loadAISettings();
        } else {
            statusDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="error">Fehler: ${error.message}</div>`;
    }
}

// --- Profiles ---

async function loadProfiles() {
    try {
        const response = await fetch('/api/profiles');
        allProfiles = await response.json();
        renderProfileList(allProfiles);
    } catch (error) {
        document.getElementById('profileList').innerHTML =
            `<div class="error">Fehler: ${error.message}</div>`;
    }
}

function filterProfiles() {
    const query = document.getElementById('profileSearchInput').value.toLowerCase();
    const filtered = allProfiles.filter(p =>
        (p.name || '').toLowerCase().includes(query) ||
        (p.display_name || '').toLowerCase().includes(query)
    );
    renderProfileList(filtered);
}

function renderProfileList(profiles) {
    const container = document.getElementById('profileList');
    if (!profiles.length) {
        container.innerHTML = '<div class="no-data">Keine Profile gefunden</div>';
        return;
    }

    container.innerHTML = profiles.map(p => {
        const avgRating = Math.round(
            ((p.rating_reliability || 0) + (p.rating_content_quality || 0) + (p.rating_communication || 0)) / 3
        );
        const stars = avgRating > 0 ? '&#9733;'.repeat(avgRating) + '&#9734;'.repeat(5 - avgRating) : '&#9734;&#9734;&#9734;&#9734;&#9734;';
        return `
            <div class="profile-row" onclick="openProfile('${p.name.replace(/'/g, "\\'")}')">
                <div class="profile-row-name">${p.display_name || p.name}</div>
                <div class="profile-row-stars">${stars}</div>
                <div class="profile-row-count">${p.product_count || 0} Produkte</div>
            </div>
        `;
    }).join('');
}

async function openProfile(name) {
    currentProfileName = name;
    const detailSection = document.getElementById('profileDetail');
    detailSection.style.display = 'block';

    try {
        const response = await fetch(`/api/profiles/${encodeURIComponent(name)}`);
        const profile = await response.json();

        document.getElementById('profileDetailName').textContent = profile.display_name || profile.name;
        document.getElementById('profileDetailCount').textContent = `${profile.product_count} Produkte`;

        // Render stars
        renderStars('stars-reliability', profile.rating_reliability || 0, 'rating_reliability');
        renderStars('stars-content', profile.rating_content_quality || 0, 'rating_content_quality');
        renderStars('stars-communication', profile.rating_communication || 0, 'rating_communication');

        // Notes
        document.getElementById('profileNotes').value = profile.notes || '';

        // Products
        const productsDiv = document.getElementById('profileProducts');
        if (profile.products && profile.products.length > 0) {
            productsDiv.innerHTML = `
                <h3>Produkt-Historie</h3>
                <ul class="profile-product-list">
                    ${profile.products.map(p => `<li>${p}</li>`).join('')}
                </ul>
            `;
        } else {
            productsDiv.innerHTML = '<p class="no-data">Keine Produkt-Historie</p>';
        }

        // Notion data
        const notionDiv = document.getElementById('profileNotionData');
        const emailDiv = document.getElementById('profileEmailDraft');

        if (profile.notion_page_id) {
            notionDiv.style.display = 'block';
            document.getElementById('profileNotionStatus').textContent = profile.notion_status || '-';
            document.getElementById('profileNotionStatus').className =
                'notion-badge notion-status-' + (profile.notion_status || '').toLowerCase().replace(/\s+/g, '-');
            document.getElementById('profileNotionFollower').textContent =
                profile.notion_follower ? Number(profile.notion_follower).toLocaleString('de-DE') + ' Follower' : '';
            document.getElementById('profileNotionProdukt').textContent = profile.notion_produkt || '';
            const notionLink = document.getElementById('profileNotionLink');
            notionLink.href = `https://www.notion.so/${profile.notion_page_id.replace(/-/g, '')}`;

            // Show email draft section with load button
            emailDiv.style.display = 'block';
            document.getElementById('emailDraftContent').innerHTML = '';
            document.getElementById('loadEmailBtn').style.display = '';
            document.getElementById('loadEmailBtn').disabled = false;
            document.getElementById('loadEmailBtn').textContent = 'E-Mail laden';
        } else if (notionConnected) {
            // Notion is connected but this profile has no match yet
            notionDiv.style.display = 'block';
            notionDiv.innerHTML = '<h3>Notion-Daten</h3><p class="no-data">Kein Notion-Eintrag verknuepft. ' +
                '<a href="#" onclick="switchMainTab(\'settings\'); return false;" style="color: var(--primary-light);">In Einstellungen synchronisieren</a></p>';
            emailDiv.style.display = 'none';
        } else {
            notionDiv.style.display = 'none';
            emailDiv.style.display = 'none';
        }

        // Scroll to detail
        detailSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
        showToast('Profil konnte nicht geladen werden', 'error');
    }
}

function renderStars(containerId, currentValue, field) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    for (let i = 1; i <= 5; i++) {
        const star = document.createElement('span');
        star.className = 'star' + (i <= currentValue ? ' active' : '');
        star.innerHTML = '&#9733;';
        star.addEventListener('click', () => setRating(field, i));
        container.appendChild(star);
    }
}

async function setRating(field, value) {
    if (!currentProfileName) return;

    try {
        await fetch(`/api/profiles/${encodeURIComponent(currentProfileName)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: value })
        });

        // Re-render stars
        const containerMap = {
            'rating_reliability': 'stars-reliability',
            'rating_content_quality': 'stars-content',
            'rating_communication': 'stars-communication'
        };
        renderStars(containerMap[field], value, field);
        loadProfiles(); // Refresh list
    } catch (error) {
        showToast('Bewertung konnte nicht gespeichert werden', 'error');
    }
}

async function saveProfileNotes() {
    if (!currentProfileName) return;
    const notes = document.getElementById('profileNotes').value;

    try {
        await fetch(`/api/profiles/${encodeURIComponent(currentProfileName)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes })
        });
        showToast('Notizen gespeichert', 'success');
    } catch (error) {
        showToast('Speichern fehlgeschlagen', 'error');
    }
}

// --- Notion Settings ---

async function loadNotionSettings() {
    try {
        const response = await fetch('/api/settings/notion');
        const data = await response.json();
        const statusDiv = document.getElementById('notionConnectionStatus');
        const connectSection = document.getElementById('notionConnectSection');
        const disconnectSection = document.getElementById('notionDisconnectSection');

        notionConnected = data.connected;

        if (data.connected) {
            statusDiv.innerHTML = `
                <div class="status-connected">
                    <span class="status-icon">&#x2713;</span>
                    <div>
                        <strong>Notion verbunden</strong>
                        <span class="key-preview">${data.token_preview}</span>
                    </div>
                </div>
            `;
            connectSection.style.display = 'none';
            disconnectSection.style.display = 'block';
        } else {
            statusDiv.innerHTML = `
                <div class="status-disconnected">Nicht verbunden</div>
            `;
            connectSection.style.display = 'block';
            disconnectSection.style.display = 'none';
        }
    } catch (error) {
        console.error('Failed to load Notion settings:', error);
    }
}

async function saveNotionToken() {
    const token = document.getElementById('notionToken').value.trim();
    const statusDiv = document.getElementById('notionTokenStatus');

    if (!token) {
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = '<div class="error">Bitte Token eingeben</div>';
        return;
    }

    statusDiv.style.display = 'block';
    statusDiv.innerHTML = '<div class="loading">Token wird getestet...</div>';

    try {
        const response = await fetch('/api/settings/notion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token })
        });
        const data = await response.json();

        if (data.success) {
            statusDiv.innerHTML = '<div class="success">Verbunden! Daten werden synchronisiert...</div>';
            document.getElementById('notionToken').value = '';
            loadNotionSettings();
            showToast('Notion verbunden — Sync laeuft...', 'success');
            // Auto-sync immediately after connecting
            await syncNotion();
        } else {
            statusDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="error">Fehler: ${error.message}</div>`;
    }
}

async function disconnectNotion() {
    if (!confirm('Notion-Verbindung wirklich trennen?')) return;

    await fetch('/api/settings/notion/disconnect', { method: 'POST' });
    loadNotionSettings();
    showToast('Notion getrennt', 'success');
}

async function syncNotion() {
    const btn = document.getElementById('notionSyncBtn');
    const statusSpan = document.getElementById('notionSyncStatus');
    btn.disabled = true;
    btn.textContent = 'Synchronisiere...';

    try {
        const response = await fetch('/api/notion/sync', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            statusSpan.textContent = `${data.synced} synchronisiert, ${data.created} neu erstellt`;
            showToast(`Notion-Sync fertig: ${data.synced} Eintraege`, 'success');
            loadProfiles();
        } else {
            statusSpan.textContent = data.error;
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('Sync fehlgeschlagen: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Notion-Daten synchronisieren';
    }
}

// --- Email Draft (on-demand from Notion) ---

async function loadEmailDraft() {
    if (!currentProfileName) return;

    const btn = document.getElementById('loadEmailBtn');
    const contentDiv = document.getElementById('emailDraftContent');
    btn.disabled = true;
    btn.textContent = 'Wird geladen...';

    try {
        const response = await fetch(
            `/api/profiles/${encodeURIComponent(currentProfileName)}/notion`
        );
        const data = await response.json();

        if (data.error) {
            contentDiv.innerHTML = `<div class="error">${data.error}</div>`;
            return;
        }

        if (data.email_draft) {
            contentDiv.innerHTML = `<div class="email-draft-content">${marked.parse(data.email_draft)}</div>`;
            btn.style.display = 'none';
        } else {
            contentDiv.innerHTML = '<p class="no-data">Kein E-Mail-Entwurf vorhanden</p>';
        }
    } catch (error) {
        contentDiv.innerHTML = `<div class="error">Fehler: ${error.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'E-Mail laden';
    }
}

// --- AI Explain Match ---

async function explainMatch(name, product) {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = 'KI denkt nach...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/ai/explain-match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, product })
        });

        const data = await response.json();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        // Show explanation with typewriter effect
        let explanationDiv = btn.parentElement.querySelector('.ai-explanation');
        if (!explanationDiv) {
            explanationDiv = document.createElement('div');
            explanationDiv.className = 'ai-explanation';
            btn.parentElement.appendChild(explanationDiv);
        }
        explanationDiv.innerHTML = `
            <div class="ai-explanation-content">
                <strong>KI-Analyse:</strong>
                <div class="ai-typewriter"></div>
            </div>
        `;

        await typewriterEffect(
            explanationDiv.querySelector('.ai-typewriter'),
            data.explanation
        );
    } catch (error) {
        showToast('KI-Fehler: ' + error.message, 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

async function typewriterEffect(element, markdown) {
    const cursor = document.createElement('span');
    cursor.className = 'typewriter-cursor';

    let displayed = '';
    const chars = markdown.split('');
    const chunkSize = 3;

    for (let i = 0; i < chars.length; i += chunkSize) {
        displayed += chars.slice(i, i + chunkSize).join('');
        element.innerHTML = marked.parse(displayed);
        element.appendChild(cursor);
        await new Promise(r => setTimeout(r, 15));
    }

    // Final render without cursor
    element.innerHTML = marked.parse(markdown);
}

// --- Drag & Drop Upload ---

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
    statusDiv.innerHTML = '<div class="loading">Dateien werden verarbeitet...</div>';

    try {
        const response = await fetch('/api/upload-data', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            statusDiv.innerHTML = `
                <div class="success">
                    &#x2713; ${data.contacts_loaded} Kontakte und ${data.products_found} Produkte geladen
                    <br>Dateien: ${data.uploaded.join(', ')}
                </div>
            `;
            loadStats();
        } else {
            statusDiv.innerHTML = `<div class="error">Fehler: ${data.error}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="error">Upload fehlgeschlagen: ${error.message}</div>`;
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
        alert('Bitte einen Namen eingeben');
        return;
    }

    const resultsDiv = document.getElementById('searchResults');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = '<div class="loading">Suche...</div>';

    try {
        const response = await fetch('/api/search-influencer', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
        });

        const data = await response.json();

        if (data.found) {
            const explainBtn = `<button class="btn btn-small btn-ai" onclick="explainMatch('${data.matched_name.replace(/'/g, "\\'")}', '${(data.products[0] || '').replace(/'/g, "\\'")}')">KI-Analyse</button>`;

            resultsDiv.innerHTML = `
                <div class="search-result">
                    <h3>&#x2713; Gefunden: ${data.matched_name}</h3>
                    <p class="match-score">Match Score: ${data.match_score}%</p>
                    <div class="products-list">
                        <strong>Produkt-Historie:</strong>
                        ${data.products.length > 0
                            ? '<ul>' + data.products.map(p => `<li>${p}</li>`).join('') + '</ul>'
                            : '<p class="no-data">Keine Produkt-Interaktionen gefunden</p>'}
                    </div>
                    ${data.products.length > 0 ? explainBtn : ''}
                </div>
            `;
        } else {
            resultsDiv.innerHTML = `
                <div class="no-result">
                    <p>Kein Ergebnis fuer "${name}"</p>
                    <p class="hint">Pruefe die Schreibweise oder die hochgeladenen Daten</p>
                </div>
            `;
        }
    } catch (error) {
        resultsDiv.innerHTML = `<div class="error">Suche fehlgeschlagen: ${error.message}</div>`;
    }
}

// Verify single assignment
async function verifySingle() {
    const name = document.getElementById('verifySingleName').value.trim();
    const product = document.getElementById('verifySingleProduct').value.trim();

    if (!name || !product) {
        alert('Bitte Name und Produkt eingeben');
        return;
    }

    const resultDiv = document.getElementById('verifySingleResult');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="loading">Wird geprueft...</div>';

    try {
        const response = await fetch('/api/verify-single', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, product})
        });

        const data = await response.json();

        const statusClass = data.verified ? 'verified' : data.status === 'NO_DATA' ? 'no-data' : 'mismatch';
        const icon = data.verified ? '&#x2713;' : data.status === 'NO_DATA' ? '?' : '!';

        const explainBtn = `<button class="btn btn-small btn-ai" onclick="explainMatch('${(data.matched_name || name).replace(/'/g, "\\'")}', '${product.replace(/'/g, "\\'")}')">KI-Analyse</button>`;

        resultDiv.innerHTML = `
            <div class="verification-result ${statusClass}">
                <h3>${icon} ${data.message}</h3>
                ${data.matched_name ? `<p><strong>Gefunden als:</strong> ${data.matched_name} (${data.score}%)</p>` : ''}
                ${data.products && data.products.length > 0
                    ? `<div class="products-list">
                        <strong>Bisherige Produkte:</strong>
                        <ul>${data.products.map(p => `<li>${p}</li>`).join('')}</ul>
                       </div>`
                    : ''}
                ${explainBtn}
            </div>
        `;
    } catch (error) {
        resultDiv.innerHTML = `<div class="error">Pruefung fehlgeschlagen: ${error.message}</div>`;
    }
}

// Verify batch
async function verifyBatch() {
    const fileInput = document.getElementById('batchFile');
    const file = fileInput.files[0];

    if (!file) {
        alert('Bitte eine Datei auswaehlen');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    const resultsDiv = document.getElementById('batchResults');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = '<div class="loading">Batch wird verarbeitet...</div>';

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
                    <div class="stat-label">&#x2713; Verifiziert</div>
                </div>
                <div class="stat-box mismatch">
                    <div class="stat-number">${data.stats.mismatches}</div>
                    <div class="stat-label">! Abweichung</div>
                </div>
                <div class="stat-box no-data">
                    <div class="stat-number">${data.stats.no_data}</div>
                    <div class="stat-label">? Keine Daten</div>
                </div>
                <div class="stat-box total">
                    <div class="stat-number">${data.stats.total}</div>
                    <div class="stat-label">Gesamt</div>
                </div>
            </div>
        `;

        // Build table
        const tbody = document.querySelector('#resultsTable tbody');
        tbody.innerHTML = '';

        data.results.forEach(row => {
            const statusClass = row.Verified ? 'status-verified' :
                              row.Status === 'NO_DATA' ? 'status-no-data' : 'status-mismatch';
            const statusIcon = row.Verified ? '&#x2713;' : row.Status === 'NO_DATA' ? '?' : '!';

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${row.Name}</td>
                <td>${row['Assigned Product']}</td>
                <td><span class="${statusClass}">${statusIcon} ${row.Status}</span></td>
                <td class="products-cell">${row['Historical Products'] || '\u2014'}</td>
                <td>${row['Match Score']}%</td>
            `;
            tbody.appendChild(tr);
        });

        resultsDiv.innerHTML = statsHtml + resultsDiv.innerHTML;

    } catch (error) {
        resultsDiv.innerHTML = `<div class="error">Batch-Pruefung fehlgeschlagen: ${error.message}</div>`;
    }
}

// Export results to Excel
async function exportResults() {
    if (currentResults.length === 0) {
        alert('Keine Ergebnisse zum Exportieren');
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
        alert('Export fehlgeschlagen: ' + error.message);
    }
}

// Tab switching (within cards)
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.style.display = 'none';
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById('tab-' + tabName).style.display = 'block';
    event.target.classList.add('active');
}

// --- Password Change ---

async function changePassword() {
    const oldPw = document.getElementById('oldPassword').value;
    const newPw = document.getElementById('newPassword').value;
    const statusDiv = document.getElementById('passwordChangeStatus');

    if (!oldPw || !newPw) {
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = '<div class="error">Beide Felder ausfuellen</div>';
        return;
    }

    statusDiv.style.display = 'block';
    statusDiv.innerHTML = '<div class="loading">Wird geaendert...</div>';

    try {
        const response = await fetch('/api/settings/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_password: oldPw, new_password: newPw })
        });
        const data = await response.json();

        if (data.success) {
            statusDiv.innerHTML = '<div class="success">Passwort geaendert!</div>';
            document.getElementById('oldPassword').value = '';
            document.getElementById('newPassword').value = '';
        } else {
            statusDiv.innerHTML = `<div class="error">${data.error}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="error">Fehler: ${error.message}</div>`;
    }
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
