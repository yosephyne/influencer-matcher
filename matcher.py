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
    
    def __init__(self, data_dir: Path):
        """
        Args:
            data_dir: Directory containing collaboration CSV/Excel files
        """
        self.data_dir = Path(data_dir)
        self.collaboration_data = {}  # name -> [product interactions]
        self.all_products = set()
        
    def load_collaboration_files(self, file_patterns: List[str] = None) -> None:
        """
        Load all CSV/Excel files from data directory
        
        Args:
            file_patterns: Optional list of glob patterns (e.g., ['*.csv', '*.xlsx'])
        """
        if file_patterns is None:
            file_patterns = ['*.csv', '*.xlsx']
            
        for pattern in file_patterns:
            for filepath in self.data_dir.glob(pattern):
                self._load_single_file(filepath)
                
        print(f"Loaded {len(self.collaboration_data)} unique contacts")
        print(f"Found {len(self.all_products)} unique products")
    
    def _load_single_file(self, filepath: Path) -> None:
        """Load a single CSV or Excel file and extract collaborations"""
        try:
            # Read file based on extension
            if filepath.suffix == '.csv':
                df = pd.read_csv(filepath, encoding='utf-8')
            else:
                df = pd.read_excel(filepath)
            
            # Extract name and product columns
            # Assumes first column is name, other columns may contain products
            for _, row in df.iterrows():
                name = self._normalize_name(str(row.iloc[0]))
                if not name or len(name) < 3:
                    continue
                
                # Extract products from all text in row
                products = self._extract_products_from_row(row)
                
                if name not in self.collaboration_data:
                    self.collaboration_data[name] = []
                self.collaboration_data[name].extend(products)
                self.all_products.update(products)
                
        except Exception as e:
            print(f"Warning: Could not load {filepath.name}: {e}")
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name for matching (lowercase, remove @, trim whitespace)"""
        name = name.lower()
        name = re.sub(r'@', ' ', name)
        name = re.sub(r'\d+[.,]?\d*[km]', '', name)  # Remove follower counts
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    def _extract_products_from_row(self, row: pd.Series) -> List[str]:
        """
        Extract product names from row data
        Uses keyword matching for common GMF products
        """
        products = []
        row_text = ' '.join([str(v) for v in row if pd.notna(v)]).lower()
        
        # GMF product patterns
        product_patterns = {
            'Rohkakao Peru': ['peru', 'kakao peru'],
            'Rohkakao Ecuador': ['ecuador', 'kakao ecuador'],
            'Rohkakao Criollo': ['criollo'],
            'Coco Aminos': ['coco amino', 'cocoamino'],
            'Reishi': ['reishi'],
            'Lions Mane': ['lions mane', 'lion mane', "lion's mane"],
            'Ashwagandha': ['ashwagandha'],
            'Cordyceps': ['cordyceps'],
            'Chaga': ['chaga'],
            'Kakao Nibs': ['nib', 'nibs'],
            'Matcha': ['matcha'],
            'Chlorella': ['chlorella'],
            'Maca': ['maca'],
            'Lucuma': ['lucuma'],
        }
        
        for product_name, keywords in product_patterns.items():
            if any(kw in row_text for kw in keywords):
                products.append(product_name)
        
        return products
    
    def find_best_match(self, name: str, min_score: int = 70) -> Optional[Tuple[str, int]]:
        """
        Find best fuzzy match for a name in collaboration data
        
        Args:
            name: Name to search for
            min_score: Minimum fuzzy match score (0-100)
            
        Returns:
            Tuple of (matched_name, score) or None
        """
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
        """
        Get all products this influencer has interacted with
        
        Args:
            name: Influencer name (will be fuzzy matched)
            
        Returns:
            List of product names
        """
        match = self.find_best_match(name)
        if not match:
            return []
        
        matched_name, score = match
        return list(set(self.collaboration_data.get(matched_name, [])))
    
    def verify_assignment(self, name: str, assigned_product: str) -> Dict:
        """
        Verify if assigned product matches historical data
        
        Args:
            name: Influencer name
            assigned_product: Product assigned to them
            
        Returns:
            Dict with verification status and details
        """
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
        
        # Check if assigned product is in their history
        product_match = any(
            fuzz.partial_ratio(assigned_product.lower(), p.lower()) > 80 
            for p in products
        )
        
        if product_match:
            return {
                'status': 'VERIFIED',
                'message': f'✓ Product matches history (score: {score})',
                'matched_name': matched_name,
                'score': score,
                'products': products,
                'verified': True
            }
        elif products:
            return {
                'status': 'MISMATCH',
                'message': f'⚠ Product not in history. Alternatives: {", ".join(products[:3])}',
                'matched_name': matched_name,
                'score': score,
                'products': products,
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
        """
        Verify multiple assignments at once
        
        Args:
            assignments: Dict mapping {name: assigned_product}
            
        Returns:
            DataFrame with verification results
        """
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
