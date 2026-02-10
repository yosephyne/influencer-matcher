"""
Influencer-Product Matching Algorithm

Matches influencers to products based on historical collaboration data.
Reads CSV/Excel files with past collaborations and scores matches.
"""

import pandas as pd
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from thefuzz import fuzz


class InfluencerMatcher:
    """Core matching engine for influencer-product assignments"""

    # Column header patterns to find the name column
    NAME_HEADER_PATTERNS = ['name', 'ig name', 'mit wem', 'influencer', 'person']

    # GMF product patterns - extend this dict to add new products
    product_patterns = {
        # Kakao Produkte
        'Rohkakao Peru': ['peru', 'kakao peru', 'rohkakao per'],
        'Rohkakao Ecuador': ['ecuador', 'kakao ecuador', 'ecu md', 'ecu '],
        'Rohkakao Criollo': ['criollo'],
        'Kakao Nibs': ['nib', 'nibs', 'sweet nibs'],
        'Feel Good Kakao': ['feel good', 'feelgood'],
        'Rise Up & Shine': ['rise up', 'rise up & shine', 'rise up and shine', ' rus ', 'rus '],
        'Calm Down & Relax': ['calm down', 'calm down & relax', ' cdr ', 'cdr '],
        'The Wholy Bean': ['wholy bean'],
        'SinnPhonie': ['sinnphonie'],
        'Queen Beans': ['queen bean', 'queen beans', ' qb '],

        # Pilze / Vitalpilze
        'Reishi': ['reishi'],
        'Lions Mane': ['lions mane', 'lion mane', "lion's mane"],
        'Cordyceps': ['cordyceps'],
        'Chaga': ['chaga'],
        'Pure Power': ['pure power', ' pp '],
        'Vitalpilz Extrakte': ['vitalpilzextra', 'vitalpilz extra', 'vitalpilz-extra', 'pilzextrakt'],
        'Vitalpilz Kakao': ['vitalpilzkakao', 'vitalpilz kakao', 'vitalpilz-kakao'],

        # Superfoods
        'Coco Aminos': ['coco amino', 'cocoamino', 'würzsauce', 'wuerzsauce', 'gewürzbereitung'],
        'Ashwagandha': ['ashwagandha'],
        'Matcha': ['matcha'],
        'Chlorella': ['chlorella'],
        'Maca': ['maca'],
        'Lucuma': ['lucuma'],

        # Snacks & Weitere
        'Cashew Cluster': ['cashew cluster', 'cluster'],
        'Peru Butter Drops': ['butter drops', 'peru butter'],
    }

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.collaboration_data = {}  # normalized_name -> [product interactions]
        self.all_products = set()

    def load_collaboration_files(self, file_patterns: List[str] = None) -> None:
        """Load all CSV/Excel files from data directory"""
        if file_patterns is None:
            file_patterns = ['*.csv', '*.xlsx']

        for pattern in file_patterns:
            for filepath in self.data_dir.glob(pattern):
                self._load_single_file(filepath)

        print(f"Loaded {len(self.collaboration_data)} unique contacts")
        print(f"Found {len(self.all_products)} unique products")

    def _read_file_with_encoding_fallback(self, filepath: Path) -> Optional[pd.DataFrame]:
        """Read CSV/Excel with encoding fallbacks"""
        if filepath.suffix in ('.xlsx', '.xls'):
            try:
                return pd.read_excel(filepath)
            except Exception as e:
                print(f"  WARNING: Could not read Excel {filepath.name}: {e}")
                return None

        # CSV: try multiple encodings
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1']:
            try:
                return pd.read_csv(filepath, encoding=encoding)
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"  WARNING: Could not read {filepath.name} with {encoding}: {e}")
                continue

        print(f"  WARNING: Failed to read {filepath.name} with any encoding")
        return None

    def _find_name_column(self, df: pd.DataFrame) -> int:
        """
        Find the column index containing names (3-step strategy):
        1. Search headers for name-like patterns
        2. Fallback: column with most non-empty text entries
        3. Default: column 0
        """
        # Step 1: Search headers
        for col_idx, col_name in enumerate(df.columns):
            col_lower = str(col_name).lower().strip()
            # Handle multiline headers (e.g. "Name\nIG\nFollowers")
            col_lower = col_lower.split('\n')[0].strip()
            for pattern in self.NAME_HEADER_PATTERNS:
                if pattern in col_lower:
                    return col_idx

        # Step 2: Find column with most text entries (not numbers, not empty)
        best_col = 0
        best_count = 0
        for col_idx in range(min(5, len(df.columns))):
            text_count = 0
            for val in df.iloc[:, col_idx]:
                if pd.notna(val) and isinstance(val, str) and len(val.strip()) > 2:
                    if re.search(r'[a-zA-ZäöüÄÖÜß]', val):
                        text_count += 1
            if text_count > best_count:
                best_count = text_count
                best_col = col_idx

        if best_count > 0:
            return best_col

        # Step 3: Default
        print(f"  WARNING: Could not determine name column, using column 0")
        return 0

    def _extract_name_from_cell(self, cell_value) -> str:
        """
        Extract clean name from potentially messy cell content.
        Handles multiline cells like:
          "Celeste Mc Millian\\n@celestemcmillian\\n3K"
          "Hale Now Yoga Studio\\n@hale.now.studios"
        """
        if pd.isna(cell_value):
            return ''

        text = str(cell_value).strip()
        if not text:
            return ''

        # Split multiline cells, take first line as name
        lines = text.split('\n')
        name = lines[0].strip()

        return name

    def _load_single_file(self, filepath: Path) -> None:
        """Load a single CSV or Excel file and extract collaborations"""
        df = self._read_file_with_encoding_fallback(filepath)
        if df is None or df.empty:
            return

        name_col_idx = self._find_name_column(df)

        for _, row in df.iterrows():
            # Extract name from the identified column
            raw_name = self._extract_name_from_cell(row.iloc[name_col_idx])
            name = self._normalize_name(raw_name)

            if not name or len(name) < 3:
                continue

            # Extract products from all text in row
            products = self._extract_products_from_row(row)

            if name not in self.collaboration_data:
                self.collaboration_data[name] = []
            self.collaboration_data[name].extend(products)
            self.all_products.update(products)

        print(f"  Loaded: {filepath.name}")

    def _normalize_name(self, name: str) -> str:
        """Normalize name for matching (lowercase, remove @handles, trim)"""
        name = name.lower().strip()
        # If entire input is a single @handle, keep the handle text
        if re.match(r'^@[\w.]+$', name):
            name = name.lstrip('@').replace('.', ' ')
        else:
            name = re.sub(r'@[\w.]+', '', name)  # Remove @handles from mixed text
            name = re.sub(r'@', ' ', name)  # Remove stray @ signs
        name = re.sub(r'\d+[.,]?\d*\s*[km]\b', '', name, flags=re.IGNORECASE)  # Remove follower counts
        name = re.sub(r'\(.*?\)', '', name)  # Remove parenthetical info
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _extract_products_from_row(self, row: pd.Series) -> List[str]:
        """Extract product names from row data using keyword matching"""
        products = []
        row_text = ' '.join([str(v) for v in row if pd.notna(v)]).lower()
        # Add spaces around text to help match abbreviations like " rus " at boundaries
        row_text = f' {row_text} '

        for product_name, keywords in self.product_patterns.items():
            if any(kw in row_text for kw in keywords):
                products.append(product_name)

        return products

    def find_best_match(self, name: str, min_score: int = 70) -> Optional[Tuple[str, int]]:
        """Find best fuzzy match for a name in collaboration data"""
        name_norm = self._normalize_name(name)
        best_match = None
        best_score = 0

        for db_name in self.collaboration_data.keys():
            score = fuzz.token_set_ratio(name_norm, db_name)
            if score > best_score and score >= min_score:
                best_score = score
                best_match = db_name

        return (best_match, best_score) if best_match else None

    def get_products_for_influencer(self, name: str) -> List[str]:
        """Get all products this influencer has interacted with"""
        match = self.find_best_match(name)
        if not match:
            return []

        matched_name, score = match
        return list(set(self.collaboration_data.get(matched_name, [])))

    def verify_assignment(self, name: str, assigned_product: str) -> Dict:
        """Verify if assigned product matches historical data"""
        match = self.find_best_match(name)

        if not match:
            return {
                'status': 'NO_DATA',
                'message': 'No collaboration history found',
                'matched_name': None,
                'score': 0,
                'products': [],
                'verified': False
            }

        matched_name, score = match
        products = self.collaboration_data.get(matched_name, [])
        unique_products = list(set(products))

        # Check if assigned product is in their history
        product_match = any(
            fuzz.partial_ratio(assigned_product.lower(), p.lower()) > 80
            for p in unique_products
        )

        if product_match:
            return {
                'status': 'VERIFIED',
                'message': f'✓ Product matches history (score: {score})',
                'matched_name': matched_name,
                'score': score,
                'products': unique_products,
                'verified': True
            }
        elif unique_products:
            return {
                'status': 'MISMATCH',
                'message': f'⚠ Product not in history. Alternatives: {", ".join(unique_products[:3])}',
                'matched_name': matched_name,
                'score': score,
                'products': unique_products,
                'verified': False
            }
        else:
            return {
                'status': 'NO_PRODUCTS',
                'message': 'Contact found but no product history',
                'matched_name': matched_name,
                'score': score,
                'products': [],
                'verified': False
            }

    def batch_verify(self, assignments: Dict[str, str]) -> pd.DataFrame:
        """Verify multiple assignments at once, returns DataFrame"""
        results = []

        for name, product in assignments.items():
            verification = self.verify_assignment(name, product)
            results.append({
                'Name': name,
                'Assigned Product': product,
                'Status': verification['status'],
                'Verified': verification['verified'],
                'Match Score': verification['score'],
                'Historical Products': ', '.join(verification['products'][:5]),
                'Message': verification['message']
            })

        return pd.DataFrame(results)
