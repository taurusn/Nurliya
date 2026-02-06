"""
Anchor Management for the Hybrid Discovery Engine.

This module implements the "Learn, Discover" architecture:
- Layer 1 (Learned): Anchors learned from approved taxonomies or OS imports
- Layer 2 (Discovery): HDBSCAN clustering for unknown items

The anchor system provides category definitions that guide clustering,
ensuring consistent taxonomy structure across places of the same business type.

Anchor embeddings are stored in PostgreSQL (JSONB) alongside metadata,
not in Qdrant. This is intentional: anchors are a small, derived dataset
(dozens per business type) used for in-memory cosine similarity classification.
Qdrant stores primary data (MENTIONS_COLLECTION, PRODUCTS_COLLECTION).
"""

import uuid
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_
from database import (
    SessionLocal, CategoryAnchor, AnchorExample,
    PlaceTaxonomy, TaxonomyCategory, TaxonomyProduct, RawMention
)
import embedding_client
from logging_config import get_logger

logger = get_logger(__name__, service="anchor_manager")

# Thresholds for anchor matching
# All embeddings are 384-dim (paraphrase-multilingual-MiniLM-L12-v2)
LEARNED_MATCH_THRESHOLD = 0.80   # Learned from approved taxonomies
IMPORT_MATCH_THRESHOLD = 0.70    # OS-imported anchors (relaxed for Arabic/multilingual)
DEFAULT_MATCH_THRESHOLD = 0.85

# Learning weights
CORRECTION_WEIGHT = 2.0  # Human corrections count 2x vs auto-discovered mentions


@dataclass
class AnchorMatch:
    """Result of anchor classification."""
    anchor_id: str
    anchor_name: str
    category_name: str
    display_name_en: str
    display_name_ar: str
    is_aspect: bool
    confidence: float
    source: str  # 'learned' or 'import'


def load_anchors_for_business(business_type: str) -> List[Dict]:
    """
    Load all anchors (learned + imported) for a business type.

    Anchors are stored in PostgreSQL with centroid embeddings as JSONB.
    Each centroid is a 384-dim vector (MiniLM-L12-v2), compatible with
    the vectors stored in Qdrant's MENTIONS_COLLECTION.

    Args:
        business_type: Business type identifier (e.g., 'coffee_shop')

    Returns:
        List of anchor dictionaries with centroid embeddings
    """
    session = SessionLocal()
    try:
        anchors = session.query(CategoryAnchor).filter_by(
            business_type=business_type
        ).all()

        result = []
        for anchor in anchors:
            if anchor.centroid_embedding:
                result.append({
                    "id": str(anchor.id),
                    "category_name": anchor.category_name,
                    "display_name_en": anchor.display_name_en,
                    "display_name_ar": anchor.display_name_ar,
                    "is_aspect": anchor.is_aspect,
                    "centroid_embedding": anchor.centroid_embedding,
                    "source": anchor.source,
                    "example_count": anchor.example_count,
                    "match_count": anchor.match_count,
                })

        logger.info(f"Loaded {len(result)} anchors for {business_type}",
                   extra={"extra_data": {"business_type": business_type}})
        return result

    finally:
        session.close()


def classify_to_anchor(
    embedding: List[float],
    anchors: List[Dict],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> Optional[AnchorMatch]:
    """
    Classify a mention embedding to the nearest anchor if above threshold.

    Uses cosine similarity to find the best matching anchor.
    Applies source-specific thresholds (learned=0.88, import=0.85).

    Args:
        embedding: 384-dim embedding vector (MiniLM-L12-v2)
        anchors: List of anchor dictionaries from load_anchors_for_business
        threshold: Minimum similarity threshold for a match

    Returns:
        AnchorMatch if found, None otherwise
    """
    if not anchors or not embedding:
        return None

    query_vec = np.array(embedding)
    query_norm = np.linalg.norm(query_vec)

    if query_norm == 0:
        return None

    query_vec = query_vec / query_norm

    best_match = None
    best_score = threshold  # Only consider matches above threshold

    for anchor in anchors:
        centroid = np.array(anchor["centroid_embedding"])
        centroid_norm = np.linalg.norm(centroid)

        if centroid_norm == 0:
            continue

        centroid = centroid / centroid_norm

        # Cosine similarity
        score = float(np.dot(query_vec, centroid))

        # Apply source-specific threshold
        source = anchor.get("source", "learned")
        if source == "import":
            anchor_threshold = IMPORT_MATCH_THRESHOLD
        else:
            anchor_threshold = LEARNED_MATCH_THRESHOLD

        if score < anchor_threshold:
            continue

        # Update best match (highest score wins)
        if score > best_score:
            best_score = score
            best_match = anchor

    if best_match:
        return AnchorMatch(
            anchor_id=best_match["id"],
            anchor_name=best_match["category_name"],
            category_name=best_match["category_name"],
            display_name_en=best_match["display_name_en"],
            display_name_ar=best_match["display_name_ar"],
            is_aspect=best_match["is_aspect"],
            confidence=best_score,
            source=best_match.get("source", "learned"),
        )

    return None


def update_anchor_stats(anchor_id: str, confidence: float):
    """
    Update anchor statistics when a mention is matched.

    Args:
        anchor_id: UUID of the anchor
        confidence: Match confidence score
    """
    session = SessionLocal()
    try:
        anchor = session.query(CategoryAnchor).filter_by(id=anchor_id).first()
        if anchor:
            # Increment match count
            anchor.match_count = (anchor.match_count or 0) + 1

            # Update average confidence (running average)
            old_avg = float(anchor.avg_confidence or 0)
            old_count = anchor.match_count - 1
            if old_count > 0:
                new_avg = (old_avg * old_count + confidence) / anchor.match_count
            else:
                new_avg = confidence
            anchor.avg_confidence = round(new_avg, 3)

            anchor.updated_at = datetime.utcnow()
            session.commit()

    except Exception as e:
        logger.error(f"Failed to update anchor stats: {e}")
        session.rollback()
    finally:
        session.close()


def learn_from_approved_taxonomy(taxonomy_id: str) -> int:
    """
    Extract new anchors/examples from an approved taxonomy.

    Called when a taxonomy is published/approved. Extracts categories
    and their mentions as learned examples for future places.

    Args:
        taxonomy_id: UUID of the approved taxonomy

    Returns:
        Number of new examples learned
    """
    session = SessionLocal()
    learned_count = 0

    try:
        taxonomy = session.query(PlaceTaxonomy).filter_by(id=taxonomy_id).first()
        if not taxonomy:
            logger.warning(f"Taxonomy not found: {taxonomy_id}")
            return 0

        # Get business type from place
        business_type = taxonomy.place.category if taxonomy.place else "coffee_shop"

        # Process each approved category
        for category in taxonomy.categories:
            if not category.is_approved:
                continue

            # Get all mentions in this category (check both discovered and resolved)
            mentions = session.query(RawMention).filter(
                or_(
                    RawMention.discovered_category_id == category.id,
                    RawMention.resolved_category_id == category.id,
                )
            ).all()

            # For product categories, also collect product names/variants
            product_texts = []
            if category.has_products:
                products = session.query(TaxonomyProduct).filter_by(
                    assigned_category_id=category.id,
                    is_approved=True,
                ).all()
                for product in products:
                    if product.canonical_text:
                        product_texts.append(product.canonical_text)
                    if product.variants:
                        product_texts.extend(product.variants)

            if not mentions and not product_texts:
                continue

            # Find or create anchor
            existing_anchor = session.query(CategoryAnchor).filter_by(
                business_type=business_type,
                category_name=category.name
            ).first()

            if existing_anchor:
                # Add new examples to existing anchor
                for mention in mentions:
                    if not mention.qdrant_point_id:
                        continue

                    # Check if example already exists
                    existing_example = session.query(AnchorExample).filter_by(
                        anchor_id=existing_anchor.id,
                        text=mention.mention_text
                    ).first()

                    if not existing_example:
                        # Generate embedding for this text
                        embeddings = embedding_client.generate_embeddings([mention.mention_text])
                        if embeddings and embeddings[0]:
                            example = AnchorExample(
                                anchor_id=existing_anchor.id,
                                text=mention.mention_text,
                                embedding=embeddings[0],
                                source="learned",
                                source_taxonomy_id=uuid.UUID(taxonomy_id),
                                mention_count=1,
                            )
                            session.add(example)
                            learned_count += 1

                # Add product texts as examples for product categories
                for ptext in product_texts:
                    existing_example = session.query(AnchorExample).filter_by(
                        anchor_id=existing_anchor.id,
                        text=ptext
                    ).first()
                    if not existing_example:
                        embeddings = embedding_client.generate_embeddings([ptext])
                        if embeddings and embeddings[0]:
                            example = AnchorExample(
                                anchor_id=existing_anchor.id,
                                text=ptext,
                                embedding=embeddings[0],
                                source="learned",
                                source_taxonomy_id=uuid.UUID(taxonomy_id),
                                mention_count=1,
                            )
                            session.add(example)
                            learned_count += 1

                # Recompute centroid
                _recompute_anchor_centroid(session, existing_anchor)

            else:
                # Create new learned anchor
                anchor = None
                if mentions:
                    anchor = _create_anchor_from_category(
                        session=session,
                        business_type=business_type,
                        category=category,
                        mentions=mentions,
                        taxonomy_id=taxonomy_id,
                        source="learned"
                    )
                    if anchor:
                        learned_count += len(mentions)

                # If no anchor yet (no mentions or embedding failed), create from product texts
                if not anchor and product_texts:
                    prod_embeddings = embedding_client.generate_embeddings(product_texts)
                    if prod_embeddings:
                        valid_pairs = [(t, e) for t, e in zip(product_texts, prod_embeddings) if e]
                        if valid_pairs:
                            centroid = np.mean([e for _, e in valid_pairs], axis=0).tolist()
                            anchor = CategoryAnchor(
                                business_type=business_type,
                                category_name=category.name,
                                display_name_en=category.display_name_en,
                                display_name_ar=category.display_name_ar,
                                is_aspect=not category.has_products,
                                centroid_embedding=centroid,
                                sample_terms=[t for t, _ in valid_pairs[:10]],
                                source="learned",
                                example_count=len(valid_pairs),
                                match_count=0,
                            )
                            session.add(anchor)
                            session.flush()
                            for ptext, pemb in valid_pairs:
                                example = AnchorExample(
                                    anchor_id=anchor.id,
                                    text=ptext,
                                    embedding=pemb,
                                    source="learned",
                                    source_taxonomy_id=uuid.UUID(taxonomy_id) if taxonomy_id else None,
                                    mention_count=1,
                                )
                                session.add(example)
                                learned_count += 1

                # Add product texts as additional examples to mention-based anchor
                elif anchor and product_texts:
                    prod_embeddings = embedding_client.generate_embeddings(product_texts)
                    if prod_embeddings:
                        for ptext, pemb in zip(product_texts, prod_embeddings):
                            if pemb:
                                example = AnchorExample(
                                    anchor_id=anchor.id,
                                    text=ptext,
                                    embedding=pemb,
                                    source="learned",
                                    source_taxonomy_id=uuid.UUID(taxonomy_id) if taxonomy_id else None,
                                    mention_count=1,
                                )
                                session.add(example)
                                learned_count += 1
                        _recompute_anchor_centroid(session, anchor)

        session.commit()
        logger.info(f"Learned {learned_count} examples from taxonomy {taxonomy_id}")
        return learned_count

    except Exception as e:
        logger.error(f"Failed to learn from taxonomy: {e}", exc_info=True)
        session.rollback()
        return 0
    finally:
        session.close()


def generate_anchors_from_import(import_categories: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Convert imported JSON categories into anchor-format dicts for clustering.

    For ASPECT categories: Creates one anchor per category (centroid of all examples).
    For PRODUCT categories: Creates one anchor per PRODUCT (centroid of product variants).

    This product-level granularity prevents centroid dilution when a category has
    many diverse products (e.g., espresso_drinks with Latte, Cappuccino, Americano).
    Each product anchor still carries the parent category name for category creation.

    Args:
        import_categories: List of category dicts from the import request, each with:
            - name: str (internal category name)
            - display_name_en: str
            - display_name_ar: str
            - is_aspect: bool
            - parent: str (optional, parent category name for hierarchy)
            - examples: List[str] (example texts for aspect categories)
            - products: List[dict] (for product categories, each with name, variants)

    Returns:
        Tuple of:
        - List of anchor dicts compatible with classify_mentions_to_anchors()
        - Dict of category hierarchy info: {cat_name: {parent, display_name_en, display_name_ar, is_aspect}}
    """
    anchors = []
    hierarchy_info = {}  # cat_name -> {parent, display_names, is_aspect}

    for cat in import_categories:
        is_aspect = cat.get("is_aspect", True)
        cat_name = cat.get("name", "")
        parent_name = cat.get("parent")  # Optional parent category

        # Store hierarchy info for all categories
        hierarchy_info[cat_name] = {
            "parent": parent_name,
            "display_name_en": cat.get("display_name_en", ""),
            "display_name_ar": cat.get("display_name_ar", ""),
            "is_aspect": is_aspect,
            "has_products": not is_aspect,
        }

        if is_aspect:
            # ASPECT CATEGORIES: One anchor per category
            texts = cat.get("examples", [])
            if not texts:
                logger.warning(f"Import aspect category '{cat_name}' has no examples, skipping")
                continue

            embeddings = embedding_client.generate_embeddings(texts)
            if not embeddings:
                continue

            valid_embeddings = [emb for emb in embeddings if emb]
            if not valid_embeddings:
                continue

            centroid = np.mean(valid_embeddings, axis=0).tolist()
            anchors.append({
                "id": str(uuid.uuid4()),
                "category_name": cat_name,
                "parent_name": parent_name,
                "display_name_en": cat.get("display_name_en", ""),
                "display_name_ar": cat.get("display_name_ar", ""),
                "is_aspect": True,
                "centroid_embedding": centroid,
                "source": "import",
                "example_count": len(valid_embeddings),
                "match_count": 0,
            })
        else:
            # PRODUCT CATEGORIES: One anchor per product
            products = cat.get("products", [])
            if not products:
                logger.warning(f"Import product category '{cat_name}' has no products, skipping")
                continue

            for product in products:
                # Collect texts for this product: variants only (skip English name)
                # Use ONLY non-ASCII variants for centroid to avoid language mixing
                # English and Arabic embeddings are very different in multilingual models
                product_name = product.get("name", "")
                display_name = product.get("display_name", product_name)
                variants = product.get("variants", [])

                # Filter to non-ASCII variants (Arabic text)
                # ASCII check: if any char is A-Za-z, it's English
                def is_arabic(text: str) -> bool:
                    return not any(c.isascii() and c.isalpha() for c in text)

                arabic_variants = [v for v in variants if is_arabic(v)]

                # Fallback: if no Arabic variants, use all variants
                texts = arabic_variants if arabic_variants else variants
                if not texts:
                    # Last resort: use display_name (Arabic) or product name
                    texts = [display_name] if display_name else [product_name] if product_name else []

                if not texts:
                    continue

                embeddings = embedding_client.generate_embeddings(texts)
                if not embeddings:
                    continue

                valid_embeddings = [emb for emb in embeddings if emb]
                if not valid_embeddings:
                    continue

                # Centroid from Arabic variants only (avoids language mixing)
                centroid = np.mean(valid_embeddings, axis=0).tolist()

                anchors.append({
                    "id": str(uuid.uuid4()),
                    "category_name": cat_name,  # Category name
                    "parent_name": parent_name,  # Parent category (for hierarchy)
                    "product_name": product_name,  # Specific product
                    "display_name_en": cat.get("display_name_en", ""),
                    "display_name_ar": cat.get("display_name_ar", ""),
                    "product_display_name": display_name,  # Product display name
                    "is_aspect": False,
                    "centroid_embedding": centroid,
                    "source": "import",
                    "example_count": len(valid_embeddings),
                    "match_count": 0,
                })

    logger.info(f"Generated {len(anchors)} anchors from import data "
                f"({sum(1 for a in anchors if a.get('is_aspect'))} aspects, "
                f"{sum(1 for a in anchors if not a.get('is_aspect'))} products)")
    return anchors, hierarchy_info


def create_seed_anchors(business_type: str, seeds: List[Dict]) -> int:
    """
    Initialize seed anchors for a business type (cold start).

    Creates anchors from seed definitions, generating embeddings
    for all example terms.

    Args:
        business_type: Business type identifier
        seeds: List of seed definitions from seeds/*.py

    Returns:
        Number of anchors created
    """
    session = SessionLocal()
    created_count = 0

    try:
        for seed in seeds:
            # Check if anchor already exists
            existing = session.query(CategoryAnchor).filter_by(
                business_type=business_type,
                category_name=seed["category"]
            ).first()

            if existing:
                logger.debug(f"Anchor already exists: {seed['category']}")
                continue

            # Generate embeddings for all examples
            examples = seed.get("examples", [])
            if not examples:
                logger.warning(f"No examples for seed: {seed['category']}")
                continue

            embeddings = embedding_client.generate_embeddings(examples)
            if not embeddings:
                logger.error(f"Failed to generate embeddings for: {seed['category']}")
                continue

            # Filter out None embeddings
            valid_pairs = [(text, emb) for text, emb in zip(examples, embeddings) if emb]
            if not valid_pairs:
                continue

            # Compute centroid
            valid_embeddings = [emb for _, emb in valid_pairs]
            centroid = np.mean(valid_embeddings, axis=0).tolist()

            # Create anchor
            anchor = CategoryAnchor(
                business_type=business_type,
                category_name=seed["category"],
                display_name_en=seed.get("display_name_en"),
                display_name_ar=seed.get("display_name_ar"),
                is_aspect=seed.get("is_aspect", True),
                centroid_embedding=centroid,
                sample_terms=examples[:10],  # Store top 10 as reference
                source="seed",
                example_count=len(valid_pairs),
                match_count=0,
            )
            session.add(anchor)
            session.flush()  # Get the ID

            # Create examples
            for text, emb in valid_pairs:
                example = AnchorExample(
                    anchor_id=anchor.id,
                    text=text,
                    embedding=emb,
                    source="seed",
                    mention_count=1,
                )
                session.add(example)

            created_count += 1
            logger.info(f"Created seed anchor: {seed['category']} ({len(valid_pairs)} examples)")

        session.commit()
        logger.info(f"Created {created_count} seed anchors for {business_type}")
        return created_count

    except Exception as e:
        logger.error(f"Failed to create seed anchors: {e}", exc_info=True)
        session.rollback()
        return 0
    finally:
        session.close()


def get_anchor_stats(business_type: str) -> Dict:
    """
    Get statistics about anchors for a business type.

    Returns:
        Dictionary with anchor statistics
    """
    session = SessionLocal()
    try:
        anchors = session.query(CategoryAnchor).filter_by(
            business_type=business_type
        ).all()

        total_anchors = len(anchors)
        seed_anchors = sum(1 for a in anchors if a.source == "seed")
        learned_anchors = sum(1 for a in anchors if a.source == "learned")
        total_examples = sum(a.example_count or 0 for a in anchors)
        total_matches = sum(a.match_count or 0 for a in anchors)

        aspect_anchors = [a for a in anchors if a.is_aspect]
        product_anchors = [a for a in anchors if not a.is_aspect]

        return {
            "business_type": business_type,
            "total_anchors": total_anchors,
            "seed_anchors": seed_anchors,
            "learned_anchors": learned_anchors,
            "aspect_anchors": len(aspect_anchors),
            "product_category_anchors": len(product_anchors),
            "total_examples": total_examples,
            "total_matches": total_matches,
            "anchors": [
                {
                    "name": a.category_name,
                    "display_name": a.display_name_en,
                    "is_aspect": a.is_aspect,
                    "source": a.source,
                    "examples": a.example_count or 0,
                    "matches": a.match_count or 0,
                    "avg_confidence": float(a.avg_confidence) if a.avg_confidence else None,
                }
                for a in anchors
            ]
        }

    finally:
        session.close()


def _recompute_anchor_centroid(session, anchor: CategoryAnchor):
    """Recompute centroid from all examples."""
    examples = session.query(AnchorExample).filter_by(anchor_id=anchor.id).all()

    if not examples:
        return

    embeddings = [ex.embedding for ex in examples if ex.embedding]
    if not embeddings:
        return

    centroid = np.mean(embeddings, axis=0).tolist()
    anchor.centroid_embedding = centroid
    anchor.example_count = len(examples)
    anchor.updated_at = datetime.utcnow()


def _recompute_anchor_centroid_weighted(session, anchor: CategoryAnchor):
    """
    Recompute anchor centroid with higher weight for corrections.

    Corrections (source='correction') count 2x more than other examples,
    reflecting that human corrections are more reliable than auto-discovery.
    """
    examples = session.query(AnchorExample).filter_by(anchor_id=anchor.id).all()

    if not examples:
        return

    weighted_embeddings = []
    for ex in examples:
        if ex.embedding:
            weight = CORRECTION_WEIGHT if ex.source == 'correction' else 1.0
            # Add embedding weighted times (integer approximation)
            for _ in range(int(weight)):
                weighted_embeddings.append(ex.embedding)

    if not weighted_embeddings:
        return

    centroid = np.mean(weighted_embeddings, axis=0).tolist()
    anchor.centroid_embedding = centroid
    anchor.example_count = len(examples)
    anchor.updated_at = datetime.utcnow()


def learn_from_corrections(
    session,
    mention_ids: List,
    target_type: str,
    target_id,
    taxonomy,
) -> int:
    """
    Learn from user corrections by adding mention texts as anchor examples.

    This enables immediate anchor improvement without waiting for publish.
    Called from bulk_move_mentions endpoint.

    Args:
        session: Database session
        mention_ids: List of RawMention UUIDs that were moved
        target_type: 'product' or 'category'
        target_id: UUID of target product or category
        taxonomy: PlaceTaxonomy object

    Returns:
        Number of new examples added
    """
    from database import TaxonomyProduct, TaxonomyCategory, RawMention, CategoryAnchor, AnchorExample

    # Get the target category
    if target_type == 'product':
        target = session.query(TaxonomyProduct).filter_by(id=target_id).first()
        if not target or not target.assigned_category_id:
            return 0
        category = session.query(TaxonomyCategory).filter_by(id=target.assigned_category_id).first()
    else:
        category = session.query(TaxonomyCategory).filter_by(id=target_id).first()

    if not category:
        return 0

    # Determine business_type from place
    place = taxonomy.place
    business_type = place.category if place and place.category else 'general'

    # Find existing anchor for this category
    anchor = session.query(CategoryAnchor).filter_by(
        business_type=business_type,
        category_name=category.name,
    ).first()

    # If no anchor exists, create one
    if not anchor:
        anchor = CategoryAnchor(
            business_type=business_type,
            category_name=category.name,
            display_name_en=category.display_name_en or category.name,
            display_name_ar=category.display_name_ar,
            is_aspect=not category.has_products,
            source='correction',
            example_count=0,
            match_count=0,
        )
        session.add(anchor)
        session.flush()  # Get the anchor ID

    # Get mention texts
    mentions = session.query(RawMention).filter(RawMention.id.in_(mention_ids)).all()

    # Collect unique texts
    unique_texts = list(set(m.mention_text for m in mentions if m.mention_text))
    if not unique_texts:
        return 0

    # Generate embeddings for all texts
    embeddings = embedding_client.generate_embeddings(unique_texts)
    if not embeddings:
        return 0

    # Add as examples
    new_count = 0
    for text, embedding in zip(unique_texts, embeddings):
        if not embedding:
            continue

        # Check for existing example
        existing = session.query(AnchorExample).filter_by(
            anchor_id=anchor.id,
            text=text,
        ).first()

        if existing:
            # Update existing - increment count and mark as correction
            existing.mention_count = (existing.mention_count or 0) + 1
            if existing.source != 'correction':
                existing.source = 'correction'  # Upgrade source
        else:
            # Create new example
            example = AnchorExample(
                anchor_id=anchor.id,
                text=text,
                embedding=embedding,
                source='correction',
                source_taxonomy_id=taxonomy.id,
                mention_count=1,
            )
            session.add(example)
            new_count += 1

    # Recompute centroid with correction weighting
    if new_count > 0:
        _recompute_anchor_centroid_weighted(session, anchor)

    logger.info(
        f"Learned from corrections: {new_count} new examples added to anchor '{anchor.category_name}'",
        extra={"data": {
            "anchor_id": str(anchor.id),
            "category_name": anchor.category_name,
            "business_type": business_type,
            "new_examples": new_count,
            "total_mentions": len(mentions),
        }}
    )

    return new_count


def _create_anchor_from_category(
    session,
    business_type: str,
    category: TaxonomyCategory,
    mentions: List[RawMention],
    taxonomy_id: str,
    source: str = "learned"
) -> Optional[CategoryAnchor]:
    """Create a new anchor from a taxonomy category and its mentions."""

    # Get embeddings for mentions
    texts = [m.mention_text for m in mentions if m.mention_text][:50]  # Limit to 50
    if not texts:
        return None

    embeddings = embedding_client.generate_embeddings(texts)
    if not embeddings:
        return None

    valid_pairs = [(text, emb) for text, emb in zip(texts, embeddings) if emb]
    if not valid_pairs:
        return None

    # Compute centroid
    valid_embeddings = [emb for _, emb in valid_pairs]
    centroid = np.mean(valid_embeddings, axis=0).tolist()

    # Create anchor
    anchor = CategoryAnchor(
        business_type=business_type,
        category_name=category.name,
        display_name_en=category.display_name_en,
        display_name_ar=category.display_name_ar,
        is_aspect=not category.has_products,
        centroid_embedding=centroid,
        sample_terms=[t for t, _ in valid_pairs[:10]],
        source=source,
        example_count=len(valid_pairs),
        match_count=0,
    )
    session.add(anchor)
    session.flush()

    # Create examples
    for text, emb in valid_pairs:
        example = AnchorExample(
            anchor_id=anchor.id,
            text=text,
            embedding=emb,
            source=source,
            source_taxonomy_id=uuid.UUID(taxonomy_id) if taxonomy_id else None,
            mention_count=1,
        )
        session.add(example)

    return anchor


# Convenience functions for clustering integration
def classify_mentions_to_anchors(
    items: List[Dict],
    business_type: str,
    anchors: Optional[List[Dict]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Classify a list of mention items to anchors.

    Separates items into those matched to anchors and those that need clustering.
    Anchor centroids (384-dim, stored in PostgreSQL JSONB) are compared against
    mention embeddings via cosine similarity.

    Args:
        items: List of ClusterItem-like dicts with 'embedding', 'text', 'mention_type'
        business_type: Business type for anchor lookup
        anchors: Pre-loaded anchors (skip DB load). Used when merging
                 learned anchors with import anchors for re-clustering.

    Returns:
        Tuple of (matched_items, unmatched_items)
    """
    if anchors is None:
        anchors = load_anchors_for_business(business_type)

    if not anchors:
        logger.info("No anchors found, all items will go to discovery")
        return [], items

    matched = []
    unmatched = []

    for item in items:
        embedding = item.get("embedding")
        if not embedding:
            unmatched.append(item)
            continue

        match = classify_to_anchor(embedding, anchors)

        if match:
            # Item matched to anchor
            item["anchor_match"] = match
            item["anchor_id"] = match.anchor_id
            item["anchor_category"] = match.category_name
            matched.append(item)

            # Update stats
            update_anchor_stats(match.anchor_id, match.confidence)
        else:
            unmatched.append(item)

    logger.info(f"Anchor classification: {len(matched)} matched, {len(unmatched)} to discovery",
               extra={"extra_data": {"business_type": business_type}})

    return matched, unmatched
