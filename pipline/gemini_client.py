import json
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """You are a review analysis assistant for Saudi businesses including cafes, restaurants, hotels, and retail stores.

Your job is to analyze customer reviews and extract structured data by calling the save_review_analysis function.

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
- Do not be defensive or make excuses"""

# Tool definition for structured output
ANALYSIS_TOOL = {
    "name": "save_review_analysis",
    "description": "Save structured analysis of a customer review",
    "parameters": {
        "type": "object",
        "properties": {
            "sentiment": {
                "type": "string",
                "enum": ["positive", "neutral", "negative"],
                "description": "Overall sentiment of the review"
            },
            "score": {
                "type": "number",
                "description": "Confidence score from 0.0 to 1.0"
            },
            "topics_positive": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Positive topics mentioned"
            },
            "topics_negative": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Negative topics mentioned"
            },
            "language": {
                "type": "string",
                "enum": ["ar", "en", "arabizi"],
                "description": "Language of the review"
            },
            "urgent": {
                "type": "boolean",
                "description": "Whether this review needs urgent attention"
            },
            "summary_ar": {
                "type": "string",
                "description": "One sentence summary in Arabic"
            },
            "summary_en": {
                "type": "string",
                "description": "One sentence summary in English"
            },
            "suggested_reply_ar": {
                "type": "string",
                "description": "Suggested reply in Saudi Arabic dialect"
            }
        },
        "required": [
            "sentiment", "score", "topics_positive", "topics_negative",
            "language", "urgent", "summary_ar", "summary_en", "suggested_reply_ar"
        ]
    }
}


def get_model():
    """Get configured Gemini model with tools."""
    return genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        tools=[{"function_declarations": [ANALYSIS_TOOL]}]
    )


def analyze_review(review_text: str, rating: int = None) -> dict:
    """Analyze a single review and return structured data."""
    model = get_model()

    # Build prompt
    prompt = f"Analyze this review"
    if rating:
        prompt += f" (rating: {rating}/5)"
    prompt += f":\n\n{review_text}"

    # Call Gemini
    response = model.generate_content(prompt)

    # Extract function call
    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                if fc.name == "save_review_analysis":
                    # Convert protobuf to dict
                    args = dict(fc.args)
                    # Convert repeated fields to lists
                    if 'topics_positive' in args:
                        args['topics_positive'] = list(args['topics_positive'])
                    if 'topics_negative' in args:
                        args['topics_negative'] = list(args['topics_negative'])
                    return args

    # Fallback: try to parse text response as JSON
    try:
        return json.loads(response.text)
    except:
        raise ValueError(f"Could not extract analysis from response: {response.text}")


if __name__ == "__main__":
    # Test with sample review
    test_review = "القهوة ممتازة والمكان هادي بس الخدمة بطيئة شوي"
    print(f"Testing with: {test_review}\n")

    result = analyze_review(test_review, rating=4)
    print(json.dumps(result, ensure_ascii=False, indent=2))
