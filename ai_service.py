"""
Unified AI service using LiteLLM + OpenRouter OAuth PKCE.
Supports OpenAI, Anthropic Claude, and Google Gemini via OpenRouter or direct API keys.
"""

import hashlib
import secrets
import base64
import requests as http_requests
from litellm import completion


# OpenRouter OAuth endpoints
OPENROUTER_AUTH_URL = 'https://openrouter.ai/auth'
OPENROUTER_TOKEN_URL = 'https://openrouter.ai/api/v1/auth/keys'

# Default models per provider
PROVIDER_MODELS = {
    'openrouter': 'openrouter/auto',
    'openai': 'gpt-4o-mini',
    'anthropic': 'claude-3-5-haiku-20241022',
    'gemini': 'gemini/gemini-2.0-flash',
}

PROVIDER_NAMES = {
    'openrouter': 'OpenRouter (alle Modelle)',
    'openai': 'OpenAI',
    'anthropic': 'Anthropic (Claude)',
    'gemini': 'Google (Gemini)',
}


class AINotConfiguredError(Exception):
    """Raised when AI features are used without a configured provider."""
    pass


class AIService:
    """Unified AI layer with OpenRouter OAuth + LiteLLM completions."""

    def __init__(self, db):
        self.db = db
        # PKCE state stored in memory (lost on restart, user just re-connects)
        self._pkce_verifier = None

    # --- OpenRouter OAuth PKCE ---

    def get_oauth_url(self, callback_url):
        """Generate OpenRouter OAuth URL with PKCE challenge.
        Returns the URL to redirect the user to.
        """
        # Generate PKCE code_verifier (43-128 chars, URL-safe)
        self._pkce_verifier = secrets.token_urlsafe(64)

        # Create code_challenge = base64url(sha256(verifier))
        digest = hashlib.sha256(self._pkce_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()

        auth_url = (
            f"{OPENROUTER_AUTH_URL}"
            f"?callback_url={callback_url}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )
        return auth_url

    def handle_oauth_callback(self, code):
        """Exchange OAuth code for API key and store it.
        Returns {'success': True/False, 'error': '...' if failed}
        """
        if not self._pkce_verifier:
            return {'success': False, 'error': 'OAuth session abgelaufen. Bitte erneut verbinden.'}

        try:
            response = http_requests.post(
                OPENROUTER_TOKEN_URL,
                json={
                    'code': code,
                    'code_verifier': self._pkce_verifier,
                    'code_challenge_method': 'S256',
                }
            )

            if response.status_code != 200:
                return {'success': False, 'error': f'OpenRouter Fehler: {response.text}'}

            data = response.json()
            api_key = data.get('key')

            if not api_key:
                return {'success': False, 'error': 'Kein API-Key in der Antwort'}

            # Save encrypted
            self.db.save_ai_provider('openrouter', api_key, 'openrouter/auto')
            self._pkce_verifier = None  # Clear after use

            return {'success': True}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    # --- Configuration ---

    def is_configured(self):
        return self.db.get_ai_provider() is not None

    def get_status(self):
        """Get current AI connection status for UI."""
        config = self.db.get_ai_provider()
        if not config:
            return {'configured': False}

        key = config['api_key']
        return {
            'configured': True,
            'provider': config['provider'],
            'provider_name': PROVIDER_NAMES.get(config['provider'], config['provider']),
            'model': config.get('model', ''),
            'key_preview': key[:8] + '...' + key[-4:] if len(key) > 12 else key[:4] + '...',
        }

    def validate_api_key(self, provider, api_key):
        """Test if an API key is valid with a minimal call."""
        model = PROVIDER_MODELS.get(provider, 'gpt-4o-mini')

        # OpenRouter keys use the openai format but route through openrouter
        extra_kwargs = {}
        if provider == 'openrouter':
            extra_kwargs['api_base'] = 'https://openrouter.ai/api/v1'
            model = 'openrouter/auto'

        try:
            response = completion(
                model=model,
                api_key=api_key,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5,
                **extra_kwargs,
            )
            return {'valid': True, 'model': model}
        except Exception as e:
            return {'valid': False, 'error': str(e)}

    # --- AI Completions ---

    def _get_completion_kwargs(self):
        """Build LiteLLM completion kwargs from stored settings."""
        config = self.db.get_ai_provider()
        if not config:
            raise AINotConfiguredError(
                "Keine KI verbunden. Bitte unter Einstellungen verbinden."
            )

        provider = config['provider']
        api_key = config['api_key']
        model = config.get('model') or PROVIDER_MODELS.get(provider, 'gpt-4o-mini')

        kwargs = {'model': model, 'api_key': api_key}

        if provider == 'openrouter':
            kwargs['api_base'] = 'https://openrouter.ai/api/v1'

        return kwargs

    def explain_match(self, influencer_name, products, target_product, match_score):
        """AI explains WHY an influencer fits a product.
        Returns explanation text (German).
        """
        kwargs = self._get_completion_kwargs()

        system_prompt = (
            "Du bist ein Experte fuer Influencer-Marketing bei goodmoodfood, "
            "einer deutschen Marke fuer Rohkakao, Vitalpilze und Superfoods. "
            "Erklaere kurz und praxisnah (3-5 Saetze), warum ein Influencer "
            "zu einem Produkt passt oder nicht. Beruecksichtige die bisherige "
            "Kollaborationshistorie. Antworte auf Deutsch."
        )

        history_text = ', '.join(products) if products else 'Keine bisherigen Kollaborationen bekannt'

        user_prompt = (
            f"Influencer: {influencer_name}\n"
            f"Bisherige Produkte: {history_text}\n"
            f"Zugewiesenes Produkt: {target_product}\n"
            f"Match-Score: {match_score}%\n\n"
            f"Erklaere, warum diese Zuweisung sinnvoll ist oder was dagegen spricht."
        )

        response = completion(
            **kwargs,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=400,
            temperature=0.7,
        )
        return response.choices[0].message.content

    def analyze_profile(self, profile, products):
        """AI generates a comprehensive profile analysis.
        Returns analysis text (German).
        """
        kwargs = self._get_completion_kwargs()

        system_prompt = (
            "Du bist ein Experte fuer Influencer-Marketing bei goodmoodfood, "
            "einer deutschen Marke fuer Rohkakao, Vitalpilze und Superfoods. "
            "Erstelle eine kurze, praxisnahe Analyse (5-8 Saetze) dieses Influencer-Profils. "
            "Beruecksichtige Produkt-Historie, Follower-Zahl, Kooperationsstatus und Tags. "
            "Gib konkrete Empfehlungen fuer die zukuenftige Zusammenarbeit. Antworte auf Deutsch."
        )

        products_text = ', '.join(products) if products else 'Keine bisherigen Kollaborationen'
        follower = profile.get('notion_follower', 0) or 0
        status = profile.get('notion_status', '') or 'unbekannt'
        kontakt = profile.get('notion_kontakt', '') or 'unbekannt'
        rolle = profile.get('notion_rolle', '') or 'unbekannt'
        tags_raw = profile.get('tags', '[]')
        if isinstance(tags_raw, str):
            import json
            try:
                tags = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                tags = []
        else:
            tags = tags_raw
        tags_text = ', '.join(tags) if tags else 'keine'

        user_prompt = (
            f"Influencer: {profile.get('display_name') or profile.get('name', 'Unbekannt')}\n"
            f"Bisherige Produkte: {products_text}\n"
            f"Anzahl Produkte: {len(products)}\n"
            f"Follower: {follower:,}\n"
            f"Status: {status}\n"
            f"Kontakt: {kontakt}\n"
            f"Rolle: {rolle}\n"
            f"Tags: {tags_text}\n\n"
            f"Analysiere dieses Profil und gib Empfehlungen fuer die Zusammenarbeit."
        )

        response = completion(
            **kwargs,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=600,
            temperature=0.7,
        )
        return response.choices[0].message.content

    def suggest_products(self, influencer_name, products, all_products):
        """Phase 2: AI recommends best products for an influencer."""
        raise NotImplementedError("Kommt in Phase 2")

    def campaign_advisor(self, campaign_description, influencer_data):
        """Phase 2: AI ranks influencers for a campaign."""
        raise NotImplementedError("Kommt in Phase 2")
