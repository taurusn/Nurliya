"""
Hybrid Text + Vector Matching Module

Combines text-based substring matching with vector similarity
to catch obvious matches that vectors miss.

Usage:
    from hybrid_matcher import hybrid_match, text_matches_product

    # Check text match
    if text_matches_product("V60 جواتيمالا", "v60", ["V60 كولومبي"]):
        print("Text match!")

    # Hybrid matching
    matched, score, method = hybrid_match(
        mention_text="V60 جواتيمالا",
        canonical_text="v60",
        variants=["V60 كولومبي"],
        vector_score=0.58
    )
"""

from typing import List, Tuple, Optional

# Minimum characters for substring matching to avoid false positives
# e.g., "بن" (2 chars) matching "بنانا" (banana)
MIN_MATCH_LENGTH = 3

# Vector similarity threshold
VECTOR_THRESHOLD = 0.80


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip whitespace."""
    if not text:
        return ""
    return text.lower().strip()


def text_matches_product(
    mention_text: str,
    canonical_text: str,
    variants: Optional[List[str]] = None,
    min_length: int = MIN_MATCH_LENGTH
) -> bool:
    """
    Check if mention text matches a product via substring matching.

    Rules:
    1. Product canonical text is IN mention (e.g., "V60" in "V60 جواتيمالا")
    2. Mention is IN product canonical text (e.g., "v60" in "v60 كولومبي")
    3. Any variant matches by same rules
    4. Minimum length requirement to avoid short string false positives

    Args:
        mention_text: The mention text to check
        canonical_text: Product's canonical text
        variants: List of product variants (optional)
        min_length: Minimum characters for match (default 3)

    Returns:
        True if text match found, False otherwise
    """
    mention = normalize_text(mention_text)
    canonical = normalize_text(canonical_text)

    # Empty strings don't match
    if not mention or not canonical:
        return False

    # Check canonical text both ways (with min length)
    if len(canonical) >= min_length and canonical in mention:
        return True
    if len(mention) >= min_length and mention in canonical:
        return True

    # Check variants
    if variants:
        for variant in variants:
            variant_norm = normalize_text(variant)
            if not variant_norm:
                continue
            if len(variant_norm) >= min_length and variant_norm in mention:
                return True
            if len(mention) >= min_length and mention in variant_norm:
                return True

    return False


def hybrid_match(
    mention_text: str,
    canonical_text: str,
    variants: Optional[List[str]],
    vector_score: float,
    vector_threshold: float = VECTOR_THRESHOLD,
    min_text_length: int = MIN_MATCH_LENGTH
) -> Tuple[bool, float, str]:
    """
    Hybrid matching: try text first, then vector.

    Algorithm:
    1. If text matches → return (True, 1.0, "text")
    2. Else if vector_score >= threshold → return (True, vector_score, "vector")
    3. Else → return (False, vector_score, "none")

    Args:
        mention_text: The mention text
        canonical_text: Product's canonical text
        variants: Product variants list
        vector_score: Pre-computed vector similarity score
        vector_threshold: Minimum vector score to match (default 0.80)
        min_text_length: Minimum chars for text match (default 3)

    Returns:
        Tuple of (matched: bool, score: float, method: str)
        - method is "text", "vector", or "none"
    """
    # Try text match first (fast path)
    if text_matches_product(mention_text, canonical_text, variants, min_text_length):
        return (True, 1.0, "text")

    # Fall back to vector match
    if vector_score >= vector_threshold:
        return (True, vector_score, "vector")

    # No match
    return (False, vector_score, "none")


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def find_text_match_for_orphan(
    mention_text: str,
    products: list,
    use_variants: bool = False
) -> Optional[str]:
    """
    Find a product that text-matches the given mention.

    Args:
        mention_text: The orphan mention text
        products: List of product objects with canonical_text and variants
        use_variants: Whether to check variants (default False for safety)

    Returns:
        Product ID if match found, None otherwise
    """
    for product in products:
        variants = product.variants if use_variants else None
        if text_matches_product(mention_text, product.canonical_text, variants):
            return str(product.id)
    return None


def rescue_orphan_mentions(session, taxonomy_id: str, use_variants: bool = False) -> int:
    """
    Find and link orphan mentions that can be rescued by text matching.

    This is meant to be called after clustering to catch obvious matches
    that HDBSCAN missed due to vector embedding limitations.

    Args:
        session: Database session
        taxonomy_id: The taxonomy to process
        use_variants: Whether to use variants (default False)

    Returns:
        Number of orphans rescued
    """
    from database import TaxonomyProduct, RawMention

    # Get all products for this taxonomy
    products = session.query(TaxonomyProduct).filter(
        TaxonomyProduct.taxonomy_id == taxonomy_id
    ).all()

    if not products:
        return 0

    # Get product orphans (mentions without discovered_product_id)
    # that belong to places in this taxonomy
    taxonomy = session.query(TaxonomyProduct).filter_by(
        taxonomy_id=taxonomy_id
    ).first()

    if not taxonomy:
        return 0

    # Get orphan mentions for the taxonomy's places
    orphans = session.query(RawMention).filter(
        RawMention.discovered_product_id.is_(None),
        RawMention.mention_type == 'product'
    ).all()

    rescued = 0
    for orphan in orphans:
        product_id = find_text_match_for_orphan(
            orphan.mention_text,
            products,
            use_variants
        )
        if product_id:
            # Find the product to get its category
            product = next((p for p in products if str(p.id) == product_id), None)
            if product:
                orphan.discovered_product_id = product.id
                orphan.discovered_category_id = product.discovered_category_id
                rescued += 1

    if rescued > 0:
        session.commit()

    return rescued
