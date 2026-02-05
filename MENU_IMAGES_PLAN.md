# Menu Images Scraping & Storage Plan

**Created**: 2026-02-05
**Branch**: `feature/taxonomy-system`
**Status**: Not started — plan only

---

## Goal

Allow OS (operations team) to see menu images from Google Maps places during taxonomy review in the onboarding portal. This helps them understand what products the place actually sells when auditing/editing the taxonomy.

---

## Current State

### What the scraper already does
- Go scraper at `google-maps-scraper/` outputs CSV with `images` column
- `images` column contains JSON array of `{title, image}` objects
- Each object is ONE thumbnail per Google Maps photo tab (All, Menu, Food & drink, Latte, etc.)
- Example: `{"title": "Menu", "image": "https://lh3.googleusercontent.com/p/AF1QipO5KO43..."}`
- **Problem**: Only gets 1 cover image per category, NOT all photos in the "Menu" tab
- The `menu` field is a link to external ordering page (HungerStation etc.), not menu photos

### Key scraper files
- `google-maps-scraper/gmaps/entry.go` — `Image` struct: `{Title string, Image string}`
- `google-maps-scraper/gmaps/place.go` — Place data extraction, images from `darray[171]`
- `google-maps-scraper/gmaps/reviews.go` — Review image extraction (RPC + DOM)
- `google-maps-scraper/runner/runner.go` — Job runner config
- `google-maps-scraper/web/` — HTTP API for scraper

### Pipeline files
- `pipline/csv_parser.py` — Parses CSV, currently ignores `images`/`menu`/`thumbnail` columns (not saved to metadata)
- `pipline/orchestrator.py` — Runs scrape pipeline, calls csv_parser
- `pipline/scraper_client.py` — Python client for Go scraper API
- `pipline/database.py` — SQLAlchemy models (Place, Review, etc.)

### Frontend
- `onboarding-portal/src/app/[taxonomyId]/page.tsx` — Taxonomy editor
- `onboarding-portal/src/components/ImportModal.tsx` — Import/export modal
- `onboarding-portal/src/lib/api.ts` — API client

### Docker
- `docker-compose.yml` — All services defined here
- Scraper runs as `nurliya-scraper` container
- All services on `nurliya-network` Docker network

---

## Implementation Plan

### Phase 1: Set Up MinIO

**Why MinIO**: Google image URLs expire. We need permanent storage for menu images. MinIO is S3-compatible, self-hosted, lightweight.

#### 1A: Add MinIO to docker-compose.yml
```yaml
minio:
  image: minio/minio:latest
  container_name: nurliya-minio
  command: server /data --console-address ":9001"
  environment:
    MINIO_ROOT_USER: ${MINIO_ROOT_USER:-nurliya}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-nurliya123}
  ports:
    - "9000:9000"   # API
    - "9001:9001"   # Console
  volumes:
    - minio_data:/data
  networks:
    - nurliya-network
  healthcheck:
    test: ["CMD", "mc", "ready", "local"]
    interval: 10s
    timeout: 5s
    retries: 3
```

Add `minio_data` to volumes section.

#### 1B: Add config
In `pipline/config.py`:
```python
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "nurliya")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "nurliya123")
MINIO_BUCKET = "menu-images"
MINIO_PUBLIC_URL = os.environ.get("MINIO_PUBLIC_URL", "https://storage.nurliya.com")
```

#### 1C: Add Cloudflare tunnel for MinIO API
In `~/.cloudflared/config.yml`, add:
```yaml
- hostname: storage.nurliya.com
  service: http://localhost:9000
```

---

### Phase 2: Modify Go Scraper — Fetch All Menu Images

**Key change**: When extracting images from `darray[171]`, the scraper currently gets one image per category. Need to modify to fetch ALL images from the "Menu" category.

#### Approach
Google Maps photo tabs use an RPC endpoint to load photos by category. The scraper needs to:

1. Identify the "Menu" photo category from the place data
2. Make additional RPC requests to `https://www.google.com/maps/rpc/listphotos` (or similar) to fetch all photos in the Menu category
3. Store them in a new field like `MenuImages []string` (array of URLs)

#### Files to modify
- `google-maps-scraper/gmaps/entry.go` — Add `MenuImages []string` field to `Entry` struct
- `google-maps-scraper/gmaps/place.go` — Add menu image extraction logic
- `google-maps-scraper/gmaps/export.go` — Add `menu_images` CSV column

#### Research needed
- Inspect Google Maps network requests when clicking "Menu" photo tab
- Find the RPC endpoint and parameters for category-filtered photo listing
- May need Playwright interaction to load menu photos

---

### Phase 3: Pipeline — Download & Store Images to MinIO

#### 3A: Create `pipline/image_store.py`
```python
from minio import Minio
import requests
import uuid

class ImageStore:
    def __init__(self):
        self.client = Minio(MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, secure=False)
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(MINIO_BUCKET):
            self.client.make_bucket(MINIO_BUCKET)
            # Set public read policy for serving images

    def download_and_store(self, image_url: str, place_id: str) -> str:
        """Download image from Google and store in MinIO. Returns stored path."""
        response = requests.get(image_url)
        filename = f"{place_id}/menu/{uuid.uuid4()}.jpg"
        self.client.put_object(MINIO_BUCKET, filename, response.content, ...)
        return f"{MINIO_PUBLIC_URL}/{MINIO_BUCKET}/{filename}"
```

#### 3B: Add to requirements.txt
```
minio>=7.0.0
```

#### 3C: Database schema
Add to `pipline/database.py`:
```python
class PlaceMenuImage(Base):
    __tablename__ = "place_menu_images"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    place_id = Column(UUID, ForeignKey("places.id"))
    image_url = Column(Text)          # MinIO URL (permanent)
    original_url = Column(Text)       # Google URL (may expire)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
```

#### 3D: Modify csv_parser.py
After saving place, download menu images:
```python
menu_images = parse_json_field(row.get("menu_images")) or []
for img_url in menu_images:
    stored_url = image_store.download_and_store(img_url, place_id)
    # Save PlaceMenuImage record
```

---

### Phase 4: API Endpoints

In `pipline/api.py`:

#### GET /api/onboarding/taxonomies/{id}/menu-images
Returns menu images for the taxonomy's place(s):
```json
{
  "images": [
    {"id": "...", "url": "https://storage.nurliya.com/menu-images/...", "place_name": "..."}
  ]
}
```

---

### Phase 5: Onboarding Portal UI

In `onboarding-portal/src/app/[taxonomyId]/page.tsx`:

Add a "Menu Images" section/tab in the taxonomy editor that shows:
- Grid of menu images from the place
- Helps OS identify products when building taxonomy
- Could be a sidebar panel or collapsible section

---

## Bugs Fixed This Session (Context)

1. **Race condition in `update_job_progress()`** (`pipline/worker.py:586`)
   - Two workers could read same `processed_reviews`, both increment in Python, lose 1 count
   - Fixed: atomic SQL `UPDATE SET processed_reviews = processed_reviews + 1`
   - Jobs were stuck at "processing" forever

2. **Draft template export missing products** (`onboarding-portal/src/components/ImportModal.tsx:96`)
   - `buildTemplateFromDraft()` only exported parent categories, missed subcategory products
   - Products use `discovered_category_id` not `assigned_category_id` after clustering
   - Fixed: collect products from parent + children, fallback to `discovered_category_id`

3. **Missing DB columns** — `is_reclustering`, `source` columns from Phase 4 not applied to existing DB
   - Manually ran ALTER TABLE (create_tables only creates new tables, doesn't add columns)
   - Applied: `place_taxonomies.is_reclustering`, `taxonomy_categories.source`, `taxonomy_products.source`

## Current DB State
- 2 places (Specialty Bean Roastery — 2 branches)
- 1,233 reviews processed
- 2,027 mentions extracted
- Draft taxonomy: 15 categories, 20 products
- Taxonomy ID: `47d0b369-f998-491e-a38b-d925355e70d5`
- All on branch `feature/taxonomy-system`, latest commit `53b2b63`

## Credentials & Access
- DB: `postgresql://nurliya:nurliya123@localhost:5432/nurliya` (via Docker)
- Qdrant: `http://localhost:6333`
- RabbitMQ: `nurliya:nurliya123` port 5672
- API login: `test@nurliya.com` / `hatimhatim` (field is `access_token` not `token`)
- Cloudflare tunnel config: `~/.cloudflared/config.yml`
- All services running in Docker via `docker-compose.yml`
