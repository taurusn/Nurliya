# Menu Images — Implementation Progress

## Phase 1: Set Up MinIO ✅
- [x] Added MinIO service to `docker-compose.yml` (ports 9000 API, 9001 console)
- [x] Added `minio_data` volume
- [x] Added MinIO config to `pipline/config.py` (MINIO_ENDPOINT, ACCESS_KEY, SECRET_KEY, BUCKET, PUBLIC_URL)
- [x] Added `storage.nurliya.com` route to `/etc/cloudflared/config.yml`
- [x] DNS CNAME created for `storage.nurliya.com`
- [x] Verified: MinIO healthy, tunnel working, other services unaffected
- Commit: `bbf5ecb` — `feat: add MinIO object storage for menu images (Phase 1)`

## Phase 2: Modify Go Scraper — Fetch All Menu Images ✅
- [x] Add `MenuImages []string` field to `Entry` struct in `entry.go`
- [x] Add `menu_images` to `CsvHeaders()` and `CsvRow()` in `entry.go`
- [x] Add `findGooglePhotoURLs()` helper to extract URLs from `darray[171]` Menu category data
- [x] Add `normalizePhotoURL()` helper for deduplication across data + DOM sources
- [x] Add `extractMenuPhotos()` in `place.go` — clicks Menu tab, scrolls carousels, collects all photo URLs
- [x] Wire into `BrowserActions()` and `Process()` with dedup merge of data + browser sources
- [x] Upscale thumbnails from `w112-h112` to `w1200-h1200` for full-size images
- [x] Tested with real scrape — reliably extracts 3-24 menu photos per place
- Commit: see below

### How it works:
1. **Data extraction** (`entry.go`): `EntryFromJSON()` walks `darray[171][0]` to find the "Menu" category and recursively extracts all `googleusercontent.com/p/` URLs
2. **DOM extraction** (`place.go`): `extractMenuPhotos()` scrolls page → clicks "Menu" tab → collects `img.DaSXdd` URLs from all `button.K4UgGe` across all carousels → scrolls + clicks Next in each carousel to reveal more items
3. **Merge** (`place.go` Process): deduplicates browser + data URLs using `normalizePhotoURL()` (strips size suffix)

## Phase 3: Pipeline — Download & Store Images to MinIO ⬜
- [ ] Create `pipline/image_store.py`
- [ ] Add `minio` to `requirements.txt`
- [ ] Add `PlaceMenuImage` model to `database.py`
- [ ] Modify `csv_parser.py` to download menu images after saving place

## Phase 4: API Endpoints ⬜
- [ ] Add `GET /api/onboarding/taxonomies/{id}/menu-images` to `api.py`

## Phase 5: Onboarding Portal UI ⬜
- [ ] Add "Menu Images" section/tab in taxonomy editor
