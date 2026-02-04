"""
HDBSCAN clustering job for taxonomy discovery.
Clusters mention embeddings and generates category hierarchy for human review.
"""

import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict

import numpy as np

from logging_config import get_logger
from config import VLLM_MODEL
from sqlalchemy import or_
from database import (
    PlaceTaxonomy, TaxonomyCategory, TaxonomyProduct, RawMention,
    Job, Place, ScrapeJob, get_session,
)
import vector_store
from vector_store import MENTIONS_COLLECTION, VectorPayload

logger = get_logger(__name__, service="clustering")

# HDBSCAN configuration
HDBSCAN_CONFIG = {
    "min_cluster_size": 3,      # Minimum mentions for a cluster
    "min_samples": 2,           # Controls noise sensitivity
    "metric": "euclidean",      # Works with normalized embeddings
    "cluster_selection_method": "eom",  # Excess of Mass
}

# Thresholds
MIN_MENTIONS_FOR_CLUSTERING = 10
REDISCOVERY_THRESHOLD = 50  # New mentions needed to trigger re-discovery
SUPER_CATEGORY_SIMILARITY_THRESHOLD = 0.55  # For grouping sub-categories (lowered from 0.7)
PRODUCT_SIMILARITY_THRESHOLD = 0.78  # For grouping product variants within a cluster
TEXT_MATCH_MIN_LENGTH = 3  # Minimum chars for text matching to avoid false positives


def _text_matches_product(mention_text: str, canonical_text: str, min_length: int = TEXT_MATCH_MIN_LENGTH) -> bool:
    """
    Check if mention contains product name or vice versa.

    Used to rescue orphan mentions that vectors missed but clearly match.
    E.g., "V60 جواتيمالا" contains "v60" → should match V60 product.

    Args:
        mention_text: The mention text to check
        canonical_text: Product's canonical text
        min_length: Minimum characters for match (avoids "بن" matching "بنانا")

    Returns:
        True if text match found
    """
    if not mention_text or not canonical_text:
        return False
    mention = mention_text.lower().strip()
    canonical = canonical_text.lower().strip()
    if len(canonical) >= min_length and canonical in mention:
        return True
    if len(mention) >= min_length and mention in canonical:
        return True
    return False


@dataclass
class ClusterItem:
    """Item within a cluster."""
    vector_id: str
    text: str
    embedding: List[float]
    mention_type: str
    sentiment_sum: float
    mention_count: int
    cluster_id: int = -1
    confidence: float = 0.0


def deduplicate_cluster_items(
    items: List[ClusterItem],
    similarity_threshold: float = PRODUCT_SIMILARITY_THRESHOLD
) -> List[Dict]:
    """
    Sub-cluster items within an HDBSCAN cluster to identify distinct products.

    Uses DBSCAN with cosine similarity on embeddings to group same-language
    variants (Arabic-Arabic, English-English work well at 0.78+ threshold).

    Args:
        items: List of ClusterItem objects from one HDBSCAN cluster
        similarity_threshold: Minimum cosine similarity to group items (default 0.78)

    Returns:
        List of product dictionaries with:
        - canonical_text: Most frequent mention text (lowercase)
        - display_name: Original casing of canonical text
        - variants: List of other text variations
        - total_mentions: Sum of mention_count
        - avg_sentiment: Weighted average sentiment
    """
    from sklearn.cluster import DBSCAN

    if not items:
        return []

    if len(items) == 1:
        item = items[0]
        return [{
            "canonical_text": item.text.lower().strip(),
            "display_name": item.text,
            "variants": [],
            "total_mentions": item.mention_count,
            "avg_sentiment": item.sentiment_sum / max(item.mention_count, 1),
            "vector_id": item.vector_id,
            "mention_vector_ids": [item.vector_id],
        }]

    # Extract embeddings for sub-clustering
    embeddings = np.array([item.embedding for item in items])

    # DBSCAN with cosine distance (eps = 1 - similarity)
    sub_clustering = DBSCAN(
        eps=1 - similarity_threshold,
        min_samples=1,
        metric="cosine"
    ).fit(embeddings)

    # Group items by sub-cluster label
    groups: Dict[int, List[ClusterItem]] = defaultdict(list)
    for i, label in enumerate(sub_clustering.labels_):
        groups[label].append(items[i])

    # Convert groups to products
    products = []
    seen_canonical = set()  # Prevent exact duplicates

    for group_items in groups.values():
        # Sort by mention_count descending - highest frequency = canonical
        sorted_items = sorted(group_items, key=lambda x: -x.mention_count)

        canonical = sorted_items[0].text.lower().strip()

        # Skip if we already have this exact canonical text
        if canonical in seen_canonical:
            # Merge into existing product
            for p in products:
                if p["canonical_text"] == canonical:
                    for item in sorted_items:
                        if item.text not in p["variants"] and item.text.lower().strip() != canonical:
                            p["variants"].append(item.text)
                        p["total_mentions"] += item.mention_count
                    break
            continue

        seen_canonical.add(canonical)
        display_name = sorted_items[0].text  # Preserve original casing

        # Collect unique variants (excluding canonical)
        variants = []
        seen_variants = {canonical}
        for item in sorted_items[1:]:
            normalized = item.text.lower().strip()
            if normalized not in seen_variants:
                variants.append(item.text)
                seen_variants.add(normalized)

        # Calculate aggregated metrics
        total_mentions = sum(item.mention_count for item in group_items)
        total_sentiment = sum(item.sentiment_sum for item in group_items)

        products.append({
            "canonical_text": canonical,
            "display_name": display_name,
            "variants": variants,
            "total_mentions": total_mentions,
            "avg_sentiment": total_sentiment / max(total_mentions, 1),
            "vector_id": sorted_items[0].vector_id,  # Use highest-mention item's vector
            # Store ALL vector_ids to link mentions to this product
            "mention_vector_ids": [item.vector_id for item in group_items],
        })

    logger.debug(
        f"Deduplicated {len(items)} items into {len(products)} products",
        extra={"extra_data": {"input": len(items), "output": len(products)}}
    )

    return products


# LLM prompt for cluster labeling
CLUSTER_LABELING_PROMPT = """You are labeling clusters of product/service mentions for a Saudi {business_type}.

Given these sample items from a cluster, provide a concise category name.

RULES:
1. Category name should be 1-3 words, descriptive
2. Provide both English and Arabic names
3. If items are drinks, specify type (Hot Coffee, Cold Drinks, Tea, etc.)
4. If items are food, specify type (Pastries, Sandwiches, Main Dishes, etc.)
5. For service aspects, use clear labels (Service Speed, Staff Friendliness, Cleanliness, etc.)

CLUSTER ITEMS:
{items}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "name_en": "Category Name",
  "name_ar": "اسم الفئة",
  "has_products": true
}}

Set has_products to true if these are orderable items (food, drinks), false if service aspects."""


def is_clustering_needed(place_id: str, job_id: str = None) -> Tuple[bool, str]:
    """
    Check if clustering is needed and appropriate.

    Args:
        place_id: UUID of the place
        job_id: Optional job ID to verify extraction completion

    Returns:
        (should_cluster, reason)
    """
    session = get_session()
    try:
        # BUG-013 FIX: Check if ALL pipeline jobs for this place are complete
        # Don't start clustering while other jobs are still processing
        if job_id:
            job = session.query(Job).filter_by(id=job_id).first()
            if job:
                # Find the parent scrape job
                scrape_job = (
                    session.query(ScrapeJob)
                    .filter(ScrapeJob.pipeline_job_ids.any(job.id))
                    .first()
                )

                if scrape_job and scrape_job.pipeline_job_ids:
                    # Check if all pipeline jobs are complete
                    incomplete_jobs = session.query(Job).filter(
                        Job.id.in_(scrape_job.pipeline_job_ids),
                        Job.status != 'completed'
                    ).count()

                    if incomplete_jobs > 0:
                        logger.info(
                            f"Clustering deferred: {incomplete_jobs} jobs still processing",
                            extra={"extra_data": {"place_id": place_id, "job_id": job_id}}
                        )
                        return False, f"Waiting for {incomplete_jobs} other jobs to complete"

        # BUG-001 FIX: Verify mention extraction completed successfully
        # If job_id provided, check that mentions were actually extracted
        if job_id:
            job = session.query(Job).filter_by(id=job_id).first()
            if job:
                # Count reviews in this job
                review_count = job.total_reviews or 0
                if review_count > 0:
                    # Count RawMentions for reviews in this job
                    from database import Review
                    mention_count_for_job = session.query(RawMention).join(
                        Review, RawMention.review_id == Review.id
                    ).filter(
                        Review.job_id == job_id
                    ).count()

                    # Expect at least 30% of reviews to have mentions extracted
                    # (some reviews have no extractable mentions, that's normal)
                    MIN_EXTRACTION_RATE = 0.3
                    extraction_rate = mention_count_for_job / review_count if review_count > 0 else 0

                    if extraction_rate < MIN_EXTRACTION_RATE:
                        logger.warning(
                            f"Low mention extraction rate: {extraction_rate:.1%} ({mention_count_for_job}/{review_count})",
                            extra={"extra_data": {"place_id": place_id, "job_id": job_id}}
                        )
                        return False, f"Extraction incomplete: only {extraction_rate:.1%} of reviews have mentions"

        # Check existing taxonomy
        # FEATURE-001: Check both place_id (legacy) and place_ids array (multi-branch)
        place_uuid = uuid.UUID(place_id) if isinstance(place_id, str) else place_id
        existing = session.query(PlaceTaxonomy).filter(
            or_(
                PlaceTaxonomy.place_id == place_uuid,
                PlaceTaxonomy.place_ids.any(place_uuid)
            )
        ).first()

        if existing:
            if existing.status == "draft":
                return False, "Draft taxonomy already exists, pending review"
            if existing.status == "review":
                return False, "Taxonomy in review, cannot create new draft"

            # Active taxonomy exists - check for re-discovery threshold
            # FEATURE-001: Count unresolved mentions across ALL places in shared taxonomy
            all_place_ids = existing.all_place_ids
            unresolved_count = session.query(RawMention).filter(
                RawMention.place_id.in_(all_place_ids),
                RawMention.resolved_product_id.is_(None),
                RawMention.resolved_category_id.is_(None),
            ).count()

            if unresolved_count < REDISCOVERY_THRESHOLD:
                return False, f"Only {unresolved_count} unresolved mentions (need {REDISCOVERY_THRESHOLD})"

            return True, f"Re-discovery triggered: {unresolved_count} unresolved mentions across {len(all_place_ids)} places"

        # No taxonomy exists - check minimum mentions
        mention_count = vector_store.count_vectors(
            MENTIONS_COLLECTION,
            place_id=str(place_id),
            is_canonical=True,
        )

        if mention_count < MIN_MENTIONS_FOR_CLUSTERING:
            return False, f"Only {mention_count} mentions (need {MIN_MENTIONS_FOR_CLUSTERING})"

        return True, f"First discovery: {mention_count} mentions available"

    finally:
        session.close()


def trigger_taxonomy_clustering(job_id: str) -> bool:
    """
    Evaluate if clustering should be triggered for a completed job.
    Queues clustering task to RabbitMQ if conditions are met.

    PHASE 4: For multi-branch scrapes, detects all places and queues
    combined clustering with all place_ids.

    Returns:
        True if clustering was queued, False otherwise.
    """
    from rabbitmq import get_channel, TAXONOMY_CLUSTERING_QUEUE

    session = get_session()
    try:
        # Get the job and place
        job = session.query(Job).filter_by(id=job_id).first()
        if not job or not job.place_id:
            logger.debug("Job not found or no place_id", extra={"extra_data": {"job_id": job_id}})
            return False

        place_id = str(job.place_id)

        # PHASE 4: Check if this is part of a multi-place scrape
        scrape_job = (
            session.query(ScrapeJob)
            .filter(ScrapeJob.pipeline_job_ids.any(job.id))
            .first()
        )

        place_ids = [place_id]  # Default: single place
        scrape_job_id = None

        if scrape_job and scrape_job.pipeline_job_ids:
            # Get all place_ids from sibling jobs
            sibling_jobs = session.query(Job).filter(
                Job.id.in_(scrape_job.pipeline_job_ids)
            ).all()

            all_place_ids = list(set(str(j.place_id) for j in sibling_jobs if j.place_id))
            if len(all_place_ids) > 1:
                place_ids = all_place_ids
                scrape_job_id = str(scrape_job.id)
                logger.info(f"Multi-branch scrape detected: {len(place_ids)} places",
                           extra={"extra_data": {"scrape_job_id": scrape_job_id, "place_ids": place_ids}})

        # Check if clustering is needed (pass job_id for extraction verification)
        # For multi-place, we still check with primary place_id but clustering will gather all
        should_cluster, reason = is_clustering_needed(place_id, job_id=job_id)

        if not should_cluster:
            logger.debug(f"Clustering skipped: {reason}",
                        extra={"extra_data": {"place_id": place_id, "reason": reason}})
            return False

        # Queue clustering task
        # PHASE 4: Include place_ids array and scrape_job_id for multi-branch
        task_data = {
            "type": "taxonomy_clustering",
            "place_id": place_id,  # Primary place (backward compat)
            "place_ids": place_ids,  # PHASE 4: All places for combined clustering
            "scrape_job_id": scrape_job_id,  # PHASE 4: Link to parent scrape
            "job_id": str(job_id),
            "trigger": "job_completion",
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            channel = get_channel()
            channel.basic_publish(
                exchange='',
                routing_key=TAXONOMY_CLUSTERING_QUEUE,
                body=json.dumps(task_data),
            )
            place_desc = f"{len(place_ids)} places" if len(place_ids) > 1 else f"place {place_id}"
            logger.info(f"Queued taxonomy clustering for {place_desc}: {reason}",
                       extra={"extra_data": {"place_ids": place_ids, "job_id": job_id}})
            return True
        except Exception as e:
            logger.error(f"Failed to queue taxonomy clustering: {e}",
                        extra={"extra_data": {"place_id": place_id}})
            return False

    except Exception as e:
        logger.error(f"Error in trigger_taxonomy_clustering: {e}",
                    extra={"extra_data": {"job_id": job_id}}, exc_info=True)
        return False
    finally:
        session.close()


def cluster_mentions(embeddings: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run HDBSCAN clustering on embeddings.

    Args:
        embeddings: 2D numpy array of shape (n_samples, n_features)

    Returns:
        Tuple of (cluster_labels, probabilities)
        cluster_labels: -1 indicates noise/outlier
    """
    try:
        import hdbscan
    except ImportError:
        logger.error("hdbscan not installed. Run: pip install hdbscan")
        # Return all as noise
        return np.full(len(embeddings), -1), np.zeros(len(embeddings))

    if len(embeddings) < HDBSCAN_CONFIG["min_cluster_size"]:
        logger.warning(f"Not enough samples for clustering: {len(embeddings)}")
        return np.full(len(embeddings), -1), np.zeros(len(embeddings))

    try:
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=HDBSCAN_CONFIG["min_cluster_size"],
            min_samples=HDBSCAN_CONFIG["min_samples"],
            metric=HDBSCAN_CONFIG["metric"],
            cluster_selection_method=HDBSCAN_CONFIG["cluster_selection_method"],
            prediction_data=True,
        )
        clusterer.fit(embeddings)

        logger.debug(f"HDBSCAN found {len(set(clusterer.labels_)) - (1 if -1 in clusterer.labels_ else 0)} clusters",
                    extra={"extra_data": {"n_samples": len(embeddings), "n_noise": sum(clusterer.labels_ == -1)}})

        return clusterer.labels_, clusterer.probabilities_

    except Exception as e:
        logger.error(f"HDBSCAN clustering failed: {e}")
        return np.full(len(embeddings), -1), np.zeros(len(embeddings))


def label_cluster(items: List[str], business_type: str = "cafe") -> dict:
    """
    Generate category label for a cluster using LLM.

    Args:
        items: Sample texts from cluster (max 10)
        business_type: Context for labeling

    Returns:
        {"name_en": str, "name_ar": str, "has_products": bool}
    """
    from openai import OpenAI
    from config import VLLM_BASE_URL, VLLM_API_KEY

    # Sample up to 10 items
    sample_items = items[:10]
    items_text = "\n".join(f"- {item}" for item in sample_items)

    prompt = CLUSTER_LABELING_PROMPT.format(
        business_type=business_type,
        items=items_text,
    )

    try:
        client = OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a category labeling assistant for Saudi businesses."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=200,
        )

        content = response.choices[0].message.content.strip()

        # Clean up markdown if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result = json.loads(content)

        # Validate and normalize
        return {
            "name_en": result.get("name_en", "Unnamed Category"),
            "name_ar": result.get("name_ar", "فئة غير مسماة"),
            "has_products": result.get("has_products", True),
        }

    except Exception as e:
        logger.warning(f"LLM cluster labeling failed: {e}")
        # Fallback: use first item as category name
        fallback_name = items[0][:30] if items else "Unknown"
        return {
            "name_en": fallback_name,
            "name_ar": fallback_name,
            "has_products": True,
        }


def compute_cluster_centroid(embeddings: List[List[float]]) -> List[float]:
    """Compute the centroid of a cluster."""
    arr = np.array(embeddings)
    centroid = np.mean(arr, axis=0)
    # Normalize
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm
    return centroid.tolist()


def detect_super_categories(
    cluster_centroids: Dict[int, List[float]],
) -> Dict[int, Optional[int]]:
    """
    Group clusters into super-categories based on centroid similarity.

    Args:
        cluster_centroids: Mapping from cluster_id to centroid vector

    Returns:
        Mapping from cluster_id to super_category_id (None if standalone)
    """
    if len(cluster_centroids) < 2:
        return {cid: None for cid in cluster_centroids}

    cluster_ids = list(cluster_centroids.keys())
    centroids = np.array([cluster_centroids[cid] for cid in cluster_ids])

    # Compute pairwise cosine similarity
    # For normalized vectors, cosine = dot product
    similarity_matrix = np.dot(centroids, centroids.T)

    # Use agglomerative clustering to group similar clusters
    try:
        from sklearn.cluster import AgglomerativeClustering

        agg = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - SUPER_CATEGORY_SIMILARITY_THRESHOLD,
            metric="precomputed",
            linkage="average",
        )

        # Convert similarity to distance
        distance_matrix = 1 - similarity_matrix
        np.fill_diagonal(distance_matrix, 0)

        super_labels = agg.fit_predict(distance_matrix)

        result = {}
        for i, cid in enumerate(cluster_ids):
            super_id = int(super_labels[i])
            # Only assign super-category if there are multiple clusters in it
            same_super = [j for j, sl in enumerate(super_labels) if sl == super_id]
            if len(same_super) > 1:
                result[cid] = super_id
            else:
                result[cid] = None

        return result

    except ImportError:
        logger.warning("sklearn not available for super-category detection")
        return {cid: None for cid in cluster_centroids}
    except Exception as e:
        logger.warning(f"Super-category detection failed: {e}")
        return {cid: None for cid in cluster_centroids}


def build_hierarchy(
    product_items: List[ClusterItem],
    aspect_items: List[ClusterItem],
    product_labels: Dict[int, dict],
    aspect_labels: Dict[int, dict],
    product_centroids: Dict[int, List[float]],
    aspect_centroids: Dict[int, List[float]] = None,  # BUG-006 FIX: Accept aspect centroids
    business_type: str = "business",
) -> dict:
    """
    Build taxonomy hierarchy from clustered items.

    Args:
        product_items: Clustered product mention items
        aspect_items: Clustered aspect mention items
        product_labels: LLM-generated labels for product clusters
        aspect_labels: LLM-generated labels for aspect clusters
        product_centroids: Centroid embeddings for product clusters
        aspect_centroids: Centroid embeddings for aspect clusters (BUG-006 FIX)
        business_type: Type of business (e.g., "Cafe", "Restaurant") for LLM context

    Returns:
        {
            "main_categories": [...],
            "sub_categories": [...],
            "products": [...],
            "aspect_categories": [...],
        }
    """
    aspect_centroids = aspect_centroids or {}
    hierarchy = {
        "main_categories": [],
        "sub_categories": [],
        "products": [],
        "aspect_categories": [],
    }

    # Group products by cluster
    product_clusters = defaultdict(list)
    for item in product_items:
        if item.cluster_id >= 0:
            product_clusters[item.cluster_id].append(item)

    # Detect super-categories for products
    super_mapping = detect_super_categories(product_centroids)

    # Group clusters by super-category
    super_to_clusters = defaultdict(list)
    standalone_clusters = []
    for cluster_id, super_id in super_mapping.items():
        if super_id is not None:
            super_to_clusters[super_id].append(cluster_id)
        else:
            standalone_clusters.append(cluster_id)

    # Create main categories for super-categories
    main_id_map = {}  # super_id -> main_category dict
    for super_id, cluster_ids in super_to_clusters.items():
        # Name main category from child clusters using LLM
        child_names_en = [product_labels[cid]["name_en"] for cid in cluster_ids if cid in product_labels]
        child_names_ar = [product_labels[cid]["name_ar"] for cid in cluster_ids if cid in product_labels]
        main_names = _derive_main_category_name(child_names_en, child_names_ar, business_type=business_type)
        main_name_en = main_names["name_en"]
        main_name_ar = main_names["name_ar"]

        main_cat = {
            "id": str(uuid.uuid4()),
            "name": main_name_en.lower().replace(" ", "_"),
            "display_name_en": main_name_en,
            "display_name_ar": main_name_ar,
            "has_products": True,
            "parent_id": None,
        }
        hierarchy["main_categories"].append(main_cat)
        main_id_map[super_id] = main_cat

    # Create sub-categories from clusters
    sub_id_map = {}  # cluster_id -> sub_category dict
    for cluster_id, items in product_clusters.items():
        if cluster_id not in product_labels:
            continue

        label = product_labels[cluster_id]
        super_id = super_mapping.get(cluster_id)

        parent_id = None
        if super_id is not None and super_id in main_id_map:
            parent_id = main_id_map[super_id]["id"]

        sub_cat = {
            "id": str(uuid.uuid4()),
            "name": label["name_en"].lower().replace(" ", "_"),
            "display_name_en": label["name_en"],
            "display_name_ar": label["name_ar"],
            "has_products": label.get("has_products", True),
            "parent_id": parent_id,
            "discovered_mention_count": sum(item.mention_count for item in items),
        }

        if parent_id:
            hierarchy["sub_categories"].append(sub_cat)
        else:
            # Standalone cluster becomes main category
            sub_cat["parent_id"] = None
            hierarchy["main_categories"].append(sub_cat)

        sub_id_map[cluster_id] = sub_cat

    # Create products from items WITH DEDUPLICATION
    # Group items by cluster first
    cluster_items: Dict[int, List[ClusterItem]] = defaultdict(list)
    for item in product_items:
        if item.cluster_id >= 0:  # Skip noise
            cluster_items[item.cluster_id].append(item)

    # Process each cluster with deduplication
    for cluster_id, items in cluster_items.items():
        category = sub_id_map.get(cluster_id)
        if not category:
            continue

        # Deduplicate similar items within this cluster
        product_groups = deduplicate_cluster_items(items)

        logger.debug(
            f"Cluster {cluster_id} ({category['name']}): {len(items)} items → {len(product_groups)} products"
        )

        for group in product_groups:
            product = {
                "id": str(uuid.uuid4()),
                "canonical_text": group["canonical_text"],
                "display_name": group["display_name"],
                "variants": group["variants"],
                "discovered_category_id": category["id"],
                "vector_id": group["vector_id"],
                "discovered_mention_count": group["total_mentions"],
                "avg_sentiment": group["avg_sentiment"],
                # Store vector_ids to link mentions to this product
                "mention_vector_ids": group.get("mention_vector_ids", []),
            }
            hierarchy["products"].append(product)

    # Create aspect categories (flat, no products)
    aspect_clusters = defaultdict(list)
    for item in aspect_items:
        if item.cluster_id >= 0:
            aspect_clusters[item.cluster_id].append(item)

    for cluster_id, items in aspect_clusters.items():
        if cluster_id not in aspect_labels:
            continue

        label = aspect_labels[cluster_id]
        aspect_cat = {
            "id": str(uuid.uuid4()),
            "name": label["name_en"].lower().replace(" ", "_"),
            "display_name_en": label["name_en"],
            "display_name_ar": label["name_ar"],
            "has_products": False,
            "parent_id": None,
            "discovered_mention_count": sum(item.mention_count for item in items),
            # BUG-006 FIX: Include centroid embedding for later indexing
            "centroid_embedding": aspect_centroids.get(cluster_id),
            # Store vector_ids to link mentions to this category
            "mention_vector_ids": [item.vector_id for item in items],
        }
        hierarchy["aspect_categories"].append(aspect_cat)

    return hierarchy


MAIN_CATEGORY_PROMPT = """You are naming a parent category that groups these sub-categories for a Saudi {business_type}.

SUB-CATEGORIES:
{subcategories}

Provide a concise parent category name (1-2 words) that encompasses all these sub-categories.

Return ONLY valid JSON (no markdown):
{{
  "name_en": "Parent Category",
  "name_ar": "الفئة الرئيسية"
}}"""


def _derive_main_category_name(child_names_en: List[str], child_names_ar: List[str], business_type: str = "cafe") -> dict:
    """
    Derive a main category name from child category names using LLM.

    Returns:
        {"name_en": str, "name_ar": str}
    """
    if not child_names_en:
        return {"name_en": "Products", "name_ar": "منتجات"}

    from openai import OpenAI
    from config import VLLM_BASE_URL, VLLM_API_KEY

    # Combine English and Arabic names for context
    subcategories = "\n".join(f"- {en} / {ar}" for en, ar in zip(child_names_en, child_names_ar))

    prompt = MAIN_CATEGORY_PROMPT.format(
        business_type=business_type,
        subcategories=subcategories,
    )

    try:
        client = OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a category naming assistant for Saudi businesses."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=100,
        )

        content = response.choices[0].message.content.strip()

        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result = json.loads(content)
        return {
            "name_en": result.get("name_en", "Products"),
            "name_ar": result.get("name_ar", "منتجات"),
        }

    except Exception as e:
        logger.warning(f"LLM main category naming failed: {e}")
        # Fallback: use first child name or generic
        return {
            "name_en": child_names_en[0] if child_names_en else "Products",
            "name_ar": child_names_ar[0] if child_names_ar else "منتجات",
        }


def save_draft_taxonomy(
    place_id: str,
    hierarchy: dict,
    reviews_sampled: int,
    place_ids: Optional[List[str]] = None,  # PHASE 4: Multi-place support
    scrape_job_id: Optional[str] = None,    # PHASE 4: Link to parent scrape
) -> Optional[str]:
    """
    Save draft taxonomy to database.

    Args:
        place_id: Primary place UUID (backward compat)
        hierarchy: Taxonomy hierarchy dict
        reviews_sampled: Number of reviews used for clustering
        place_ids: All place UUIDs for multi-branch shared taxonomy (PHASE 4)
        scrape_job_id: Parent scrape job UUID (PHASE 4)

    Returns:
        taxonomy_id if successful, None otherwise
    """
    session = get_session()
    try:
        # PHASE 4: Check for existing draft across ALL places
        place_uuid = uuid.UUID(place_id) if isinstance(place_id, str) else place_id
        place_uuids = [uuid.UUID(p) if isinstance(p, str) else p for p in (place_ids or [place_id])]

        # Build conditions: check if ANY of our place_uuids conflicts with existing taxonomy
        # - Either matches place_id directly
        # - Or is contained in the place_ids array
        overlap_conditions = [PlaceTaxonomy.place_id.in_(place_uuids)]
        for p_uuid in place_uuids:
            overlap_conditions.append(PlaceTaxonomy.place_ids.any(p_uuid))

        existing = session.query(PlaceTaxonomy).filter(
            or_(*overlap_conditions),
            PlaceTaxonomy.status == "draft",
        ).first()

        if existing:
            place_desc = f"{len(place_ids)} places" if place_ids and len(place_ids) > 1 else f"place {place_id}"
            logger.warning(f"Draft taxonomy already exists for {place_desc}, skipping")
            return str(existing.id)

        # Count entities
        total_categories = (
            len(hierarchy["main_categories"]) +
            len(hierarchy["sub_categories"]) +
            len(hierarchy["aspect_categories"])
        )
        total_products = len(hierarchy["products"])

        # Create taxonomy
        # PHASE 4: Set place_ids and scrape_job_id for multi-branch support
        taxonomy = PlaceTaxonomy(
            place_id=place_uuid,  # Primary place (backward compat)
            place_ids=place_uuids if place_ids and len(place_ids) > 1 else None,  # PHASE 4
            scrape_job_id=uuid.UUID(scrape_job_id) if scrape_job_id else None,    # PHASE 4
            status="draft",
            discovered_at=datetime.utcnow(),
            reviews_sampled=reviews_sampled,
            entities_discovered=total_categories + total_products,
        )
        session.add(taxonomy)
        session.flush()

        taxonomy_id = taxonomy.id

        # Create categories
        category_id_map = {}  # temp_id -> real TaxonomyCategory

        # Main categories first (no parent)
        for cat_data in hierarchy["main_categories"]:
            category = TaxonomyCategory(
                taxonomy_id=taxonomy_id,
                parent_id=None,
                name=cat_data["name"],
                display_name_en=cat_data["display_name_en"],
                display_name_ar=cat_data["display_name_ar"],
                has_products=cat_data["has_products"],
                discovered_mention_count=cat_data.get("discovered_mention_count", 0),
            )
            session.add(category)
            session.flush()
            category_id_map[cat_data["id"]] = category

        # Sub-categories (with parent)
        for cat_data in hierarchy["sub_categories"]:
            parent = category_id_map.get(cat_data["parent_id"])
            category = TaxonomyCategory(
                taxonomy_id=taxonomy_id,
                parent_id=parent.id if parent else None,
                name=cat_data["name"],
                display_name_en=cat_data["display_name_en"],
                display_name_ar=cat_data["display_name_ar"],
                has_products=cat_data["has_products"],
                discovered_mention_count=cat_data.get("discovered_mention_count", 0),
            )
            session.add(category)
            session.flush()
            category_id_map[cat_data["id"]] = category

        # Aspect categories (flat)
        for cat_data in hierarchy["aspect_categories"]:
            category = TaxonomyCategory(
                taxonomy_id=taxonomy_id,
                parent_id=None,
                name=cat_data["name"],
                display_name_en=cat_data["display_name_en"],
                display_name_ar=cat_data["display_name_ar"],
                has_products=False,
                discovered_mention_count=cat_data.get("discovered_mention_count", 0),
                # BUG-006 FIX: Store centroid embedding for later use in publish indexing
                centroid_embedding=cat_data.get("centroid_embedding"),
            )
            session.add(category)
            session.flush()
            category_id_map[cat_data["id"]] = category

        # Create products and track mention links
        product_mention_links = []  # (product_db_id, [vector_ids])
        for prod_data in hierarchy["products"]:
            discovered_cat = category_id_map.get(prod_data["discovered_category_id"])
            product = TaxonomyProduct(
                taxonomy_id=taxonomy_id,
                discovered_category_id=discovered_cat.id if discovered_cat else None,
                canonical_text=prod_data["canonical_text"],
                display_name=prod_data["display_name"],
                variants=prod_data.get("variants", []),  # Save variants
                vector_id=prod_data.get("vector_id"),
                discovered_mention_count=prod_data.get("discovered_mention_count", 1),
                avg_sentiment=prod_data.get("avg_sentiment"),
            )
            session.add(product)
            session.flush()  # Get product.id

            # Track mentions to link
            if prod_data.get("mention_vector_ids"):
                product_mention_links.append((product.id, discovered_cat.id if discovered_cat else None, prod_data["mention_vector_ids"]))

        # Collect category mention links
        category_mention_links = []  # (category_db_id, [vector_ids])
        for cat_data in hierarchy.get("aspect_categories", []):
            db_cat = category_id_map.get(cat_data["id"])
            if db_cat and cat_data.get("mention_vector_ids"):
                category_mention_links.append((db_cat.id, cat_data["mention_vector_ids"]))

        session.commit()

        # Link mentions to discovered products/categories
        linked_count = 0
        for product_id, category_id, vector_ids in product_mention_links:
            for vector_id in vector_ids:
                updated = session.query(RawMention).filter_by(
                    qdrant_point_id=vector_id
                ).update({
                    "discovered_product_id": product_id,
                    "discovered_category_id": category_id,
                }, synchronize_session=False)
                linked_count += updated

        for category_id, vector_ids in category_mention_links:
            for vector_id in vector_ids:
                updated = session.query(RawMention).filter_by(
                    qdrant_point_id=vector_id
                ).update({
                    "discovered_category_id": category_id,
                }, synchronize_session=False)
                linked_count += updated

        session.commit()
        logger.info(f"Linked {linked_count} mentions to discovered products/categories")

        # TEXT-BASED ORPHAN RESCUE
        # Some mentions weren't linked during clustering because vectors didn't match,
        # but they contain the product name (e.g., "V60 جواتيمالا" contains "v60")
        text_rescued = 0
        products = session.query(TaxonomyProduct).filter_by(taxonomy_id=taxonomy_id).all()
        orphan_mentions = session.query(RawMention).filter(
            RawMention.discovered_product_id.is_(None),
            RawMention.mention_type == 'product',
            RawMention.place_id.in_(place_uuids)
        ).all()

        for orphan in orphan_mentions:
            for product in products:
                if _text_matches_product(orphan.mention_text, product.canonical_text):
                    orphan.discovered_product_id = product.id
                    orphan.discovered_category_id = product.discovered_category_id
                    text_rescued += 1
                    break  # Stop after first match

        if text_rescued > 0:
            session.commit()
            logger.info(f"Text matching rescued {text_rescued} orphan mentions",
                       extra={"extra_data": {"rescued": text_rescued, "total_orphans": len(orphan_mentions)}})

        # PHASE 4: Log multi-place info
        place_desc = f"{len(place_ids)} places" if place_ids and len(place_ids) > 1 else f"place {place_id}"
        logger.info(f"Saved draft taxonomy for {place_desc}",
                   extra={"extra_data": {
                       "taxonomy_id": str(taxonomy_id),
                       "place_ids": [str(p) for p in place_uuids],
                       "categories": total_categories,
                       "products": total_products,
                   }})

        return str(taxonomy_id)

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save draft taxonomy: {e}", exc_info=True)
        return None
    finally:
        session.close()


def run_clustering_job(
    place_id: str,
    job_id: Optional[str] = None,
    place_ids: Optional[List[str]] = None,  # PHASE 4: Multi-place support
    scrape_job_id: Optional[str] = None,    # PHASE 4: Link to parent scrape
) -> Optional[str]:
    """
    Main clustering entry point.

    Args:
        place_id: UUID of primary place to cluster (backward compat)
        job_id: Optional triggering job ID (for logging)
        place_ids: All place UUIDs for combined clustering (PHASE 4)
        scrape_job_id: Parent scrape job UUID (PHASE 4)

    Returns:
        taxonomy_id if successful, None if failed/skipped
    """
    # PHASE 4: Use place_ids if provided, otherwise single place
    effective_place_ids = place_ids if place_ids else [place_id]
    is_multi_place = len(effective_place_ids) > 1

    place_desc = f"{len(effective_place_ids)} places" if is_multi_place else f"place {place_id}"
    logger.info(f"Starting clustering job for {place_desc}",
               extra={"extra_data": {"place_ids": effective_place_ids, "job_id": job_id}})

    # Fetch business type from Place record (use primary place)
    session = get_session()
    try:
        place = session.query(Place).filter_by(id=place_id).first()
        business_type = place.category if place and place.category else "business"
    finally:
        session.close()

    # Step 1: Fetch vectors from Qdrant
    # PHASE 4: Gather from ALL places for combined clustering
    all_vectors = vector_store.scroll_all_vectors(
        collection_name=MENTIONS_COLLECTION,
        place_ids=effective_place_ids,  # PHASE 4: Multi-place
        is_canonical=True,
    )

    if len(all_vectors) < MIN_MENTIONS_FOR_CLUSTERING:
        logger.warning(f"Not enough vectors for clustering: {len(all_vectors)}",
                      extra={"extra_data": {"place_ids": effective_place_ids}})
        return None

    # Step 2: Separate products and aspects
    product_items = []
    aspect_items = []

    for vector_id, embedding, payload in all_vectors:
        item = ClusterItem(
            vector_id=vector_id,
            text=payload.text,
            embedding=embedding,
            mention_type=payload.mention_type,
            sentiment_sum=payload.sentiment_sum,
            mention_count=payload.mention_count,
        )
        if payload.mention_type == "product":
            product_items.append(item)
        else:
            aspect_items.append(item)

    logger.debug(f"Fetched {len(product_items)} products, {len(aspect_items)} aspects")

    # Step 3: Cluster products
    product_labels = {}
    product_centroids = {}

    if product_items:
        product_embeddings = np.array([item.embedding for item in product_items])
        labels, probs = cluster_mentions(product_embeddings)

        for i, item in enumerate(product_items):
            item.cluster_id = int(labels[i])
            item.confidence = float(probs[i])

        # Group by cluster and label
        product_clusters = defaultdict(list)
        for item in product_items:
            if item.cluster_id >= 0:
                product_clusters[item.cluster_id].append(item)

        for cluster_id, items in product_clusters.items():
            # Get sample texts for labeling
            sample_texts = [item.text for item in sorted(items, key=lambda x: -x.confidence)[:10]]
            product_labels[cluster_id] = label_cluster(sample_texts, business_type=business_type)

            # Compute centroid
            cluster_embeddings = [item.embedding for item in items]
            product_centroids[cluster_id] = compute_cluster_centroid(cluster_embeddings)

    # Step 4: Cluster aspects
    aspect_labels = {}
    aspect_centroids = {}  # BUG-006 FIX: Store aspect centroids

    if aspect_items:
        aspect_embeddings = np.array([item.embedding for item in aspect_items])
        labels, probs = cluster_mentions(aspect_embeddings)

        for i, item in enumerate(aspect_items):
            item.cluster_id = int(labels[i])
            item.confidence = float(probs[i])

        # Group by cluster and label
        aspect_clusters = defaultdict(list)
        for item in aspect_items:
            if item.cluster_id >= 0:
                aspect_clusters[item.cluster_id].append(item)

        for cluster_id, items in aspect_clusters.items():
            sample_texts = [item.text for item in sorted(items, key=lambda x: -x.confidence)[:10]]
            aspect_labels[cluster_id] = label_cluster(sample_texts, business_type=business_type)
            # Override has_products for aspects
            aspect_labels[cluster_id]["has_products"] = False

            # BUG-006 FIX: Compute centroid for aspect clusters
            cluster_embeddings = [item.embedding for item in items]
            aspect_centroids[cluster_id] = compute_cluster_centroid(cluster_embeddings)

    # Step 5: Build hierarchy
    hierarchy = build_hierarchy(
        product_items=product_items,
        aspect_items=aspect_items,
        product_labels=product_labels,
        aspect_labels=aspect_labels,
        product_centroids=product_centroids,
        aspect_centroids=aspect_centroids,  # BUG-006 FIX: Pass aspect centroids
        business_type=business_type,
    )

    # Check if hierarchy has any content
    total_entities = (
        len(hierarchy["main_categories"]) +
        len(hierarchy["sub_categories"]) +
        len(hierarchy["products"]) +
        len(hierarchy["aspect_categories"])
    )
    if total_entities == 0:
        logger.warning("Clustering produced empty hierarchy (all noise), skipping taxonomy creation",
                      extra={"extra_data": {"place_ids": effective_place_ids}})
        return None

    # Count reviews sampled (estimate from RawMention table)
    # PHASE 4: Count across ALL places for multi-branch
    session = get_session()
    try:
        place_uuids = [uuid.UUID(p) if isinstance(p, str) else p for p in effective_place_ids]
        reviews_sampled = session.query(RawMention.review_id).filter(
            RawMention.place_id.in_(place_uuids)
        ).distinct().count()
    finally:
        session.close()

    # Step 6: Save draft taxonomy
    # PHASE 4: Pass place_ids and scrape_job_id for multi-branch support
    taxonomy_id = save_draft_taxonomy(
        place_id=place_id,
        hierarchy=hierarchy,
        reviews_sampled=reviews_sampled,
        place_ids=effective_place_ids if is_multi_place else None,
        scrape_job_id=scrape_job_id,
    )

    if taxonomy_id:
        logger.info(f"Clustering job completed for {place_desc}",
                   extra={"extra_data": {
                       "taxonomy_id": taxonomy_id,
                       "place_ids": effective_place_ids,
                       "product_clusters": len(product_labels),
                       "aspect_clusters": len(aspect_labels),
                   }})

    return taxonomy_id


def process_clustering_message(ch, method, properties, body):
    """RabbitMQ consumer callback for clustering jobs."""
    try:
        message = json.loads(body)
        place_id = message.get("place_id")
        job_id = message.get("job_id")
        # PHASE 4: Read multi-place parameters
        place_ids = message.get("place_ids")
        scrape_job_id = message.get("scrape_job_id")

        if not place_id:
            logger.error("Clustering message missing place_id")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # PHASE 4: Log multi-place info
        is_multi_place = place_ids and len(place_ids) > 1
        place_desc = f"{len(place_ids)} places" if is_multi_place else f"place {place_id}"
        logger.info(f"Processing clustering message for {place_desc}",
                   extra={"extra_data": {"place_ids": place_ids or [place_id], "job_id": job_id}})

        # Run clustering
        # PHASE 4: Pass place_ids and scrape_job_id
        taxonomy_id = run_clustering_job(
            place_id=place_id,
            job_id=job_id,
            place_ids=place_ids,
            scrape_job_id=scrape_job_id,
        )

        if taxonomy_id:
            logger.info(f"Clustering completed: taxonomy {taxonomy_id}")
        else:
            logger.warning(f"Clustering produced no taxonomy for {place_desc}")

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger.error(f"Error processing clustering message: {e}", exc_info=True)
        # Requeue for retry
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


if __name__ == "__main__":
    # Test run with a specific place_id
    import sys
    if len(sys.argv) > 1:
        test_place_id = sys.argv[1]
        print(f"Running clustering for place: {test_place_id}")
        result = run_clustering_job(test_place_id)
        print(f"Result: {result}")
    else:
        print("Usage: python clustering_job.py <place_id>")
