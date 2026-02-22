// Global state
let currentResults = [];
let allProfiles = [];
let allProductsOverview = [];
let currentProfileName = null;
let notionConnected = false;
let isAdmin = false;
let profileSortField = 'name';
let profileSortDir = 'asc';

// Initialize on page load
document.addEventListener('DOMContentLoaded', async function() {
    loadStats();
    loadAISettings();
    await loadNotionSettings();
    handleURLParams();
    loadAuthStatus();
    loadContactNames();
    loadProductNames();

    // Default to profiles tab — load profiles immediately
    loadProfiles();

    // Auto-sync Notion if connected (silent, in background)
    if (notionConnected) {
        autoSyncNotion();
    }

    // Dropzone only needs setup when matcher tab is visited (lazy)
    setupDropzone();
    setupFileInput();
});

// --- Auth Status ---

async function loadAuthStatus() {
    try {
        const response = await fetch('/api/auth/status');
        const data = await response.json();
        isAdmin = data.is_admin;
        applyAdminVisibility();
    } catch (error) {
        console.error('Failed to load auth status:', error);
    }
}

function applyAdminVisibility() {
    const adminSettings = document.getElementById('adminOnlySettings');
    const adminHint = document.getElementById('adminOnlyHint');
    if (adminSettings) adminSettings.style.display = isAdmin ? '' : 'none';
    if (adminHint) adminHint.style.display = isAdmin ? 'none' : '';
}

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

// --- Collapsible Sections ---

function toggleCollapsible(header) {
    const section = header.parentElement;
    const body = section.querySelector('.collapsible-body');
    const arrow = header.querySelector('.collapsible-arrow');
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : 'block';
    arrow.classList.toggle('open', !isOpen);
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
    // Set active button via data-tab attribute
    const activeBtn = document.querySelector(`.nav-btn[data-tab="${tabName}"]`);
    if (activeBtn) activeBtn.classList.add('active');
    // Load data for tab
    if (tabName === 'profiles') loadProfiles();
    if (tabName === 'products') loadProductsOverview();
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

// --- Autocomplete ---

async function loadContactNames() {
    try {
        const response = await fetch('/api/contacts');
        const names = await response.json();
        const datalist = document.getElementById('contactNamesList');
        if (datalist) {
            datalist.innerHTML = names.map(n => `<option value="${n}">`).join('');
        }
    } catch (error) {
        console.error('Failed to load contact names:', error);
    }
}

async function loadProductNames() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        if (data.products) {
            const datalist = document.getElementById('productNamesList');
            if (datalist) {
                datalist.innerHTML = data.products.map(p => `<option value="${p}">`).join('');
            }
        }
    } catch (error) {
        console.error('Failed to load product names:', error);
    }
}

function populateProfileAutocomplete() {
    const datalist = document.getElementById('profileNamesList');
    if (datalist && allProfiles.length) {
        datalist.innerHTML = allProfiles.map(p =>
            `<option value="${p.display_name || p.name}">`
        ).join('');
    }
}

// --- Profiles ---

async function loadProfiles() {
    try {
        const response = await fetch('/api/profiles');
        allProfiles = await response.json();
        renderProfileList(allProfiles);
        populateProfileAutocomplete();
        loadTagSuggestions();
    } catch (error) {
        document.getElementById('profileList').innerHTML =
            `<div class="error">Fehler: ${error.message}</div>`;
    }
}

function filterProfiles() {
    const query = document.getElementById('profileSearchInput').value.toLowerCase();
    const tagFilter = (document.getElementById('tagFilter') || {}).value || '';
    const filtered = allProfiles.filter(p => {
        const nameMatch = (p.name || '').toLowerCase().includes(query) ||
            (p.display_name || '').toLowerCase().includes(query);
        const tagMatch = !tagFilter || (p.tags && p.tags.includes(tagFilter));
        return nameMatch && tagMatch;
    });
    renderProfileList(filtered);
}

function sortProfiles(field) {
    if (profileSortField === field) {
        profileSortDir = profileSortDir === 'asc' ? 'desc' : 'asc';
    } else {
        profileSortField = field;
        profileSortDir = 'asc';
    }
    // Update header styles
    document.querySelectorAll('.list-header .sort-col').forEach(col => {
        col.classList.remove('active', 'desc');
        if (col.dataset.sort === field) {
            col.classList.add('active');
            if (profileSortDir === 'desc') col.classList.add('desc');
        }
    });
    renderProfileList(allProfiles);
}

function formatFollowerCount(n) {
    if (!n || n === 0) return '-';
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace('.0', '') + 'M';
    if (n >= 1000) return Math.round(n / 1000) + 'k';
    return String(n);
}

function renderProfileList(profiles) {
    const container = document.getElementById('profileList');
    if (!profiles.length) {
        container.innerHTML = '<div class="no-data">Keine Profile gefunden</div>';
        return;
    }

    // Sort
    const sorted = [...profiles].sort((a, b) => {
        let valA, valB;
        if (profileSortField === 'name') {
            valA = (a.display_name || a.name || '').toLowerCase();
            valB = (b.display_name || b.name || '').toLowerCase();
        } else if (profileSortField === 'follower') {
            valA = a.notion_follower || 0;
            valB = b.notion_follower || 0;
        } else if (profileSortField === 'products') {
            valA = a.product_count || 0;
            valB = b.product_count || 0;
        }
        if (valA < valB) return profileSortDir === 'asc' ? -1 : 1;
        if (valA > valB) return profileSortDir === 'asc' ? 1 : -1;
        return 0;
    });

    container.innerHTML = sorted.map(p => {
        const followerStr = formatFollowerCount(p.notion_follower);
        const isActive = p.name === currentProfileName ? ' active' : '';
        const tagDots = (p.tags || []).slice(0, 3).map(t => `<span class="tag-dot" title="${t}" style="background:${tagColor(t)}"></span>`).join('');
        return `
            <div class="profile-row${isActive}" onclick="openProfile('${p.name.replace(/'/g, "\\'")}')">
                <div class="profile-row-name">${p.display_name || p.name}${tagDots ? '<span class="tag-dots">' + tagDots + '</span>' : ''}</div>
                <div class="profile-row-followers">${followerStr}</div>
                <div class="profile-row-count">${p.product_count || 0}</div>
            </div>
        `;
    }).join('');
}

function tagColor(tag) {
    const colors = ['#8a4da6', '#f29184', '#efc15f', '#10B981', '#6366F1', '#EC4899', '#F59E0B', '#3B82F6', '#14B8A6', '#F97316'];
    let hash = 0;
    for (let i = 0; i < tag.length; i++) hash = tag.charCodeAt(i) + ((hash << 5) - hash);
    return colors[Math.abs(hash) % colors.length];
}

async function openProfile(name) {
    currentProfileName = name;
    const detailSection = document.getElementById('profileDetail');
    const placeholder = document.getElementById('profileDetailPlaceholder');

    placeholder.style.display = 'none';
    detailSection.style.display = 'block';

    // Reset all collapsible sections to collapsed state
    detailSection.querySelectorAll('.collapsible-section').forEach(s => {
        const body = s.querySelector('.collapsible-body');
        const arrow = s.querySelector('.collapsible-arrow');
        if (body) body.style.display = 'none';
        if (arrow) arrow.classList.remove('open');
    });

    // On mobile: scroll to detail section
    if (window.innerWidth <= 768) {
        detailSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // Highlight active row in list
    document.querySelectorAll('.profile-row').forEach(row => row.classList.remove('active'));
    document.querySelectorAll('.profile-row').forEach(row => {
        if (row.onclick && row.onclick.toString().includes(name.replace(/'/g, "\\'"))) {
            row.classList.add('active');
        }
    });

    try {
        const response = await fetch(`/api/profiles/${encodeURIComponent(name)}`);
        const profile = await response.json();

        document.getElementById('profileDetailName').textContent = profile.display_name || profile.name;
        document.getElementById('profileDetailCount').textContent = `${profile.product_count} Produkte`;

        // Avatar (photo > notion icon > instagram avatar > initials)
        const avatarDiv = document.getElementById('profileAvatar');
        const displayName = profile.display_name || profile.name;
        const initials = displayName.split(/\s+/).map(w => w[0]).join('').substring(0, 2).toUpperCase();
        const avatarColors = ['#8a4da6', '#f29184', '#efc15f', '#10B981', '#6366F1', '#EC4899', '#F59E0B', '#3B82F6'];
        let hash = 0;
        for (let i = 0; i < displayName.length; i++) hash = displayName.charCodeAt(i) + ((hash << 5) - hash);
        const colorIdx = Math.abs(hash) % avatarColors.length;
        const fallbackInitials = () => { avatarDiv.textContent = initials; avatarDiv.style.backgroundColor = avatarColors[colorIdx]; };
        const igHandle = (profile.instagram_handle || '').replace(/^@/, '');

        if (profile.profile_photo) {
            avatarDiv.innerHTML = `<img src="/api/profiles/${encodeURIComponent(profile.name)}/photo" alt="${initials}">`;
            avatarDiv.style.backgroundColor = 'transparent';
        } else if (profile.notion_icon_url) {
            avatarDiv.innerHTML = `<img src="${profile.notion_icon_url}" alt="${initials}">`;
            avatarDiv.style.backgroundColor = 'transparent';
            avatarDiv.querySelector('img').onerror = function() { fallbackInitials(); };
        } else {
            fallbackInitials();
        }

        // AI Analysis button visibility
        const aiBtn = document.getElementById('aiAnalysisBtn');
        const aiResult = document.getElementById('aiAnalysisResult');
        if (aiBtn) {
            aiBtn.style.display = profile.ai_configured ? '' : 'none';
            aiBtn.textContent = 'KI-Analyse';
            aiBtn.disabled = false;
        }
        if (aiResult) aiResult.style.display = 'none';

        // Instagram link
        const igLink = document.getElementById('profileInstagram');
        const handle = profile.instagram_handle;
        if (handle) {
            const cleanHandle = handle.replace(/^@/, '');
            igLink.href = `https://instagram.com/${cleanHandle}`;
            igLink.textContent = `@${cleanHandle}`;
            igLink.style.display = '';
        } else {
            igLink.style.display = 'none';
        }

        // Email address
        const emailLink = document.getElementById('profileEmail');
        if (profile.email) {
            emailLink.href = `mailto:${profile.email}`;
            emailLink.textContent = profile.email;
            emailLink.style.display = '';
        } else {
            emailLink.style.display = 'none';
        }

        // Tags
        renderProfileTags(profile);

        // Follower count in header
        const followerEl = document.getElementById('profileFollowerCount');
        if (profile.notion_follower && profile.notion_follower > 0) {
            followerEl.textContent = Number(profile.notion_follower).toLocaleString('de-DE') + ' Follower';
            followerEl.style.display = '';
        } else {
            followerEl.style.display = 'none';
        }

        // Status badges & Prio Alice
        const statusSection = document.getElementById('profileStatusSection');
        const statusBadges = document.getElementById('profileStatusBadges');
        const prioBadge = document.getElementById('profilePrioBadge');

        const hasStatus = profile.notion_status && profile.notion_status.trim();
        const hasPrio = profile.prio_alice && profile.prio_alice.trim();

        if (hasStatus || hasPrio) {
            statusSection.style.display = '';
            // Status badges (comma-separated multi_select)
            if (hasStatus) {
                statusBadges.innerHTML = profile.notion_status.split(',').map(s => {
                    const status = s.trim();
                    const cssClass = 'status-badge status-badge-' + status.toLowerCase().replace(/\s+/g, '-');
                    return `<span class="${cssClass}">${status}</span>`;
                }).join('');
            } else {
                statusBadges.innerHTML = '';
            }
            // Prio Alice badge
            if (hasPrio) {
                const prio = profile.prio_alice.trim();
                const prioClass = 'prio-badge prio-' + prio.toLowerCase().replace(/\s+/g, '-');
                prioBadge.className = prioClass;
                prioBadge.textContent = 'Prio: ' + prio;
                prioBadge.style.display = '';
            } else {
                prioBadge.style.display = 'none';
            }
        } else {
            statusSection.style.display = 'none';
        }

        // Website Links
        const websiteDiv = document.getElementById('profileWebsiteLinks');
        const links = [];
        if (profile.website_link_1) links.push(profile.website_link_1);
        if (profile.website_link_2) links.push(profile.website_link_2);
        if (links.length > 0) {
            websiteDiv.style.display = '';
            websiteDiv.innerHTML = '<h3>Website-Links</h3>' + links.map(url => {
                let domain = '';
                try { domain = new URL(url).hostname.replace('www.', ''); } catch(e) { domain = url; }
                return `<a href="${url}" target="_blank" class="website-link-card">
                    <img src="https://www.google.com/s2/favicons?domain=${domain}&sz=32" alt="" class="website-favicon">
                    <span>${domain}</span>
                </a>`;
            }).join('');
        } else {
            websiteDiv.style.display = 'none';
        }

        // CS Hinweis (Cornerstone)
        const csDiv = document.getElementById('profileCSHinweis');
        if (profile.cs_hinweis && profile.cs_hinweis.trim()) {
            csDiv.style.display = '';
            csDiv.innerHTML = `<strong>CS Hinweis</strong><p>${profile.cs_hinweis}</p>`;
        } else {
            csDiv.style.display = 'none';
        }

        // Notes
        document.getElementById('profileNotes').value = profile.notes || '';

        // Products (with links to goodmood-food.de)
        const productsDiv = document.getElementById('profileProducts');
        const productsListDiv = document.getElementById('profileProductsList');
        if (profile.products && profile.products.length > 0) {
            productsDiv.style.display = 'block';
            productsListDiv.innerHTML = `
                <ul class="profile-product-list">
                    ${profile.products.map(p => {
                        if (typeof p === 'object' && p.url) {
                            return `<li><a href="${p.url}" target="_blank" class="product-link">${p.name}</a></li>`;
                        }
                        const name = typeof p === 'object' ? p.name : p;
                        return `<li>${name}</li>`;
                    }).join('')}
                </ul>
            `;
        } else {
            productsDiv.style.display = 'none';
        }

        // Notion data (collab history + email draft)
        const notionDiv = document.getElementById('profileNotionData');
        const emailDraftDiv = document.getElementById('profileEmailDraft');
        const collabDiv = document.getElementById('profileCollabHistory');

        if (profile.notion_page_id) {
            notionDiv.style.display = 'none'; // No separate Notion section needed

            if (profile.collab_history) {
                collabDiv.style.display = 'block';
                document.getElementById('collabHistoryContent').innerHTML =
                    `<div class="collab-history-content">${marked.parse(profile.collab_history)}</div>`;
            } else {
                collabDiv.style.display = 'none';
            }

            if (profile.email_draft) {
                emailDraftDiv.style.display = 'block';
                document.getElementById('emailDraftContent').innerHTML =
                    `<div class="email-draft-content">${marked.parse(profile.email_draft)}</div>`;
            } else {
                emailDraftDiv.style.display = 'none';
            }
        } else if (notionConnected) {
            notionDiv.style.display = 'block';
            notionDiv.innerHTML = '<p class="no-data">Kein Notion-Eintrag verknuepft. ' +
                '<a href="#" onclick="switchMainTab(\'settings\'); return false;" style="color: var(--primary-light);">In Einstellungen synchronisieren</a></p>';
            collabDiv.style.display = 'none';
            emailDraftDiv.style.display = 'none';
        } else {
            notionDiv.style.display = 'none';
            collabDiv.style.display = 'none';
            emailDraftDiv.style.display = 'none';
        }

        // Re-render list to update active highlight
        renderProfileList(allProfiles.filter(p => {
            const query = (document.getElementById('profileSearchInput').value || '').toLowerCase();
            if (!query) return true;
            return (p.name || '').toLowerCase().includes(query) || (p.display_name || '').toLowerCase().includes(query);
        }));
    } catch (error) {
        showToast('Profil konnte nicht geladen werden', 'error');
    }
}


// --- Tags ---

function renderProfileTags(profile) {
    const section = document.getElementById('profileTags');
    const list = document.getElementById('profileTagsList');
    const tags = profile.tags || [];

    section.style.display = 'block';
    list.innerHTML = tags.map(tag =>
        `<span class="tag-chip" style="background:${tagColor(tag)}30; color:${tagColor(tag)}; border-color:${tagColor(tag)}40;">
            ${tag}
            <span class="tag-remove" onclick="removeTag('${tag.replace(/'/g, "\\'")}')">&times;</span>
        </span>`
    ).join('') || '<span class="no-tags">Keine Tags</span>';

    // Load tag suggestions
    loadTagSuggestions();
}

async function loadTagSuggestions() {
    try {
        const response = await fetch('/api/tags');
        const tags = await response.json();
        const datalist = document.getElementById('tagSuggestions');
        if (datalist) {
            datalist.innerHTML = tags.map(t => `<option value="${t}">`).join('');
        }
        // Also update the filter dropdown
        const filter = document.getElementById('tagFilter');
        if (filter) {
            const currentVal = filter.value;
            filter.innerHTML = '<option value="">Alle Tags</option>' +
                tags.map(t => `<option value="${t}"${t === currentVal ? ' selected' : ''}>${t}</option>`).join('');
        }
    } catch (error) {
        console.error('Failed to load tags:', error);
    }
}

async function addTagFromInput() {
    if (!currentProfileName) return;
    const input = document.getElementById('tagInput');
    const tag = input.value.trim();
    if (!tag) return;

    try {
        await fetch(`/api/profiles/${encodeURIComponent(currentProfileName)}/tags`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'add', tag })
        });
        input.value = '';
        openProfile(currentProfileName);
        loadProfiles();
    } catch (error) {
        showToast('Tag konnte nicht hinzugefuegt werden', 'error');
    }
}

async function removeTag(tag) {
    if (!currentProfileName) return;
    try {
        await fetch(`/api/profiles/${encodeURIComponent(currentProfileName)}/tags`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'remove', tag })
        });
        openProfile(currentProfileName);
        loadProfiles();
    } catch (error) {
        showToast('Tag konnte nicht entfernt werden', 'error');
    }
}


async function saveProfileNotes() {
    if (!currentProfileName) return;
    const notes = document.getElementById('profileNotes').value;
    const hint = document.getElementById('notionSyncHint');
    const btn = document.querySelector('#profileDetail .btn-primary.btn-small');
    if (btn) { btn.textContent = 'Speichert...'; btn.disabled = true; }

    try {
        const url = `/api/profiles/${encodeURIComponent(currentProfileName)}`;
        console.log('[Notes] Saving to:', url, 'notes:', notes);
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes })
        });
        console.log('[Notes] Response status:', response.status);
        const data = await response.json();
        console.log('[Notes] Response data:', JSON.stringify(data));
        if (data.notion_synced) {
            showToast('In Notion gespeichert!', 'success');
            if (hint) { hint.textContent = 'Notion OK'; hint.style.display = ''; }
        } else if (data.notion_error) {
            showToast('Notion-Fehler: ' + data.notion_error, 'error');
        } else {
            showToast('Gespeichert (kein Notion-Profil)', 'success');
            if (hint) hint.style.display = 'none';
        }
    } catch (error) {
        console.error('[Notes] Error:', error);
        showToast('Speichern fehlgeschlagen: ' + error.message, 'error');
    } finally {
        if (btn) { btn.textContent = 'Notizen speichern'; btn.disabled = false; }
    }
}

// --- Photo Upload ---

async function uploadProfilePhoto() {
    if (!currentProfileName) return;
    const input = document.getElementById('photoUploadInput');
    const file = input.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('photo', file);

    try {
        const response = await fetch(`/api/profiles/${encodeURIComponent(currentProfileName)}/photo`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (data.success) {
            showToast('Foto hochgeladen', 'success');
            openProfile(currentProfileName);
        } else {
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('Upload fehlgeschlagen: ' + error.message, 'error');
    }
    input.value = '';
}

// --- AI Profile Analysis ---

async function generateProfileAnalysis() {
    if (!currentProfileName) return;
    const btn = document.getElementById('aiAnalysisBtn');
    const resultDiv = document.getElementById('aiAnalysisResult');

    btn.textContent = 'KI denkt nach...';
    btn.disabled = true;

    try {
        const response = await fetch(`/api/profiles/${encodeURIComponent(currentProfileName)}/ai-analysis`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        const data = await response.json();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `
            <div class="ai-explanation-content">
                <strong>KI-Profil-Analyse:</strong>
                <div class="ai-typewriter"></div>
            </div>
        `;

        await typewriterEffect(
            resultDiv.querySelector('.ai-typewriter'),
            data.analysis
        );
    } catch (error) {
        showToast('KI-Fehler: ' + error.message, 'error');
    } finally {
        btn.textContent = 'KI-Analyse';
        btn.disabled = false;
    }
}

// --- Products Tab ---

async function loadProductsOverview() {
    try {
        const response = await fetch('/api/products/overview');
        allProductsOverview = await response.json();
        renderProductList(allProductsOverview);
    } catch (error) {
        document.getElementById('productList').innerHTML =
            `<div class="error">Fehler: ${error.message}</div>`;
    }
}

function filterProductList() {
    const query = document.getElementById('productSearchInput').value.toLowerCase();
    if (!query) {
        renderProductList(allProductsOverview);
        return;
    }
    const filtered = allProductsOverview.filter(p =>
        p.name.toLowerCase().includes(query)
    );
    renderProductList(filtered);
}

function renderProductList(products) {
    const container = document.getElementById('productList');
    if (!products.length) {
        container.innerHTML = '<div class="no-data">Keine Produkte gefunden</div>';
        return;
    }

    container.innerHTML = products.map(p => `
        <div class="product-row" onclick="openProduct('${p.name.replace(/'/g, "\\'")}')">
            <div class="product-row-name">${p.name}</div>
            <div class="product-row-count">${p.influencer_count} Influencer</div>
        </div>
    `).join('');
}

function openProduct(productName) {
    const product = allProductsOverview.find(p => p.name === productName);
    if (!product) return;

    const detail = document.getElementById('productDetail');
    const placeholder = document.getElementById('productDetailPlaceholder');

    placeholder.style.display = 'none';
    detail.style.display = 'block';

    document.getElementById('productDetailName').textContent = product.name;
    document.getElementById('productDetailCount').textContent =
        `${product.influencer_count} Influencer haben mit diesem Produkt gearbeitet`;

    const listDiv = document.getElementById('productInfluencers');
    listDiv.innerHTML = product.influencers.map(name => `
        <div class="product-influencer-row" onclick="switchToProfile('${name.replace(/'/g, "\\'")}')">
            <span class="product-influencer-name">${name}</span>
            <span class="product-influencer-link">Profil ansehen &rarr;</span>
        </div>
    `).join('');

    // Highlight active product
    document.querySelectorAll('.product-row').forEach(row => row.classList.remove('active'));
    document.querySelectorAll('.product-row').forEach(row => {
        if (row.querySelector('.product-row-name').textContent === productName) {
            row.classList.add('active');
        }
    });
}

function switchToProfile(name) {
    switchMainTab('profiles');
    setTimeout(() => openProfile(name), 200);
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
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Synchronisiere...';
    }

    try {
        const response = await fetch('/api/notion/sync', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            if (statusSpan) statusSpan.textContent = `${data.synced} synchronisiert, ${data.created} neu erstellt`;
            showToast(`Notion-Sync fertig: ${data.synced} Eintraege`, 'success');
            loadProfiles();
        } else {
            if (statusSpan) statusSpan.textContent = data.error;
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('Sync fehlgeschlagen: ' + error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Notion-Daten synchronisieren';
        }
    }
}

async function autoSyncNotion() {
    try {
        const response = await fetch('/api/notion/sync', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            console.log(`Auto-sync: ${data.synced} Eintraege synchronisiert`);
            loadProfiles();
        }
    } catch (error) {
        console.error('Auto-sync fehlgeschlagen:', error);
    }
}

// Email draft and collab history are now auto-loaded in openProfile() via the profile GET endpoint.
// No separate on-demand load functions needed.

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

    element.innerHTML = marked.parse(markdown);
}

// --- Drag & Drop Upload ---

function setupDropzone() {
    const dropzone = document.getElementById('dropzone');
    if (!dropzone) return;

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
    const fi = document.getElementById('fileInput');
    if (fi) fi.addEventListener('change', function(e) { uploadFiles(e.target.files); });
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
            loadContactNames();
            loadProductNames();
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

document.getElementById('tagInput')?.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); addTagFromInput(); }
});
