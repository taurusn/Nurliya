# Nurliya — Product Requirements Document

## Product Overview

**Name:** Nurliya (نورليّة)

**Purpose:** AI-powered sentiment analysis platform for Saudi businesses to understand and respond to Google Maps reviews.

**Target Users:** Cafes, restaurants, hotels, retail stores in Saudi Arabia.

---

## Core Value

- Analyze customer reviews (Arabic, English, Arabizi)
- Extract sentiment, topics, urgency
- Generate Saudi-friendly suggested replies
- Store structured insights in database

---

## Architecture

```
[CSV from Scraper]
        ↓
[CSV Parser]
        ↓
[PostgreSQL] ← place + raw reviews
        ↓
[Pipeline Worker]
        ↓
[Gemini API] ← one review at a time
        ↓
[PostgreSQL] ← analysis results
        ↓
[FastAPI] ← serve results
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| API | FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| LLM | Gemini API (Vertex AI) |
| Parser | Pandas |
| Scraper | External repo (CSV output) |

---

## Database Schema

```sql
-- Places
CREATE TABLE places (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255),
    place_id VARCHAR(255) UNIQUE,
    category VARCHAR(100),
    address TEXT,
    rating DECIMAL(2,1),
    review_count INT,
    reviews_per_rating JSONB,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Jobs
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id UUID REFERENCES places(id),
    status VARCHAR(50) DEFAULT 'pending',
    total_reviews INT DEFAULT 0,
    processed_reviews INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Reviews (raw from scraper)
CREATE TABLE reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id UUID REFERENCES places(id),
    job_id UUID REFERENCES jobs(id),
    author VARCHAR(255),
    rating INT,
    text TEXT,
    review_date VARCHAR(50),
    profile_picture TEXT,
    images JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Analysis (Gemini output)
CREATE TABLE review_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID REFERENCES reviews(id) UNIQUE,
    sentiment VARCHAR(20),
    score DECIMAL(3,2),
    topics_positive TEXT[],
    topics_negative TEXT[],
    language VARCHAR(20),
    urgent BOOLEAN DEFAULT FALSE,
    summary_ar TEXT,
    summary_en TEXT,
    suggested_reply_ar TEXT,
    raw_response JSONB,
    analyzed_at TIMESTAMP DEFAULT NOW()
);
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/jobs` | Upload CSV, start pipeline |
| GET | `/api/jobs/{id}` | Get job status |
| GET | `/api/places` | List all places |
| GET | `/api/places/{id}` | Get place details |
| GET | `/api/places/{id}/reviews` | Get reviews + analysis |
| GET | `/api/places/{id}/stats` | Get sentiment stats |

---

## Gemini Configuration

### System Prompt

```
You are a review analysis assistant for Saudi businesses including cafes, restaurants, hotels, and retail stores.

Your job is to analyze customer reviews and extract structured data by calling the save_review_analysis tool.

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
```

### Tool Definition

```json
{
  "name": "save_review_analysis",
  "description": "Save structured analysis of a customer review",
  "parameters": {
    "type": "object",
    "properties": {
      "sentiment": {
        "type": "string",
        "enum": ["positive", "neutral", "negative"]
      },
      "score": {
        "type": "number",
        "description": "Confidence 0.0 to 1.0"
      },
      "topics_positive": {
        "type": "array",
        "items": {"type": "string"}
      },
      "topics_negative": {
        "type": "array",
        "items": {"type": "string"}
      },
      "language": {
        "type": "string",
        "enum": ["ar", "en", "arabizi"]
      },
      "urgent": {
        "type": "boolean"
      },
      "summary_ar": {"type": "string"},
      "summary_en": {"type": "string"},
      "suggested_reply_ar": {"type": "string"}
    },
    "required": [
      "sentiment", "score", "topics_positive", "topics_negative",
      "language", "urgent", "summary_ar", "summary_en", "suggested_reply_ar"
    ]
  }
}
```

### Example Output

```json
{
  "sentiment": "negative",
  "score": 0.9,
  "topics_positive": ["quality"],
  "topics_negative": ["service", "wait_time"],
  "language": "ar",
  "urgent": true,
  "summary_ar": "استياء العميل من بطء الخدمة رغم جودة القهوة",
  "summary_en": "Customer dissatisfied with slow service despite good coffee",
  "suggested_reply_ar": "ياهلا فيك، نعتذر منك جداً على التأخير. ملاحظتك محل اهتمامنا وراح نشتغل عليها فوراً."
}
```

---

## Project Structure

```
nurliya/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── models.py
│   ├── parser/
│   │   ├── __init__.py
│   │   └── csv_parser.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── gemini.py
│   │   └── runner.py
│   └── api/
│       ├── __init__.py
│       ├── routes.py
│       └── schemas.py
├── data/
│   └── results.csv
├── scripts/
│   └── init_db.py
├── credentials.json
├── .env
├── .gitignore
├── requirements.txt
└── main.py
```

---

## Development Phases

### Phase 1: Foundation

| Step | Task | Description |
|------|------|-------------|
| 1.1 | Project setup | Create folders, files |
| 1.2 | Dependencies | Install requirements |
| 1.3 | PostgreSQL | Run local DB (Docker) |
| 1.4 | Config | `.env`, `config.py` |
| 1.5 | DB connection | `database.py` |
| 1.6 | Models | `models.py` (SQLAlchemy) |
| 1.7 | Init script | Create tables |

**Deliverable:** Empty DB with schema ready

---

### Phase 2: CSV Parser

| Step | Task | Description |
|------|------|-------------|
| 2.1 | Load CSV | Read with Pandas |
| 2.2 | Parse place | Extract place metadata |
| 2.3 | Parse reviews | Extract `user_reviews` JSON |
| 2.4 | Save place | Insert to `places` table |
| 2.5 | Save reviews | Insert to `reviews` table |
| 2.6 | Test | Parse sample CSV |

**Deliverable:** CSV → DB working

---

### Phase 3: Gemini Integration

| Step | Task | Description |
|------|------|-------------|
| 3.1 | Gemini client | Setup Vertex AI |
| 3.2 | Tool definition | Define `save_review_analysis` |
| 3.3 | System prompt | Implement full prompt |
| 3.4 | Analyze function | Single review → structured output |
| 3.5 | Save analysis | Insert to `review_analysis` table |
| 3.6 | Test | Analyze sample reviews |

**Deliverable:** Review → Gemini → DB working

---

### Phase 4: Pipeline

| Step | Task | Description |
|------|------|-------------|
| 4.1 | Job creation | Create job record |
| 4.2 | Pipeline runner | CSV → Parse → Gemini → Save |
| 4.3 | Progress tracking | Update `processed_reviews` |
| 4.4 | Error handling | Catch failures, log errors |
| 4.5 | Status updates | pending → processing → completed |
| 4.6 | Test | Full pipeline end-to-end |

**Deliverable:** Complete pipeline working locally

---

### Phase 5: API

| Step | Task | Description |
|------|------|-------------|
| 5.1 | FastAPI setup | `main.py` with app |
| 5.2 | Schemas | Pydantic models |
| 5.3 | POST `/jobs` | Upload CSV, trigger pipeline |
| 5.4 | GET `/jobs/{id}` | Return job status |
| 5.5 | GET `/places/{id}/reviews` | Return reviews + analysis |
| 5.6 | Background tasks | Run pipeline async |
| 5.7 | Test | API endpoints working |

**Deliverable:** REST API serving results

---

### Phase 6: Polish (Optional)

| Step | Task | Description |
|------|------|-------------|
| 6.1 | Stats endpoint | Sentiment aggregation |
| 6.2 | Filtering | Filter by sentiment, date |
| 6.3 | Pagination | Paginate reviews |
| 6.4 | Rate limiting | Gemini API limits |
| 6.5 | Logging | Structured logs |
| 6.6 | Docker | Containerize app |

**Deliverable:** Production-ready POC

---

## Timeline (Estimated)

| Phase | Duration |
|-------|----------|
| Phase 1: Foundation | 1 day |
| Phase 2: CSV Parser | 1 day |
| Phase 3: Gemini Integration | 1 day |
| Phase 4: Pipeline | 1-2 days |
| Phase 5: API | 1-2 days |
| Phase 6: Polish | 2-3 days |
| **Total** | **~7-10 days** |

---

## Success Criteria

| Criteria | Target |
|----------|--------|
| Parse CSV | ✓ Place + reviews saved |
| Gemini accuracy | >90% correct sentiment |
| Arabic support | Handles dialect + Arabizi |
| Pipeline | End-to-end working |
| API | All endpoints functional |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Gemini rate limits | Add delay between calls |
| Arabic accuracy | Test early, refine prompt |
| Large CSVs | Process in batches |
| DB connection drops | Add retry logic |

---

## Configuration Files

### requirements.txt

```
python-dotenv>=1.0.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
google-cloud-aiplatform>=1.38.0
fastapi>=0.109.0
uvicorn>=0.27.0
pandas>=2.0.0
```

### .env

```
DATABASE_URL=postgresql://nurliya:nurliya123@localhost:5432/nurliya
GOOGLE_CLOUD_PROJECT=nurliya
GOOGLE_APPLICATION_CREDENTIALS=./credentials.json
```

### .gitignore

```
.env
credentials.json
__pycache__/
*.pyc
data/*.csv
.venv/
```

### Docker (PostgreSQL)

```bash
docker run --name nurliya-db \
  -e POSTGRES_USER=nurliya \
  -e POSTGRES_PASSWORD=nurliya123 \
  -e POSTGRES_DB=nurliya \
  -p 5432:5432 \
  -d postgres:16
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01-30 | Initial PRD |
