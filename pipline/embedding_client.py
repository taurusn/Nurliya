"""
Embedding client for generating text embeddings with Arabic support.
Uses sentence-transformers with multilingual model.

Includes an in-memory embedding cache to avoid recomputing embeddings
for the same normalized text (used heavily by mention grouping).
"""

import re
import unicodedata
from typing import Dict, List, Optional

from logging_config import get_logger
from config import EMBEDDING_MODEL, EMBEDDING_DIMENSION

logger = get_logger(__name__, service="embedding")

# Lazy load model to avoid import overhead
_model = None
_model_load_attempted = False

# In-memory cache: normalized_text -> embedding vector
# MiniLM embeddings are 384 floats (~3KB each), 1000 entries ≈ 3MB
_embedding_cache: Dict[str, List[float]] = {}
EMBEDDING_CACHE_MAX_SIZE = 2000


def _get_model():
    """Lazy load the sentence transformer model."""
    global _model, _model_load_attempted

    if _model is not None:
        return _model

    if _model_load_attempted:
        return None

    _model_load_attempted = True

    try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info(f"Embedding model loaded successfully (dimension: {_model.get_sentence_embedding_dimension()})")
        return _model
    except ImportError:
        logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
        return None
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
        return None


# Arabic character normalization mappings
ARABIC_CHAR_MAPPINGS = {
    # Alef variations → Alef
    '\u0622': '\u0627',  # Alef with madda → Alef
    '\u0623': '\u0627',  # Alef with hamza above → Alef
    '\u0625': '\u0627',  # Alef with hamza below → Alef
    '\u0671': '\u0627',  # Alef wasla → Alef
    # Teh marbuta → Heh
    '\u0629': '\u0647',  # Teh marbuta → Heh
    # Yeh variations → Yeh
    '\u0649': '\u064A',  # Alef maksura → Yeh
    '\u06CC': '\u064A',  # Farsi yeh → Arabic yeh
    # Kaf variations
    '\u06A9': '\u0643',  # Farsi keh → Arabic kaf
}

# Arabic diacritics (tashkeel) - to be removed
ARABIC_DIACRITICS = re.compile(r'[\u064B-\u065F\u0670]')

# Tatweel (kashida) - elongation character
TATWEEL = '\u0640'


def normalize_arabic(text: str) -> str:
    """
    Normalize Arabic text for better embedding similarity.

    Operations:
    1. Normalize Unicode (NFC form)
    2. Remove diacritics (tashkeel)
    3. Remove tatweel (kashida)
    4. Normalize character variations (alef, yeh, etc.)
    5. Collapse multiple spaces

    Args:
        text: Input text (can be Arabic, English, or mixed)

    Returns:
        Normalized text
    """
    if not text:
        return ""

    # Unicode normalization (NFC form)
    text = unicodedata.normalize('NFC', text)

    # Remove Arabic diacritics
    text = ARABIC_DIACRITICS.sub('', text)

    # Remove tatweel
    text = text.replace(TATWEEL, '')

    # Apply character mappings
    for old, new in ARABIC_CHAR_MAPPINGS.items():
        text = text.replace(old, new)

    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def normalize_for_embedding(text: str) -> str:
    """
    Full normalization pipeline for embedding generation.

    Applies:
    1. Arabic normalization
    2. Lowercase (for consistency)
    3. Strip whitespace

    Args:
        text: Input text

    Returns:
        Normalized text ready for embedding
    """
    if not text:
        return ""

    # Arabic-specific normalization
    text = normalize_arabic(text)

    # Lowercase for consistency (works for both Arabic and English)
    text = text.lower()

    return text.strip()


def generate_embedding(text: str, normalize: bool = True) -> Optional[List[float]]:
    """
    Generate embedding for a single text. Uses in-memory cache.

    Args:
        text: Input text to embed
        normalize: Whether to apply Arabic normalization (default: True)

    Returns:
        Embedding vector as list of floats, or None if model unavailable
    """
    model = _get_model()
    if model is None:
        logger.warning("Embedding model not available, returning None")
        return None

    if normalize:
        text = normalize_for_embedding(text)

    if not text:
        logger.warning("Empty text after normalization, returning zero vector")
        return [0.0] * EMBEDDING_DIMENSION

    # Check cache
    if text in _embedding_cache:
        return _embedding_cache[text]

    try:
        embedding = model.encode(text, convert_to_numpy=True)
        result = embedding.tolist()
        _cache_embedding(text, result)
        return result
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None


def generate_embeddings(texts: List[str], normalize: bool = True, batch_size: int = 32) -> Optional[List[List[float]]]:
    """
    Generate embeddings for multiple texts (batch processing).
    Uses in-memory cache — only computes embeddings for uncached texts.

    Args:
        texts: List of input texts
        normalize: Whether to apply Arabic normalization (default: True)
        batch_size: Batch size for encoding (default: 32)

    Returns:
        List of embedding vectors, or None if model unavailable
    """
    model = _get_model()
    if model is None:
        logger.warning("Embedding model not available, returning None")
        return None

    if not texts:
        return []

    if normalize:
        normalized = [normalize_for_embedding(t) for t in texts]
    else:
        normalized = list(texts)

    # Split into cached and uncached
    results: List[Optional[List[float]]] = [None] * len(normalized)
    uncached_texts = []
    uncached_indices = []

    for i, t in enumerate(normalized):
        if not t:
            results[i] = [0.0] * EMBEDDING_DIMENSION
        elif t in _embedding_cache:
            results[i] = _embedding_cache[t]
        else:
            uncached_texts.append(t)
            uncached_indices.append(i)

    # Only call model.encode for uncached texts
    if uncached_texts:
        try:
            new_embeddings = model.encode(uncached_texts, convert_to_numpy=True, batch_size=batch_size)
            for idx, emb in zip(uncached_indices, new_embeddings):
                emb_list = emb.tolist()
                results[idx] = emb_list
                _cache_embedding(normalized[idx], emb_list)
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            return None

    cache_hits = len(normalized) - len(uncached_texts)
    if cache_hits > 0:
        logger.debug(f"Embedding cache: {cache_hits}/{len(normalized)} hits, {len(uncached_texts)} computed")

    return results


def _cache_embedding(text: str, embedding: List[float]):
    """Add an embedding to the cache, evicting oldest entries if full."""
    if len(_embedding_cache) >= EMBEDDING_CACHE_MAX_SIZE:
        # Evict ~10% of oldest entries (dict preserves insertion order in Python 3.7+)
        evict_count = EMBEDDING_CACHE_MAX_SIZE // 10
        keys_to_evict = list(_embedding_cache.keys())[:evict_count]
        for k in keys_to_evict:
            del _embedding_cache[k]
    _embedding_cache[text] = embedding


def compute_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """
    Compute cosine similarity between two embeddings.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        Cosine similarity score (0 to 1 for normalized vectors)
    """
    if not embedding1 or not embedding2:
        return 0.0

    if len(embedding1) != len(embedding2):
        logger.error(f"Embedding dimension mismatch: {len(embedding1)} vs {len(embedding2)}")
        return 0.0

    try:
        import numpy as np
        e1 = np.array(embedding1)
        e2 = np.array(embedding2)

        norm1 = np.linalg.norm(e1)
        norm2 = np.linalg.norm(e2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(e1, e2) / (norm1 * norm2))
    except ImportError:
        # Fallback without numpy
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        norm1 = sum(a * a for a in embedding1) ** 0.5
        norm2 = sum(b * b for b in embedding2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


def is_model_available() -> bool:
    """Check if the embedding model is available."""
    return _get_model() is not None


def get_model_dimension() -> int:
    """Get the embedding dimension of the loaded model."""
    model = _get_model()
    if model is not None:
        return model.get_sentence_embedding_dimension()
    return EMBEDDING_DIMENSION


# Pre-compute embeddings for common Arabic food/drink terms for testing
SAMPLE_ARABIC_TERMS = [
    "قهوة",           # coffee
    "لاتيه",          # latte
    "سبانش لاتيه",    # spanish latte
    "كابتشينو",       # cappuccino
    "موكا",           # mocha
    "شاي",            # tea
    "عصير",           # juice
    "كرواسون",        # croissant
    "كيك",            # cake
    "خدمة",           # service
    "سريع",           # fast
    "بطيء",           # slow
]


def test_arabic_embeddings():
    """
    Test Arabic embedding quality by checking similarity between related terms.
    Returns True if Arabic embeddings are working well.
    """
    if not is_model_available():
        logger.error("Model not available for testing")
        return False

    # Test pairs that should have high similarity
    test_pairs = [
        ("قهوة", "coffee"),  # Arabic/English for same concept
        ("سبانش لاتيه", "spanish latte"),
        ("لاتيه", "latte"),
        ("خدمة ممتازة", "excellent service"),
    ]

    results = []
    for ar, en in test_pairs:
        emb_ar = generate_embedding(ar)
        emb_en = generate_embedding(en)

        if emb_ar and emb_en:
            sim = compute_similarity(emb_ar, emb_en)
            results.append((ar, en, sim))
            logger.info(f"Similarity '{ar}' <-> '{en}': {sim:.3f}")

    # Check if average similarity is above threshold
    if results:
        avg_sim = sum(r[2] for r in results) / len(results)
        logger.info(f"Average cross-lingual similarity: {avg_sim:.3f}")
        return avg_sim > 0.5  # Threshold for acceptable quality

    return False


if __name__ == "__main__":
    # Run tests
    print("Testing Arabic normalization:")
    test_texts = [
        "القَهوَة السَعودِيَّة",  # With diacritics
        "القهوة السعودية",        # Without diacritics
        "سبـــانش لاتـــيه",     # With tatweel
        "spanish latté",          # Latin with accent
    ]

    for text in test_texts:
        normalized = normalize_for_embedding(text)
        print(f"  '{text}' -> '{normalized}'")

    print("\nTesting embedding generation:")
    if is_model_available():
        test_arabic_embeddings()
    else:
        print("  Model not available - install sentence-transformers")
