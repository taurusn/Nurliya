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
from database import (
    PlaceTaxonomy, TaxonomyCategory, TaxonomyProduct, RawMention,
    Job, Place, get_session,
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
SUPER_CATEGORY_SIMILARITY_THRESHOLD = 0.7  # For grouping sub-categories


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
        existing = session.query(PlaceTaxonomy).filter_by(place_id=place_id).first()

        if existing:
            if existing.status == "draft":
                return False, "Draft taxonomy already exists, pending review"
            if existing.status == "review":
                return False, "Taxonomy in review, cannot create new draft"

            # Active taxonomy exists - check for re-discovery threshold
            unresolved_count = session.query(RawMention).filter(
                RawMention.place_id == place_id,
                RawMention.resolved_product_id.is_(None),
                RawMention.resolved_category_id.is_(None),
            ).count()

            if unresolved_count < REDISCOVERY_THRESHOLD:
                return False, f"Only {unresolved_count} unresolved mentions (need {REDISCOVERY_THRESHOLD})"

            return True, f"Re-discovery triggered: {unresolved_count} unresolved mentions"

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

        # Check if clustering is needed (pass job_id for extraction verification)
        should_cluster, reason = is_clustering_needed(place_id, job_id=job_id)

        if not should_cluster:
            logger.debug(f"Clustering skipped: {reason}",
                        extra={"extra_data": {"place_id": place_id, "reason": reason}})
            return False

        # Queue clustering task
        task_data = {
            "type": "taxonomy_clustering",
            "place_id": place_id,
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
            logger.info(f"Queued taxonomy clustering: {reason}",
                       extra={"extra_data": {"place_id": place_id, "job_id": job_id}})
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

    # Create products from items
    for item in product_items:
        if item.cluster_id < 0:
            continue  # Skip noise

        category = sub_id_map.get(item.cluster_id)
        if not category:
            continue

        product = {
            "id": str(uuid.uuid4()),
            "canonical_text": item.text.lower().strip(),
            "display_name": item.text,
            "discovered_category_id": category["id"],
            "vector_id": item.vector_id,
            "discovered_mention_count": item.mention_count,
            "avg_sentiment": item.sentiment_sum / max(item.mention_count, 1),
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


def save_draft_taxonomy(place_id: str, hierarchy: dict, reviews_sampled: int) -> Optional[str]:
    """
    Save draft taxonomy to database.

    Returns:
        taxonomy_id if successful, None otherwise
    """
    session = get_session()
    try:
        # Check for existing draft (shouldn't happen, but be safe)
        existing = session.query(PlaceTaxonomy).filter_by(
            place_id=place_id,
            status="draft",
        ).first()

        if existing:
            logger.warning(f"Draft taxonomy already exists for place {place_id}, skipping")
            return str(existing.id)

        # Count entities
        total_categories = (
            len(hierarchy["main_categories"]) +
            len(hierarchy["sub_categories"]) +
            len(hierarchy["aspect_categories"])
        )
        total_products = len(hierarchy["products"])

        # Create taxonomy
        taxonomy = PlaceTaxonomy(
            place_id=place_id,
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

        # Create products
        for prod_data in hierarchy["products"]:
            discovered_cat = category_id_map.get(prod_data["discovered_category_id"])
            product = TaxonomyProduct(
                taxonomy_id=taxonomy_id,
                discovered_category_id=discovered_cat.id if discovered_cat else None,
                canonical_text=prod_data["canonical_text"],
                display_name=prod_data["display_name"],
                vector_id=prod_data.get("vector_id"),
                discovered_mention_count=prod_data.get("discovered_mention_count", 1),
                avg_sentiment=prod_data.get("avg_sentiment"),
            )
            session.add(product)

        session.commit()

        logger.info(f"Saved draft taxonomy for place {place_id}",
                   extra={"extra_data": {
                       "taxonomy_id": str(taxonomy_id),
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


def run_clustering_job(place_id: str, job_id: Optional[str] = None) -> Optional[str]:
    """
    Main clustering entry point.

    Args:
        place_id: UUID of place to cluster
        job_id: Optional triggering job ID (for logging)

    Returns:
        taxonomy_id if successful, None if failed/skipped
    """
    logger.info(f"Starting clustering job for place {place_id}",
               extra={"extra_data": {"place_id": place_id, "job_id": job_id}})

    # Fetch business type from Place record
    session = get_session()
    try:
        place = session.query(Place).filter_by(id=place_id).first()
        business_type = place.category if place and place.category else "business"
    finally:
        session.close()

    # Step 1: Fetch vectors from Qdrant
    all_vectors = vector_store.scroll_all_vectors(
        collection_name=MENTIONS_COLLECTION,
        place_id=place_id,
        is_canonical=True,
    )

    if len(all_vectors) < MIN_MENTIONS_FOR_CLUSTERING:
        logger.warning(f"Not enough vectors for clustering: {len(all_vectors)}",
                      extra={"extra_data": {"place_id": place_id}})
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
                      extra={"extra_data": {"place_id": place_id}})
        return None

    # Count reviews sampled (estimate from RawMention table)
    session = get_session()
    try:
        reviews_sampled = session.query(RawMention.review_id).filter_by(
            place_id=place_id
        ).distinct().count()
    finally:
        session.close()

    # Step 6: Save draft taxonomy
    taxonomy_id = save_draft_taxonomy(place_id, hierarchy, reviews_sampled)

    if taxonomy_id:
        logger.info(f"Clustering job completed for place {place_id}",
                   extra={"extra_data": {
                       "taxonomy_id": taxonomy_id,
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

        if not place_id:
            logger.error("Clustering message missing place_id")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        logger.info(f"Processing clustering message for place {place_id}",
                   extra={"extra_data": {"place_id": place_id, "job_id": job_id}})

        # Run clustering
        taxonomy_id = run_clustering_job(place_id, job_id)

        if taxonomy_id:
            logger.info(f"Clustering completed: taxonomy {taxonomy_id}")
        else:
            logger.warning(f"Clustering produced no taxonomy for place {place_id}")

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
