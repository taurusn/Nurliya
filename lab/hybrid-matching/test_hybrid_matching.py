#!/usr/bin/env python3
"""
Hybrid Text + Vector Matching Test Suite

Tests the hypothesis that combining text-based substring matching
with vector similarity will catch obvious matches that vectors miss.

Run: python test_hybrid_matching.py
"""

import sys
import os
from typing import List, Tuple, Optional
from dataclasses import dataclass

# Add pipline to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../pipline'))


# =============================================================================
# HYBRID MATCHING IMPLEMENTATION
# =============================================================================

def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip whitespace."""
    if not text:
        return ""
    return text.lower().strip()


def text_matches_product(
    mention_text: str,
    canonical_text: str,
    variants: Optional[List[str]] = None
) -> bool:
    """
    Check if mention text matches a product via substring matching.

    Matches if:
    1. Product canonical text is IN mention (e.g., "V60" in "V60 جواتيمالا")
    2. Mention is IN product canonical text (e.g., "v60" in "v60 كولومبي")
    3. Any variant matches by same rules

    Args:
        mention_text: The mention text to check
        canonical_text: Product's canonical text
        variants: List of product variants

    Returns:
        True if text match found, False otherwise
    """
    mention = normalize_text(mention_text)
    canonical = normalize_text(canonical_text)

    # Empty strings don't match
    if not mention or not canonical:
        return False

    # Check canonical text both ways
    if canonical in mention or mention in canonical:
        return True

    # Check variants
    if variants:
        for variant in variants:
            variant_norm = normalize_text(variant)
            if not variant_norm:
                continue
            if variant_norm in mention or mention in variant_norm:
                return True

    return False


def hybrid_match(
    mention_text: str,
    canonical_text: str,
    variants: Optional[List[str]],
    vector_score: float,
    vector_threshold: float = 0.80
) -> Tuple[bool, float, str]:
    """
    Hybrid matching: try text first, then vector.

    Args:
        mention_text: The mention text
        canonical_text: Product's canonical text
        variants: Product variants list
        vector_score: Pre-computed vector similarity score
        vector_threshold: Minimum vector score to match (default 0.80)

    Returns:
        Tuple of (matched: bool, score: float, method: str)
        - method is "text", "vector", or "none"
    """
    # Try text match first
    if text_matches_product(mention_text, canonical_text, variants):
        return (True, 1.0, "text")

    # Fall back to vector match
    if vector_score >= vector_threshold:
        return (True, vector_score, "vector")

    # No match
    return (False, vector_score, "none")


# =============================================================================
# TEST CASES
# =============================================================================

@dataclass
class TestCase:
    name: str
    mention: str
    canonical: str
    variants: List[str]
    vector_score: float
    expected_match: bool
    expected_method: str  # "text", "vector", or "none"
    description: str


TEST_CASES = [
    # Test Case 1: Substring Match (Product in Mention)
    TestCase(
        name="substring_product_in_mention_1",
        mention="V60 جواتيمالا",
        canonical="V60",
        variants=[],
        vector_score=0.58,
        expected_match=True,
        expected_method="text",
        description="Product name 'V60' is substring of mention 'V60 جواتيمالا'"
    ),
    TestCase(
        name="substring_product_in_mention_2",
        mention="اللاتيه الساخن",
        canonical="لاتيه",
        variants=[],
        vector_score=0.65,
        expected_match=True,
        expected_method="text",
        description="Product 'لاتيه' is substring of 'اللاتيه الساخن'"
    ),
    TestCase(
        name="substring_product_in_mention_3",
        mention="flat white hot",
        canonical="flat white",
        variants=[],
        vector_score=0.70,
        expected_match=True,
        expected_method="text",
        description="Product 'flat white' is substring of mention"
    ),

    # Test Case 2: Reverse Substring (Mention in Product)
    TestCase(
        name="substring_mention_in_product_1",
        mention="v60",
        canonical="V60 كولومبي",
        variants=[],
        vector_score=0.75,
        expected_match=True,
        expected_method="text",
        description="Mention 'v60' is substring of product 'V60 كولومبي'"
    ),
    TestCase(
        name="substring_mention_in_product_2",
        mention="latte",
        canonical="iced latte",
        variants=[],
        vector_score=0.60,
        expected_match=True,
        expected_method="text",
        description="Mention 'latte' is substring of product 'iced latte'"
    ),

    # Test Case 3: Variant Matching
    TestCase(
        name="variant_match_1",
        mention="V60 برازيلي",
        canonical="V60",
        variants=["V60 برازيلي", "V60 كولومبي"],
        vector_score=0.55,
        expected_match=True,
        expected_method="text",
        description="Mention matches variant exactly"
    ),
    TestCase(
        name="variant_match_2",
        mention="iced latte special",
        canonical="latte",
        variants=["hot latte", "iced latte"],
        vector_score=0.50,
        expected_match=True,
        expected_method="text",
        description="Variant 'iced latte' is substring of mention"
    ),

    # Test Case 4: No Text Match - Vector Only
    TestCase(
        name="vector_only_1",
        mention="قهوة مثلجة",
        canonical="iced coffee",
        variants=[],
        vector_score=0.85,
        expected_match=True,
        expected_method="vector",
        description="No text match, but vector score 0.85 >= 0.80"
    ),
    TestCase(
        name="vector_only_2",
        mention="فلات وايت",
        canonical="flat white",
        variants=[],
        vector_score=0.92,
        expected_match=True,
        expected_method="vector",
        description="Arabic transliteration matches via vector"
    ),

    # Test Case 5: No Match At All
    TestCase(
        name="no_match_1",
        mention="كيكة الشوكولاتة",
        canonical="V60",
        variants=["V60 كولومبي"],
        vector_score=0.30,
        expected_match=False,
        expected_method="none",
        description="Chocolate cake has nothing to do with V60 coffee"
    ),
    TestCase(
        name="no_match_2",
        mention="sandwich",
        canonical="latte",
        variants=["iced latte"],
        vector_score=0.45,
        expected_match=False,
        expected_method="none",
        description="Food item doesn't match drink"
    ),

    # Test Case 6: Edge Cases
    TestCase(
        name="edge_exact_match",
        mention="V60",
        canonical="V60",
        variants=[],
        vector_score=1.0,
        expected_match=True,
        expected_method="text",
        description="Exact match"
    ),
    TestCase(
        name="edge_case_insensitive",
        mention="v60",
        canonical="V60",
        variants=[],
        vector_score=0.99,
        expected_match=True,
        expected_method="text",
        description="Case insensitive match"
    ),
    TestCase(
        name="edge_whitespace",
        mention="  V60  ",
        canonical="V60",
        variants=[],
        vector_score=0.99,
        expected_match=True,
        expected_method="text",
        description="Whitespace handling"
    ),
    TestCase(
        name="edge_empty_mention",
        mention="",
        canonical="V60",
        variants=[],
        vector_score=0.0,
        expected_match=False,
        expected_method="none",
        description="Empty mention should not match"
    ),
    TestCase(
        name="edge_empty_product",
        mention="V60",
        canonical="",
        variants=[],
        vector_score=0.0,
        expected_match=False,
        expected_method="none",
        description="Empty product should not match"
    ),

    # Test Case 7: Real-world examples from our data
    TestCase(
        name="real_v60_guatemala",
        mention="V60 جواتيمالا",
        canonical="v60",
        variants=["V60 Qv", "V60 كولومبي", "V60 برازيلية", "V60 سيلفادور"],
        vector_score=0.58,
        expected_match=True,
        expected_method="text",
        description="REAL: V60 Guatemala should match V60 product"
    ),
    TestCase(
        name="real_latte_arabic_misspelling",
        mention="الاتيه",
        canonical="اللاتيه",
        variants=[],
        vector_score=0.75,
        expected_match=False,  # Text won't match - it's a misspelling, needs vector
        expected_method="none",
        description="REAL: Misspelling - text can't match, vector 0.75 < 0.80 threshold"
    ),
    TestCase(
        name="real_latte_arabic_high_vector",
        mention="الاتيه",
        canonical="اللاتيه",
        variants=[],
        vector_score=0.85,  # Higher vector score
        expected_match=True,
        expected_method="vector",
        description="REAL: Misspelling with high vector score - matches via vector"
    ),
]


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_tests() -> Tuple[int, int, List[str]]:
    """
    Run all test cases.

    Returns:
        Tuple of (passed_count, failed_count, failure_messages)
    """
    passed = 0
    failed = 0
    failures = []

    print("=" * 70)
    print("HYBRID TEXT + VECTOR MATCHING TEST SUITE")
    print("=" * 70)
    print()

    for tc in TEST_CASES:
        matched, score, method = hybrid_match(
            tc.mention,
            tc.canonical,
            tc.variants,
            tc.vector_score
        )

        # Check results
        match_ok = matched == tc.expected_match
        method_ok = method == tc.expected_method

        if match_ok and method_ok:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
            failures.append(
                f"{tc.name}: expected ({tc.expected_match}, {tc.expected_method}), "
                f"got ({matched}, {method})"
            )

        # Print result
        print(f"[{status}] {tc.name}")
        print(f"       Mention: '{tc.mention}'")
        print(f"       Product: '{tc.canonical}' + variants: {tc.variants}")
        print(f"       Vector:  {tc.vector_score}")
        print(f"       Result:  match={matched}, score={score:.2f}, method={method}")
        if status == "FAIL":
            print(f"       Expected: match={tc.expected_match}, method={tc.expected_method}")
        print()

    return passed, failed, failures


def test_with_real_db():
    """
    Test against real database data.
    """
    print("=" * 70)
    print("REAL DATABASE TEST")
    print("=" * 70)
    print()

    try:
        from database import get_session, TaxonomyProduct, RawMention

        session = get_session()

        # Get V60 product
        v60_product = session.query(TaxonomyProduct).filter(
            TaxonomyProduct.canonical_text.ilike('%v60%'),
            TaxonomyProduct.display_name == 'V60'
        ).first()

        if not v60_product:
            print("V60 product not found in database")
            return

        print(f"Found V60 Product:")
        print(f"  ID: {v60_product.id}")
        print(f"  Canonical: {v60_product.canonical_text}")
        print(f"  Variants: {v60_product.variants}")
        print()

        # Get orphan mentions that contain "v60" or "V60"
        orphans = session.query(RawMention).filter(
            RawMention.discovered_product_id.is_(None),
            RawMention.mention_text.ilike('%v60%')
        ).all()

        print(f"Found {len(orphans)} V60-related orphan mentions:")
        print()

        for orphan in orphans:
            # Test our hybrid matching
            matched, score, method = hybrid_match(
                orphan.mention_text,
                v60_product.canonical_text,
                v60_product.variants or [],
                0.58  # Simulated vector score
            )

            print(f"  Mention: '{orphan.mention_text}'")
            print(f"  Hybrid Match: {matched}, score={score:.2f}, method={method}")
            print()

        session.close()

    except Exception as e:
        print(f"Database test failed: {e}")
        import traceback
        traceback.print_exc()


def analyze_orphans():
    """
    Analyze all orphan mentions and see how many would be rescued by text matching.
    """
    print("=" * 70)
    print("ORPHAN ANALYSIS")
    print("=" * 70)
    print()

    try:
        from database import get_session, TaxonomyProduct, RawMention

        session = get_session()

        # Get all products
        products = session.query(TaxonomyProduct).filter(
            TaxonomyProduct.taxonomy_id == 'a56441c9-e1b6-4cf6-85b5-ead7ea9397b8'
        ).all()

        print(f"Found {len(products)} products in taxonomy")

        # Get all orphan mentions (no discovered_product_id)
        orphans = session.query(RawMention).filter(
            RawMention.discovered_product_id.is_(None),
            RawMention.mention_type == 'product'
        ).all()

        print(f"Found {len(orphans)} product orphan mentions")
        print()

        # Test each orphan against all products
        rescued = 0
        rescued_mentions = []

        for orphan in orphans:
            for product in products:
                if text_matches_product(
                    orphan.mention_text,
                    product.canonical_text,
                    product.variants or []
                ):
                    rescued += 1
                    rescued_mentions.append({
                        'mention': orphan.mention_text,
                        'product': product.display_name,
                        'canonical': product.canonical_text
                    })
                    break  # Only count once per orphan

        print(f"Text matching would rescue {rescued}/{len(orphans)} orphans ({100*rescued/max(len(orphans),1):.1f}%)")
        print()

        if rescued_mentions:
            print("Rescued mentions:")
            for r in rescued_mentions[:20]:  # Show first 20
                print(f"  '{r['mention']}' → '{r['product']}' (canonical: '{r['canonical']}')")

        session.close()

    except Exception as e:
        print(f"Orphan analysis failed: {e}")
        import traceback
        traceback.print_exc()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Run unit tests
    passed, failed, failures = run_tests()

    print("=" * 70)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("=" * 70)

    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")

    print()

    # Run real database tests if --db flag
    if "--db" in sys.argv:
        test_with_real_db()
        print()
        analyze_orphans()
    else:
        print("Run with --db flag to test against real database")

    # Exit with error code if tests failed
    sys.exit(1 if failed > 0 else 0)
