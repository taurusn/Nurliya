import json
from openai import OpenAI
from config import VLLM_BASE_URL, VLLM_API_KEY, VLLM_MODEL

# Configure OpenAI client to point to vLLM
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
  "suggested_reply_ar": "رد مقترح بالسعودي"
}"""


def analyze_review(review_text: str, rating: int = None) -> dict:
    """Analyze a single review and return structured data."""

    # Build prompt
    prompt = f"Analyze this review"
    if rating:
        prompt += f" (rating: {rating}/5)"
    prompt += f":\n\n{review_text}\n\nReturn ONLY the JSON analysis, nothing else."

    # Call vLLM via OpenAI-compatible API
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
            raise ValueError(f"Could not parse JSON from response: {content}") from e

    # Validate required fields
    required = ["sentiment", "score", "topics_positive", "topics_negative",
                "language", "urgent", "summary_ar", "summary_en", "suggested_reply_ar"]
    for field in required:
        if field not in result:
            result[field] = [] if "topics" in field else ("" if "summary" in field or "reply" in field else False)

    return result


if __name__ == "__main__":
    # Test with sample review
    test_review = "القهوة ممتازة والمكان هادي بس الخدمة بطيئة شوي"
    print(f"Testing with: {test_review}\n")

    result = analyze_review(test_review, rating=4)
    print(json.dumps(result, ensure_ascii=False, indent=2))
