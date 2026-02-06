"""
Mention Grouping Utilities

Groups mentions by normalized text and merges similar groups using embedding similarity.
Handles Arabic text normalization (harakat, hamza variants, etc.)
"""

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sklearn.cluster import DBSCAN
import numpy as np

from embedding_client import normalize_arabic, generate_embeddings, compute_similarity


# Grouping similarity threshold (same as DBSCAN product clustering)
GROUP_SIMILARITY_THRESHOLD = 0.78


@dataclass
class MentionData:
    """Lightweight mention data for grouping operations."""
    id: str
    mention_text: str
    sentiment: Optional[str]
    review_text: str
    similarity_score: Optional[float] = None


@dataclass
class MentionGroup:
    """A group of similar mentions."""
    normalized_text: str
    display_text: str
    mention_ids: List[str] = field(default_factory=list)
    count: int = 0
    sentiments: Dict[str, int] = field(default_factory=lambda: {"positive": 0, "negative": 0, "neutral": 0})
    avg_similarity: Optional[float] = None
    sample_reviews: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "normalized_text": self.normalized_text,
            "display_text": self.display_text,
            "mention_ids": self.mention_ids,
            "count": self.count,
            "sentiments": self.sentiments,
            "avg_similarity": self.avg_similarity,
            "sample_reviews": self.sample_reviews,
        }


def normalize_for_grouping(text: str) -> str:
    """
    Normalize text for grouping (more aggressive than embedding normalization).

    Steps:
    1. Unicode normalization (NFC)
    2. Arabic normalization (harakat, hamza, etc.)
    3. Lowercase
    4. Remove punctuation (keep Arabic/Latin letters, numbers, spaces)
    5. Collapse multiple spaces
    6. Strip
    """
    if not text:
        return ""

    # Unicode normalization
    text = unicodedata.normalize('NFC', text)

    # Apply Arabic normalization (from embedding_client)
    text = normalize_arabic(text)

    # Lowercase
    text = text.lower()

    # Remove punctuation - keep Arabic letters (\u0600-\u06FF), Latin letters, numbers, spaces
    # Also keep Persian/Urdu extensions (\u0750-\u077F, \uFB50-\uFDFF, \uFE70-\uFEFF)
    text = re.sub(r'[^\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFFa-z0-9\s]', '', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def group_mentions_by_text(mentions: List[MentionData]) -> Dict[str, List[MentionData]]:
    """
    Group mentions by exact normalized text match.

    Returns:
        Dict mapping normalized_text -> list of mentions
    """
    groups: Dict[str, List[MentionData]] = defaultdict(list)

    for mention in mentions:
        normalized = normalize_for_grouping(mention.mention_text)
        if normalized:  # Skip empty after normalization
            groups[normalized].append(mention)

    return dict(groups)


def _compute_group_embeddings(groups: Dict[str, List[MentionData]]) -> Dict[str, List[float]]:
    """
    Compute embeddings for each group's normalized text.
    """
    texts = list(groups.keys())
    if not texts:
        return {}

    embeddings = generate_embeddings(texts, normalize=True)
    if embeddings is None:
        return {}

    return dict(zip(texts, embeddings))


def _find_most_common_text(mentions: List[MentionData]) -> str:
    """Find the most common original text form in a group."""
    if not mentions:
        return ""

    counter = Counter(m.mention_text for m in mentions)
    return counter.most_common(1)[0][0]


def _compute_sentiment_counts(mentions: List[MentionData]) -> Dict[str, int]:
    """Count sentiments in a group."""
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for m in mentions:
        if m.sentiment in counts:
            counts[m.sentiment] += 1
        else:
            counts["neutral"] += 1
    return counts


def _compute_avg_similarity(mentions: List[MentionData]) -> Optional[float]:
    """Compute average similarity score for mentions that have one."""
    scores = [m.similarity_score for m in mentions if m.similarity_score is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _get_sample_reviews(mentions: List[MentionData], max_samples: int = 3) -> List[str]:
    """Get sample review excerpts (first 100 chars each)."""
    samples = []
    seen_reviews = set()

    for m in mentions:
        if m.review_text and m.review_text not in seen_reviews:
            seen_reviews.add(m.review_text)
            # Take first 100 chars, add ellipsis if truncated
            excerpt = m.review_text[:100]
            if len(m.review_text) > 100:
                excerpt += "..."
            samples.append(excerpt)

            if len(samples) >= max_samples:
                break

    return samples


def _build_mention_group(
    normalized_text: str,
    mentions: List[MentionData],
    display_text: Optional[str] = None
) -> MentionGroup:
    """Build a MentionGroup from a list of mentions."""
    return MentionGroup(
        normalized_text=normalized_text,
        display_text=display_text or _find_most_common_text(mentions),
        mention_ids=[m.id for m in mentions],
        count=len(mentions),
        sentiments=_compute_sentiment_counts(mentions),
        avg_similarity=_compute_avg_similarity(mentions),
        sample_reviews=_get_sample_reviews(mentions),
    )


def merge_similar_groups(
    text_groups: Dict[str, List[MentionData]],
    similarity_threshold: float = GROUP_SIMILARITY_THRESHOLD
) -> List[MentionGroup]:
    """
    Merge groups with similar normalized text using embedding similarity.

    Uses DBSCAN clustering with cosine distance to find similar groups,
    then merges them into consolidated MentionGroup objects.

    Args:
        text_groups: Dict mapping normalized_text -> list of mentions
        similarity_threshold: Minimum cosine similarity to merge groups (default 0.78)

    Returns:
        List of MentionGroup objects (sorted by count descending)
    """
    if not text_groups:
        return []

    # If only one group, return it directly
    if len(text_groups) == 1:
        normalized_text, mentions = list(text_groups.items())[0]
        return [_build_mention_group(normalized_text, mentions)]

    # Compute embeddings for all group keys
    embeddings_map = _compute_group_embeddings(text_groups)

    # If embeddings failed, fall back to text-only groups
    if not embeddings_map:
        return [
            _build_mention_group(norm_text, mentions)
            for norm_text, mentions in text_groups.items()
        ]

    # Prepare data for DBSCAN
    texts = list(text_groups.keys())
    embeddings = [embeddings_map.get(t) for t in texts]

    # Filter out texts without embeddings
    valid_data = [(t, e) for t, e in zip(texts, embeddings) if e is not None]
    if not valid_data:
        return [
            _build_mention_group(norm_text, mentions)
            for norm_text, mentions in text_groups.items()
        ]

    valid_texts, valid_embeddings = zip(*valid_data)
    embedding_matrix = np.array(valid_embeddings)

    # Run DBSCAN with cosine distance
    # eps = 1 - similarity_threshold (convert similarity to distance)
    clustering = DBSCAN(
        eps=1 - similarity_threshold,
        min_samples=1,
        metric='cosine'
    ).fit(embedding_matrix)

    # Group by cluster label
    cluster_groups: Dict[int, List[str]] = defaultdict(list)
    for text, label in zip(valid_texts, clustering.labels_):
        cluster_groups[label].append(text)

    # Build merged groups
    result_groups: List[MentionGroup] = []

    for cluster_id, cluster_texts in cluster_groups.items():
        # Merge all mentions from all texts in this cluster
        all_mentions: List[MentionData] = []
        for text in cluster_texts:
            all_mentions.extend(text_groups[text])

        # Use the most common normalized text as the group key
        # and most common original text as display
        primary_text = max(cluster_texts, key=lambda t: len(text_groups[t]))

        group = _build_mention_group(
            normalized_text=primary_text,
            mentions=all_mentions,
        )
        result_groups.append(group)

    # Add any texts that didn't have embeddings
    texts_with_embeddings = set(valid_texts)
    for text, mentions in text_groups.items():
        if text not in texts_with_embeddings:
            result_groups.append(_build_mention_group(text, mentions))

    # Sort by count descending
    result_groups.sort(key=lambda g: g.count, reverse=True)

    return result_groups


def group_mentions(
    mentions: List[MentionData],
    similarity_threshold: float = GROUP_SIMILARITY_THRESHOLD
) -> Tuple[List[MentionGroup], int, int]:
    """
    Main entry point: Group mentions by normalized text, then merge similar groups.

    Args:
        mentions: List of MentionData objects
        similarity_threshold: Minimum cosine similarity to merge groups

    Returns:
        Tuple of (groups, total_mentions, total_groups)
    """
    if not mentions:
        return [], 0, 0

    # Step 1: Group by exact normalized text
    text_groups = group_mentions_by_text(mentions)

    # Step 2: Merge similar groups using embeddings
    merged_groups = merge_similar_groups(text_groups, similarity_threshold)

    return merged_groups, len(mentions), len(merged_groups)
