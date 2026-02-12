"""
LLM client for review analysis using OpenAI-compatible APIs.
Supports vLLM, Gemini, OpenAI, and other compatible providers.
"""

import json
from openai import OpenAI

from logging_config import get_logger
from config import VLLM_BASE_URL, VLLM_API_KEY, VLLM_MODEL

logger = get_logger(__name__, service="llm_client")

# Configure OpenAI client to point to LLM provider
client = OpenAI(
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY
)

SYSTEM_PROMPT = """You are a review analysis assistant for Saudi businesses including cafes, restaurants, hotels, and retail stores.

Your job is to analyze customer reviews and return structured JSON data.

RULES:
1. Analyze each review independently
2. Be accurate with Saudi dialect (نجدي، حجازي), formal Arabic (فصحى), and Arabizi
3. Only extract topics explicitly mentioned in the review — do not assume or hallucinate
4. Keep summaries to 1 sentence maximum
5. Suggested reply must be warm, professional, and use Saudi-friendly tone
6. If review mentions both good and bad aspects, capture both in separate topic arrays
7. Do not add topics based on general assumptions about the business type

TOPIC OPTIONS (only use these):
service, food, drinks, price, cleanliness, wait_time, staff, quality, atmosphere, location, parking, delivery

LANGUAGE DETECTION:
- ar: Arabic (formal or any dialect)
- en: English
- arabizi: Arabic written in English letters

URGENCY RULES:
Set urgent=true if:
- Sentiment is negative AND score > 0.7
- Review mentions health/safety issue
- Review threatens to report or escalate

SUGGESTED REPLY GUIDELINES:
- Use Saudi dialect naturally (ياهلا، نقدر، نعتذر منك)
- Acknowledge specific complaint
- If positive, thank warmly without being excessive
- Keep under 50 words
- Do not be defensive or make excuses

ACTION NOTE GUIDELINES (internal note for business owner, NOT for the customer):
- Set needs_action=true ONLY for negative or urgent reviews that warrant a follow-up action
- For positive/neutral reviews, set needs_action=false and leave action_ar/action_en as empty strings
- Suggest specific compensation when appropriate: free item, discount, invitation to revisit
- Flag for manager escalation if health/safety related
- Keep concise (under 20 words)
- Examples: "تعويض بقهوة مجانية" / "Offer free coffee as compensation"

OUTPUT FORMAT:
Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{
  "sentiment": "positive" | "neutral" | "negative",
  "score": 0.0-1.0,
  "topics_positive": ["topic1", "topic2"],
  "topics_negative": ["topic1"],
  "language": "ar" | "en" | "arabizi",
  "urgent": true | false,
  "summary_ar": "ملخص بالعربي",
  "summary_en": "English summary",
  "suggested_reply_ar": "رد مقترح بالسعودي",
  "needs_action": true | false,
  "action_ar": "ملاحظة داخلية للإدارة أو فارغ",
  "action_en": "Internal action note or empty string"
}"""


def analyze_review(review_text: str, rating: int = None) -> dict:
    """Analyze a single review and return structured data."""

    # Build prompt
    prompt = f"Analyze this review"
    if rating:
        prompt += f" (rating: {rating}/5)"
    prompt += f":\n\n{review_text}\n\nReturn ONLY the JSON analysis, nothing else."

    logger.debug("Calling LLM API", extra={"extra_data": {"model": VLLM_MODEL, "text_length": len(review_text)}})

    # Call LLM via OpenAI-compatible API
    response = client.chat.completions.create(
        model=VLLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=1000
    )

    # Extract response text
    content = response.choices[0].message.content.strip()

    # Clean up response (remove markdown code blocks if present)
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last lines (```json and ```)
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Parse JSON
    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        # Try to find JSON in the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(content[start:end])
        else:
            logger.error("Failed to parse LLM response", extra={"extra_data": {"content": content[:200]}})
            raise ValueError(f"Could not parse JSON from response: {content}") from e

    # Validate required fields
    required = ["sentiment", "score", "topics_positive", "topics_negative",
                "language", "urgent", "summary_ar", "summary_en", "suggested_reply_ar"]
    for field in required:
        if field not in result:
            result[field] = [] if "topics" in field else ("" if "summary" in field or "reply" in field else False)

    logger.debug(
        "LLM analysis complete",
        extra={"extra_data": {"sentiment": result.get("sentiment"), "score": result.get("score")}}
    )

    return result


def generate_anomaly_insight(anomaly_date: str, anomaly_type: str, magnitude: float,
                             topic_comparison: str, reviews_summary: str) -> dict:
    """Generate LLM insight for a sentiment anomaly."""

    prompt = f"""Analyze this sentiment anomaly for a Saudi business:

DATE: {anomaly_date}
ANOMALY TYPE: {anomaly_type} ({magnitude:.1f}% change from baseline)

TOPIC CHANGES VS 7-DAY BASELINE:
{topic_comparison}

REVIEWS FROM THIS DATE:
{reviews_summary}

Provide a brief analysis in JSON format with both English and Arabic:
{{
  "analysis": "2-3 sentences explaining what likely caused this anomaly. Look for patterns across reviews.",
  "analysis_ar": "نفس التحليل باللغة العربية، ٢-٣ جمل تشرح سبب هذا التغير",
  "recommendation": "One specific, actionable step the business can take.",
  "recommendation_ar": "خطوة واحدة محددة وقابلة للتنفيذ باللغة العربية"
}}

Be specific to the data provided. Do not give generic advice.
The Arabic text must be a proper Arabic translation, not transliteration.
Return ONLY valid JSON, no markdown or explanation."""

    logger.debug("Generating anomaly insight", extra={"extra_data": {"date": anomaly_date, "type": anomaly_type}})

    try:
        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a business analyst helping Saudi businesses understand customer feedback patterns."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )

        content = response.choices[0].message.content.strip()

        # Clean up response
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result = json.loads(content)

        # Ensure required fields
        if "analysis" not in result:
            result["analysis"] = "Unusual sentiment pattern detected."
        if "recommendation" not in result:
            result["recommendation"] = "Review the feedback from this period."

        logger.debug("Anomaly insight generated", extra={"extra_data": {"analysis_length": len(result.get("analysis", ""))}})

        return result

    except Exception as e:
        logger.error("Failed to generate anomaly insight", extra={"extra_data": {"error": str(e)}})
        return {
            "analysis": "Unable to generate detailed analysis.",
            "recommendation": "Review the reviews from this date manually."
        }


MENTION_EXTRACTION_PROMPT = """You are a mention extractor for Saudi business reviews (cafes, restaurants, hotels, retail).

Extract SPECIFIC products and CATEGORIES mentioned in reviews.

PRODUCTS = SPECIFIC menu items ONLY (items with a price on a menu)
  ✓ Extract: "Spanish Latte", "V60", "كرواسون", "تشيز كيك", "برجر واجيو", "آيس أمريكانو"
  ✗ Do NOT extract generic terms as products: "coffee", "قهوة", "drinks", "food", "مشروبات"

ASPECTS = ALL CATEGORIES (product categories + service categories)
  Product categories: "coffee", "قهوة", "juice", "عصير", "desserts", "حلويات", "breakfast", "فطور"
  Service categories: "service", "خدمة", "price", "سعر", "ambiance", "أجواء", "cleanliness", "نظافة", "staff", "موظفين", "parking", "مواقف"

RULES:
1. Extract ONLY items explicitly mentioned - never assume or hallucinate
2. If someone says "القهوة ممتازة" (coffee is excellent) → aspect: "القهوة" (it's a category, not a specific item)
3. If someone says "السبانش لاتيه لذيذ" (Spanish Latte is delicious) → product: "السبانش لاتيه" (specific menu item)
4. Keep original text as mentioned (Arabic or English)
5. Determine sentiment for EACH mention based on context
6. If mentioned neutrally (just stated, no opinion), use "neutral"
7. Maximum 10 mentions per review (prioritize most significant)
8. Do NOT extract: people names, general phrases like "the place", "المكان", objects like "customers", "employees"

EXAMPLES:
- "السبانش لاتيه لذيذ" → product: "السبانش لاتيه", sentiment: positive
- "the V60 was bitter" → product: "V60", sentiment: negative
- "القهوة عندهم ممتازة" → aspect: "القهوة", sentiment: positive (category, not specific item)
- "الخدمة بطيئة" → aspect: "الخدمة", sentiment: negative
- "أسعارهم مرتفعة" → aspect: "الأسعار", sentiment: negative
- "great coffee" → aspect: "coffee", sentiment: positive (category)
- "loved the flat white" → product: "flat white", sentiment: positive (specific item)

OUTPUT FORMAT:
Return ONLY valid JSON (no markdown, no explanation):
{
  "products": [
    {"text": "specific menu item name", "sentiment": "positive|negative|neutral"}
  ],
  "aspects": [
    {"text": "category name", "sentiment": "positive|negative|neutral"}
  ]
}

If no products or aspects found, return empty arrays."""


def extract_mentions(review_text: str) -> dict:
    """
    Extract product and aspect mentions from review text.

    Args:
        review_text: The review text to analyze

    Returns:
        Dict with 'products' and 'aspects' lists, each containing
        {'text': str, 'sentiment': str} items.
        Returns empty lists on error.
    """
    if not review_text or not review_text.strip():
        return {"products": [], "aspects": []}

    prompt = f"Extract product and aspect mentions from this review:\n\n{review_text}\n\nReturn ONLY the JSON."

    logger.debug("Extracting mentions", extra={"extra_data": {"text_length": len(review_text)}})

    try:
        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=[
                {"role": "system", "content": MENTION_EXTRACTION_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500
        )

        content = response.choices[0].message.content.strip()

        # Clean up markdown if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        # Parse JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON in response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
            else:
                logger.warning("Could not parse mention extraction response",
                             extra={"extra_data": {"content": content[:200]}})
                return {"products": [], "aspects": []}

        # Validate and normalize structure
        products = result.get("products", [])
        aspects = result.get("aspects", [])

        # Ensure each item has required fields
        valid_products = []
        for p in products:
            if isinstance(p, dict) and p.get("text"):
                valid_products.append({
                    "text": str(p["text"]).strip(),
                    "sentiment": p.get("sentiment", "neutral")
                })

        valid_aspects = []
        for a in aspects:
            if isinstance(a, dict) and a.get("text"):
                valid_aspects.append({
                    "text": str(a["text"]).strip(),
                    "sentiment": a.get("sentiment", "neutral")
                })

        logger.debug("Mentions extracted",
                    extra={"extra_data": {"products": len(valid_products), "aspects": len(valid_aspects)}})

        return {"products": valid_products, "aspects": valid_aspects}

    except Exception as e:
        logger.error(f"Mention extraction failed: {e}", extra={"extra_data": {"error": str(e)}})
        return {"products": [], "aspects": []}


# Prompt for taxonomy-aware sentiment analysis
# Used after taxonomy is approved - LLM knows the approved products/categories
TAXONOMY_AWARE_PROMPT = """You are a review analysis assistant for Saudi businesses.

You will receive:
1. The original review text
2. The APPROVED products for this specific business
3. The APPROVED categories for this specific business

Your job is to:
1. Determine overall sentiment (positive/neutral/negative) with confidence score
2. Identify which APPROVED products are mentioned in this review
3. Identify which APPROVED categories are relevant to this review
4. Generate summaries that reference the SPECIFIC products/categories mentioned
5. Generate a suggested reply that addresses the SPECIFIC products/issues

RULES:
- Match review content to products/categories from the approved lists
- If a product variant is mentioned (e.g., "سبانش لاتيه" for "Spanish Latte"), still match it
- Summaries MUST mention specific product/category names, not generic terms
- Reply should acknowledge specific products praised or complained about
- Use Saudi dialect naturally in Arabic reply (ياهلا، نقدر، نعتذر منك)

LANGUAGE DETECTION:
- ar: Arabic (formal or any dialect)
- en: English
- arabizi: Arabic written in English letters

URGENCY RULES:
Set urgent=true if:
- Sentiment is negative AND score > 0.7
- Review mentions health/safety issue
- Review threatens to report or escalate

ACTION NOTE GUIDELINES (internal note for business owner, NOT for the customer):
- Set needs_action=true ONLY for negative or urgent reviews that warrant a follow-up action
- For positive/neutral reviews, set needs_action=false and leave action_ar/action_en as empty strings
- Reference the SPECIFIC product or category when suggesting compensation (e.g., "تعويض بـ Spanish Latte مجاني")
- Suggest specific compensation when appropriate: free item, discount, invitation to revisit
- Flag for manager escalation if health/safety related
- Keep concise (under 20 words)

OUTPUT FORMAT:
Return ONLY valid JSON (no markdown, no explanation):
{
  "sentiment": "positive" | "neutral" | "negative",
  "score": 0.0-1.0,
  "matched_products": [
    {"id": "uuid", "sentiment": "positive|negative|neutral"}
  ],
  "matched_categories": [
    {"id": "uuid", "sentiment": "positive|negative|neutral"}
  ],
  "language": "ar" | "en" | "arabizi",
  "urgent": true | false,
  "summary_ar": "ملخص يذكر المنتجات المحددة بالاسم",
  "summary_en": "Summary mentioning specific product names",
  "suggested_reply_ar": "رد يذكر المنتج أو المشكلة المحددة",
  "needs_action": true | false,
  "action_ar": "ملاحظة داخلية للإدارة أو فارغ",
  "action_en": "Internal action note or empty string"
}

NOTE: For matched_products and matched_categories, specify the sentiment for EACH item
based on how it was mentioned in the review (positive praise, negative complaint, or neutral mention)."""


def _format_taxonomy_for_prompt(products: list, categories: list) -> str:
    """Format approved products and categories for the LLM prompt."""
    lines = []

    if products:
        lines.append("APPROVED PRODUCTS:")
        for p in products:
            variants = p.get("variants", [])
            variant_str = f" (also: {', '.join(variants)})" if variants else ""
            lines.append(f"  - ID: {p['id']} | Name: {p['name']}{variant_str}")

    if categories:
        lines.append("\nAPPROVED CATEGORIES:")
        for c in categories:
            lines.append(f"  - ID: {c['id']} | Name: {c['name']}")

    if not lines:
        lines.append("No approved products or categories yet.")

    return "\n".join(lines)


def analyze_with_taxonomy(
    review_text: str,
    approved_products: list,
    approved_categories: list,
    rating: int = None
) -> dict:
    """
    Analyze review with knowledge of approved taxonomy.

    The LLM knows what products/categories exist for this business
    and can match the review to specific approved items, generating
    more accurate and specific summaries/replies.

    Args:
        review_text: The review text to analyze
        approved_products: List of dicts with {id, name, variants}
        approved_categories: List of dicts with {id, name}
        rating: Optional star rating (1-5)

    Returns:
        Dict with sentiment, score, matched_product_ids, matched_category_ids,
        language, urgent, summary_ar, summary_en, suggested_reply_ar.
        Compatible with ReviewAnalysis table schema.
    """
    if not review_text or not review_text.strip():
        return {
            "sentiment": "neutral",
            "score": 0.5,
            "matched_product_ids": [],
            "matched_category_ids": [],
            "language": "ar",
            "urgent": False,
            "summary_ar": "",
            "summary_en": "",
            "suggested_reply_ar": "",
        }

    # Format taxonomy context for the prompt
    taxonomy_context = _format_taxonomy_for_prompt(approved_products, approved_categories)

    # Build user prompt
    prompt = f"""TAXONOMY FOR THIS BUSINESS:
{taxonomy_context}

REVIEW TO ANALYZE"""
    if rating:
        prompt += f" (rating: {rating}/5)"
    prompt += f""":\n\n{review_text}

Analyze this review and match it to the approved products/categories above.
Return ONLY the JSON analysis."""

    logger.debug("Calling LLM with taxonomy context",
                extra={"extra_data": {
                    "model": VLLM_MODEL,
                    "text_length": len(review_text),
                    "products_count": len(approved_products),
                    "categories_count": len(approved_categories)
                }})

    try:
        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=[
                {"role": "system", "content": TAXONOMY_AWARE_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1000
        )

        content = response.choices[0].message.content.strip()

        # Clean up markdown if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        # Parse JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
            else:
                logger.error("Failed to parse taxonomy-aware analysis",
                           extra={"extra_data": {"content": content[:200]}})
                raise ValueError(f"Could not parse JSON: {content}")

        # Validate and set defaults for required fields
        result.setdefault("sentiment", "neutral")
        result.setdefault("score", 0.5)
        result.setdefault("matched_products", [])
        result.setdefault("matched_categories", [])
        result.setdefault("language", "ar")
        result.setdefault("urgent", False)
        result.setdefault("summary_ar", "")
        result.setdefault("summary_en", "")
        result.setdefault("suggested_reply_ar", "")

        # Extract IDs for backward compatibility
        result["matched_product_ids"] = [
            m["id"] if isinstance(m, dict) else m
            for m in result.get("matched_products", [])
        ]
        result["matched_category_ids"] = [
            m["id"] if isinstance(m, dict) else m
            for m in result.get("matched_categories", [])
        ]

        # Convert to topics_positive/topics_negative for backward compatibility
        # Now uses per-item sentiment from LLM response
        result["topics_positive"] = []
        result["topics_negative"] = []

        # Map matched categories to topics based on their individual sentiment
        for match in result.get("matched_categories", []):
            if isinstance(match, dict):
                cat_id = match.get("id")
                cat_sentiment = match.get("sentiment", "neutral")
            else:
                # Handle legacy format (just IDs)
                cat_id = match
                cat_sentiment = result["sentiment"]  # Fallback to overall

            # Find category name
            for cat in approved_categories:
                if cat["id"] == cat_id:
                    topic_name = cat["name"].lower()
                    if cat_sentiment == "positive":
                        result["topics_positive"].append(topic_name)
                    elif cat_sentiment == "negative":
                        result["topics_negative"].append(topic_name)
                    break

        logger.debug("Taxonomy-aware analysis complete",
                    extra={"extra_data": {
                        "sentiment": result.get("sentiment"),
                        "score": result.get("score"),
                        "matched_products": len(result.get("matched_product_ids", [])),
                        "matched_categories": len(result.get("matched_category_ids", []))
                    }})

        return result

    except Exception as e:
        logger.error(f"Taxonomy-aware analysis failed: {e}",
                    extra={"extra_data": {"error": str(e)}})
        # Fall back to original analysis
        logger.info("Falling back to original analyze_review()")
        return analyze_review(review_text, rating)


if __name__ == "__main__":
    # Test with sample review
    test_review = "القهوة ممتازة والمكان هادي بس الخدمة بطيئة شوي"
    logger.info(f"Testing with review: {test_review}")

    result = analyze_review(test_review, rating=4)
    print("Analysis:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\nMentions:")
    mentions = extract_mentions(test_review)
    print(json.dumps(mentions, ensure_ascii=False, indent=2))
