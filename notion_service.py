"""
Notion integration for the Testimonials gmf database.
Reads influencer data (properties) and email drafts (page content) from Notion.
Uses requests directly — no extra SDK needed.
"""

import re
import requests as http_requests
from thefuzz import fuzz

# Hardcoded DB ID — this is the known TM-DB
NOTION_DATABASE_ID = '2ed091dd-0e99-8027-bf54-d3c73bc3067c'
NOTION_API_VERSION = '2022-06-28'
NOTION_API_BASE = 'https://api.notion.com/v1'


class NotionService:
    """Read-only access to the Testimonials gmf Notion database."""

    def __init__(self, db):
        self.db = db

    # --- Token Management ---

    def get_token(self):
        return self.db.get_setting('notion_token')

    def save_token(self, token):
        self.db.set_setting('notion_token', token, encrypt=True)

    def clear_token(self):
        self.db.delete_setting('notion_token')

    def is_connected(self):
        return self.get_token() is not None

    def get_status(self):
        token = self.get_token()
        if not token:
            return {'connected': False}
        return {
            'connected': True,
            'token_preview': token[:8] + '...' + token[-4:] if len(token) > 12 else '***',
            'database_id': NOTION_DATABASE_ID,
        }

    def test_connection(self, token=None):
        """Validate token by querying the database metadata."""
        token = token or self.get_token()
        if not token:
            return {'valid': False, 'error': 'Kein Token gespeichert'}

        try:
            resp = http_requests.get(
                f'{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}',
                headers=self._headers(token),
                timeout=10,
            )
            if resp.status_code == 200:
                return {'valid': True}
            elif resp.status_code == 401:
                return {'valid': False, 'error': 'Token ungueltig'}
            elif resp.status_code == 404:
                return {'valid': False, 'error': 'Datenbank nicht gefunden — wurde die Integration geteilt?'}
            else:
                return {'valid': False, 'error': f'Notion API Fehler: {resp.status_code}'}
        except Exception as e:
            return {'valid': False, 'error': str(e)}

    # --- Data Fetching ---

    def fetch_all_entries(self):
        """Query TM-DB, return list of flat dicts with all properties.
        Handles Notion pagination (max 100 per request).
        """
        token = self.get_token()
        if not token:
            raise RuntimeError('Notion nicht verbunden')

        headers = self._headers(token)
        entries = []
        has_more = True
        start_cursor = None

        while has_more:
            body = {'page_size': 100}
            if start_cursor:
                body['start_cursor'] = start_cursor

            resp = http_requests.post(
                f'{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}/query',
                headers=headers,
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for page in data.get('results', []):
                entry = self._parse_properties(page)
                if entry and entry.get('name'):
                    entries.append(entry)

            has_more = data.get('has_more', False)
            start_cursor = data.get('next_cursor')

        return entries

    def fetch_page_content(self, page_id):
        """Fetch all block children of a page, return as plain text."""
        token = self.get_token()
        if not token:
            raise RuntimeError('Notion nicht verbunden')

        headers = self._headers(token)
        blocks = []
        has_more = True
        start_cursor = None

        while has_more:
            url = f'{NOTION_API_BASE}/blocks/{page_id}/children?page_size=100'
            if start_cursor:
                url += f'&start_cursor={start_cursor}'

            resp = http_requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            blocks.extend(data.get('results', []))
            has_more = data.get('has_more', False)
            start_cursor = data.get('next_cursor')

        return self._blocks_to_text(blocks)

    def extract_email_draft(self, content_text):
        """Extract EMAIL NEU section from page content text.
        Looks for heading containing 'EMAIL NEU', captures until next heading or divider.
        """
        if not content_text:
            return None

        # Primary: heading with EMAIL NEU (e.g. "# 📧 EMAIL NEU ...")
        pattern = r'#+\s+.*EMAIL\s*NEU.*?\n(.*?)(?=\n#+\s+|\n---|\Z)'
        match = re.search(pattern, content_text, re.DOTALL | re.IGNORECASE)
        if match:
            draft = match.group(1).strip()
            return draft if draft else None

        # Fallback: emoji line with EMAIL NEU (e.g. callout block without heading marker)
        pattern2 = r'📧\s*EMAIL\s*NEU.*?\n(.*?)(?=\n#+\s+|\n---|\Z)'
        match2 = re.search(pattern2, content_text, re.DOTALL | re.IGNORECASE)
        if match2:
            draft = match2.group(1).strip()
            return draft if draft else None

        return None

    def extract_collab_history(self, content_text):
        """Extract everything from page content EXCEPT the EMAIL NEU section.
        Returns markdown string suitable for display.
        """
        if not content_text:
            return None

        lines = content_text.split('\n')
        result_lines = []
        skip = False

        for line in lines:
            # Detect start of EMAIL NEU section
            if re.search(r'(#+\s+.*EMAIL\s*NEU|📧\s*EMAIL\s*NEU)', line, re.IGNORECASE):
                skip = True
                continue

            # Detect next heading or divider → stop skipping
            if skip and (re.match(r'^#+\s+', line) or line.strip() == '---'):
                skip = False

            if not skip:
                result_lines.append(line)

        text = '\n'.join(result_lines).strip()
        return text if text else None

    # --- Property Parsers ---

    def _parse_properties(self, page):
        """Convert Notion page properties into a flat dict."""
        props = page.get('properties', {})
        # Extract page icon URL (profile picture)
        icon_url = ''
        icon_data = page.get('icon', {})
        if icon_data:
            icon_type = icon_data.get('type', '')
            if icon_type == 'external':
                icon_url = icon_data.get('external', {}).get('url', '')
            elif icon_type == 'file':
                icon_url = icon_data.get('file', {}).get('url', '')

        entry = {
            'notion_page_id': page['id'],
            'notion_url': page.get('url', ''),
            'icon_url': icon_url,
            'name': self._get_title(props.get('Name', {})),
            'follower': self._get_number(props.get('Follower', {})),
            'instagram': self._get_rich_text(props.get('Instagram', {})),
            'produkt': self._get_rich_text(props.get('Produkt', {})),
            'rolle': self._get_rich_text(props.get('Rolle', {})),
            'status': self._get_multi_select(props.get('Status', {})),
            'prioritaet': self._get_select(props.get('Priorität', {})),
            'prio_alice': self._get_select(props.get('PRIO Alice', {})),
            'email_version': self._get_select(props.get('Email-Version', {})),
            'kontakt': self._get_select(props.get('Kontakt', {})),
            'mapping_quelle': self._get_select(props.get('Mapping-Quelle', {})),
            'mapping_verifiziert': self._get_checkbox(props.get('Mapping verifiziert', {})),
            'hinweis': self._get_rich_text(props.get('Hinweis', {})),
            'extra_info': self._get_rich_text(props.get('Extra Info', {})),
            'matcher_notiz': self._get_rich_text(props.get('Matcher-Notiz', {})),
            'website_link_1': self._get_url(props.get('Website Link 1', {})),
            'website_link_2': self._get_url(props.get('Website-Link 2', {})),
            'cs_hinweis': self._get_rich_text(props.get('CS Hinweis', {})),
        }

        # Try to extract email address from various properties
        email = (self._get_email(props.get('E-Mail', {}))
                 or self._get_email(props.get('Email', {}))
                 or self._get_rich_text(props.get('E-Mail', {}))
                 or self._get_rich_text(props.get('Email', {})))
        if not email:
            # Fallback: regex in hinweis and extra_info
            for field in (entry.get('hinweis', ''), entry.get('extra_info', '')):
                m = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', field)
                if m:
                    email = m.group(0)
                    break
        entry['email'] = email or ''

        return entry

    def _get_title(self, prop):
        items = prop.get('title', [])
        return ''.join(t.get('plain_text', '') for t in items).strip() if items else ''

    def _get_rich_text(self, prop):
        items = prop.get('rich_text', [])
        return ''.join(t.get('plain_text', '') for t in items).strip() if items else ''

    def _get_number(self, prop):
        return prop.get('number') or 0

    def _get_select(self, prop):
        sel = prop.get('select')
        return sel.get('name', '') if sel else ''

    def _get_multi_select(self, prop):
        items = prop.get('multi_select', [])
        return ', '.join(item.get('name', '') for item in items) if items else ''

    def _get_url(self, prop):
        return prop.get('url', '') or ''

    def _get_checkbox(self, prop):
        return prop.get('checkbox', False)

    def _get_email(self, prop):
        """Extract email from a Notion email-type property."""
        return prop.get('email', '') or ''

    # --- Writing to Notion ---

    def add_comment(self, page_id, text):
        """Add a comment to a Notion page (used for syncing notes)."""
        token = self.get_token()
        if not token:
            raise RuntimeError('Notion nicht verbunden')

        prefixed = f'[Influencer Matcher] {text}'
        resp = http_requests.post(
            f'{NOTION_API_BASE}/comments',
            headers=self._headers(token),
            json={
                'parent': {'page_id': page_id},
                'rich_text': [{'text': {'content': prefixed[:2000]}}],
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True

    def _ensure_db_property(self, property_name, prop_type='rich_text'):
        """Ensure a property exists on the Notion database. Creates it if missing."""
        if not hasattr(self, '_known_properties'):
            self._known_properties = set()
        if property_name in self._known_properties:
            return

        token = self.get_token()
        if not token:
            return
        resp = http_requests.patch(
            f'{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}',
            headers=self._headers(token),
            json={'properties': {property_name: {prop_type: {}}}},
            timeout=10,
        )
        if resp.status_code == 200:
            self._known_properties.add(property_name)

    def update_property(self, page_id, property_name, value):
        """Update a rich_text property on a Notion page.
        Ensures the property exists on the database first.
        """
        token = self.get_token()
        if not token:
            raise RuntimeError('Notion nicht verbunden')

        self._ensure_db_property(property_name)

        resp = http_requests.patch(
            f'{NOTION_API_BASE}/pages/{page_id}',
            headers=self._headers(token),
            json={
                'properties': {
                    property_name: {
                        'rich_text': [{'text': {'content': value[:2000]}}] if value else []
                    }
                }
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True

    def update_page_icon(self, page_id, icon_url):
        """Set the icon of a Notion page to an external URL."""
        token = self.get_token()
        if not token:
            raise RuntimeError('Notion nicht verbunden')

        resp = http_requests.patch(
            f'{NOTION_API_BASE}/pages/{page_id}',
            headers=self._headers(token),
            json={
                'icon': {
                    'type': 'external',
                    'external': {'url': icon_url}
                }
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True

    # --- Block → Text Conversion ---

    def _blocks_to_text(self, blocks):
        """Convert Notion block list to readable plain text."""
        lines = []
        for block in blocks:
            block_type = block.get('type', '')
            content = block.get(block_type, {})

            if block_type in ('heading_1', 'heading_2', 'heading_3'):
                level = block_type[-1]
                text = self._rich_text_to_str(content.get('rich_text', []))
                lines.append(f'{"#" * int(level)} {text}')

            elif block_type == 'paragraph':
                text = self._rich_text_to_str(content.get('rich_text', []))
                lines.append(text)

            elif block_type in ('bulleted_list_item', 'numbered_list_item'):
                text = self._rich_text_to_str(content.get('rich_text', []))
                prefix = '- ' if block_type == 'bulleted_list_item' else '1. '
                lines.append(f'{prefix}{text}')

            elif block_type == 'divider':
                lines.append('---')

            elif block_type == 'quote':
                text = self._rich_text_to_str(content.get('rich_text', []))
                lines.append(f'> {text}')

            elif block_type == 'callout':
                icon = ''
                icon_data = content.get('icon', {})
                if icon_data.get('type') == 'emoji':
                    icon = icon_data.get('emoji', '') + ' '
                text = self._rich_text_to_str(content.get('rich_text', []))
                lines.append(f'{icon}{text}')

            elif block_type == 'toggle':
                text = self._rich_text_to_str(content.get('rich_text', []))
                lines.append(text)

            # Skip unsupported block types silently

        return '\n'.join(lines)

    def _rich_text_to_str(self, rich_text_list):
        """Join rich text items into a single string, preserving bold markers."""
        parts = []
        for item in rich_text_list:
            text = item.get('plain_text', '')
            annotations = item.get('annotations', {})
            if annotations.get('bold'):
                text = f'**{text}**'
            parts.append(text)
        return ''.join(parts)

    # --- Helpers ---

    def _headers(self, token=None):
        t = token or self.get_token()
        return {
            'Authorization': f'Bearer {t}',
            'Notion-Version': NOTION_API_VERSION,
            'Content-Type': 'application/json',
        }
