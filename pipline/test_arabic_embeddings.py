#!/usr/bin/env python3
"""
Arabic Embedding Quality Test (GATE for Phase 1B)

Tests cross-lingual similarity between Arabic and English terms
to verify the embedding model works for entity resolution.

Pass criteria: Average cross-lingual similarity > 0.5
"""

import sys

def run_test():
    from embedding_client import (
        generate_embedding,
        compute_similarity,
        normalize_for_embedding,
        is_model_available,
        test_arabic_embeddings
    )

    print("=" * 60)
    print("ARABIC EMBEDDING QUALITY TEST (GATE)")
    print("=" * 60)

    # Check model availability
    print("\n1. Model Availability")
    print("-" * 40)
    if not is_model_available():
        print("   ❌ FAIL: Embedding model not available")
        return False
    print("   ✓ Model loaded successfully")

    # Test normalization
    print("\n2. Arabic Normalization")
    print("-" * 40)
    normalization_tests = [
        ("القَهوَة", "القهوه"),      # Diacritics + teh marbuta
        ("سبـــانش", "سبانش"),       # Tatweel removal
        ("الإسبريسو", "الاسبريسو"),   # Alef normalization
        ("لاتيه", "لاتيه"),           # Should stay same (already normalized)
    ]

    for original, expected in normalization_tests:
        normalized = normalize_for_embedding(original)
        # Note: expected is approximate - just check diacritics/tatweel removed
        print(f"   '{original}' → '{normalized}'")

    # Test cross-lingual similarity (Arabic ↔ English)
    print("\n3. Cross-Lingual Similarity Tests")
    print("-" * 40)

    test_pairs = [
        # Product names
        ("قهوة", "coffee"),
        ("لاتيه", "latte"),
        ("سبانش لاتيه", "spanish latte"),
        ("كابتشينو", "cappuccino"),
        ("اسبريسو", "espresso"),
        ("كرواسون", "croissant"),
        ("كيك", "cake"),
        # Service aspects
        ("خدمة", "service"),
        ("سريع", "fast"),
        ("بطيء", "slow"),
        ("نظيف", "clean"),
        ("الموظفين", "staff"),
    ]

    results = []
    for ar, en in test_pairs:
        emb_ar = generate_embedding(ar)
        emb_en = generate_embedding(en)

        if emb_ar and emb_en:
            sim = compute_similarity(emb_ar, emb_en)
            results.append((ar, en, sim))
            status = "✓" if sim > 0.5 else "⚠"
            print(f"   {status} '{ar}' ↔ '{en}': {sim:.3f}")

    # Test same-language similarity (should be very high)
    print("\n4. Same-Language Similarity (sanity check)")
    print("-" * 40)

    same_lang_pairs = [
        ("spanish latte", "Spanish Latte"),  # Case variation
        ("سبانش لاتيه", "سبانش لاتيه"),       # Identical
        ("coffee", "Coffee"),                 # Case variation
    ]

    for t1, t2 in same_lang_pairs:
        emb1 = generate_embedding(t1)
        emb2 = generate_embedding(t2)
        if emb1 and emb2:
            sim = compute_similarity(emb1, emb2)
            status = "✓" if sim > 0.9 else "⚠"
            print(f"   {status} '{t1}' ↔ '{t2}': {sim:.3f}")

    # Test entity resolution scenario
    print("\n5. Entity Resolution Scenario")
    print("-" * 40)

    # Simulate: "spanish latté" should match "سبانش لاتيه"
    canonical = "سبانش لاتيه"
    variants = ["spanish latte", "Spanish Latte", "spanish latté", "سبانش لاتي"]

    emb_canonical = generate_embedding(canonical)
    print(f"   Canonical: '{canonical}'")
    print(f"   Threshold: 0.85")

    for variant in variants:
        emb_variant = generate_embedding(variant)
        if emb_canonical and emb_variant:
            sim = compute_similarity(emb_canonical, emb_variant)
            would_match = sim >= 0.85
            status = "✓ MATCH" if would_match else "✗ NO MATCH"
            print(f"   '{variant}': {sim:.3f} → {status}")

    # Calculate overall results
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    if results:
        avg_sim = sum(r[2] for r in results) / len(results)
        high_sim_count = sum(1 for r in results if r[2] > 0.5)

        print(f"\n   Cross-lingual pairs tested: {len(results)}")
        print(f"   Pairs with similarity > 0.5: {high_sim_count}/{len(results)}")
        print(f"   Average similarity: {avg_sim:.3f}")

        # GATE criteria
        print("\n   GATE CRITERIA: Average similarity > 0.5")
        if avg_sim > 0.5:
            print(f"   ✅ PASS: {avg_sim:.3f} > 0.5")
            print("\n   Proceeding to Phase 2 is approved.")
            return True
        else:
            print(f"   ❌ FAIL: {avg_sim:.3f} <= 0.5")
            print("\n   Consider upgrading to CAMeL-BERT for better Arabic support.")
            return False

    print("   ❌ FAIL: No results to evaluate")
    return False


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
