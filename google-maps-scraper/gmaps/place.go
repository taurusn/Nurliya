package gmaps

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/gosom/scrapemate"

	"github.com/gosom/google-maps-scraper/exiter"
)

type PlaceJobOptions func(*PlaceJob)

type PlaceJob struct {
	scrapemate.Job

	UsageInResultststs  bool
	ExtractEmail        bool
	ExitMonitor         exiter.Exiter
	ExtractExtraReviews bool
}

func NewPlaceJob(parentID, langCode, u string, extractEmail, extraExtraReviews bool, opts ...PlaceJobOptions) *PlaceJob {
	const (
		defaultPrio       = scrapemate.PriorityMedium
		defaultMaxRetries = 3
	)

	job := PlaceJob{
		Job: scrapemate.Job{
			ID:         uuid.New().String(),
			ParentID:   parentID,
			Method:     "GET",
			URL:        u,
			URLParams:  map[string]string{"hl": langCode},
			MaxRetries: defaultMaxRetries,
			Priority:   defaultPrio,
		},
	}

	job.UsageInResultststs = true
	job.ExtractEmail = extractEmail
	job.ExtractExtraReviews = extraExtraReviews

	for _, opt := range opts {
		opt(&job)
	}

	return &job
}

func WithPlaceJobExitMonitor(exitMonitor exiter.Exiter) PlaceJobOptions {
	return func(j *PlaceJob) {
		j.ExitMonitor = exitMonitor
	}
}

func (j *PlaceJob) Process(_ context.Context, resp *scrapemate.Response) (any, []scrapemate.IJob, error) {
	defer func() {
		resp.Document = nil
		resp.Body = nil
		resp.Meta = nil
	}()

	raw, ok := resp.Meta["json"].([]byte)
	if !ok {
		return nil, nil, fmt.Errorf("could not convert to []byte")
	}

	entry, err := EntryFromJSON(raw)
	if err != nil {
		return nil, nil, err
	}

	entry.ID = j.ParentID

	if entry.Link == "" {
		entry.Link = j.GetURL()
	}

	// Handle RPC-based reviews
	allReviewsRaw, ok := resp.Meta["reviews_raw"].(FetchReviewsResponse)
	if ok && len(allReviewsRaw.pages) > 0 {
		entry.AddExtraReviews(allReviewsRaw.pages)
	}

	// Handle DOM-based reviews (fallback)
	domReviews, ok := resp.Meta["dom_reviews"].([]DOMReview)
	if ok && len(domReviews) > 0 {
		convertedReviews := ConvertDOMReviewsToReviews(domReviews)
		entry.UserReviewsExtended = append(entry.UserReviewsExtended, convertedReviews...)
	}

	// Merge browser-extracted menu images with data-extracted ones
	if browserMenuImages, ok := resp.Meta["menu_images"].([]string); ok && len(browserMenuImages) > 0 {
		seen := make(map[string]bool)
		for _, u := range entry.MenuImages {
			seen[normalizePhotoURL(u)] = true
		}
		for _, u := range browserMenuImages {
			key := normalizePhotoURL(u)
			if !seen[key] {
				seen[key] = true
				entry.MenuImages = append(entry.MenuImages, u)
			}
		}
	}

	if j.ExtractEmail && entry.IsWebsiteValidForEmail() {
		opts := []EmailExtractJobOptions{}
		if j.ExitMonitor != nil {
			opts = append(opts, WithEmailJobExitMonitor(j.ExitMonitor))
		}

		emailJob := NewEmailJob(j.ID, &entry, opts...)

		j.UsageInResultststs = false

		return nil, []scrapemate.IJob{emailJob}, nil
	} else if j.ExitMonitor != nil {
		j.ExitMonitor.IncrPlacesCompleted(1)
	}

	return &entry, nil, err
}

func (j *PlaceJob) BrowserActions(ctx context.Context, page scrapemate.BrowserPage) scrapemate.Response {
	var resp scrapemate.Response

	pageResponse, err := page.Goto(j.GetURL(), scrapemate.WaitUntilDOMContentLoaded)
	if err != nil {
		resp.Error = err

		return resp
	}

	clickRejectCookiesIfRequired(page)

	const defaultTimeout = 5 * time.Second

	err = page.WaitForURL(page.URL(), defaultTimeout)
	if err != nil {
		resp.Error = err

		return resp
	}

	resp.URL = pageResponse.URL
	resp.StatusCode = pageResponse.StatusCode
	resp.Headers = pageResponse.Headers

	raw, err := j.extractJSON(page)
	if err != nil {
		resp.Error = err

		return resp
	}

	if resp.Meta == nil {
		resp.Meta = make(map[string]any)
	}

	resp.Meta["json"] = raw

	// Extract menu photos from the browser carousel
	if menuPhotos := extractMenuPhotos(page); len(menuPhotos) > 0 {
		resp.Meta["menu_images"] = menuPhotos
	}

	if j.ExtractExtraReviews {
		reviewCount := j.getReviewCount(raw)
		if reviewCount > 8 { // we have more reviews
			params := fetchReviewsParams{
				page:        page,
				mapURL:      page.URL(),
				reviewCount: reviewCount,
			}

			// Use the new fallback mechanism that tries RPC first, then DOM
			rpcData, domReviews, err := FetchReviewsWithFallback(ctx, params)

			switch {
			case err != nil:
				fmt.Printf("Warning: review extraction failed: %v\n", err)
			case len(rpcData.pages) > 0:
				resp.Meta["reviews_raw"] = rpcData
			case len(domReviews) > 0:
				resp.Meta["dom_reviews"] = domReviews
			}
		}
	}

	return resp
}

func (j *PlaceJob) getRaw(ctx context.Context, page scrapemate.BrowserPage) (any, error) {
	for {
		select {
		case <-ctx.Done():
			return nil, fmt.Errorf("timeout while getting raw data: %w", ctx.Err())
		default:
			raw, err := page.Eval(js)
			if err != nil {
				// Continue retrying on error
				<-time.After(time.Millisecond * 200)
				continue
			}

			// Check for valid non-null result
			// go-rod may return nil for JS null, or empty string
			if raw == nil {
				<-time.After(time.Millisecond * 200)
				continue
			}

			// If it's a string, make sure it's not empty
			if str, ok := raw.(string); ok {
				if str == "" {
					<-time.After(time.Millisecond * 200)
					continue
				}
			}

			return raw, nil
		}
	}
}

func (j *PlaceJob) extractJSON(page scrapemate.BrowserPage) ([]byte, error) {
	const maxRetries = 2

	for attempt := range maxRetries {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		rawI, err := j.getRaw(ctx, page)

		cancel()

		if err != nil {
			// On timeout, try reloading the page
			if attempt < maxRetries-1 {
				if reloadErr := page.Reload(scrapemate.WaitUntilDOMContentLoaded); reloadErr == nil {
					continue
				}
			}

			return nil, err
		}

		if rawI == nil {
			if attempt < maxRetries-1 {
				if reloadErr := page.Reload(scrapemate.WaitUntilDOMContentLoaded); reloadErr == nil {
					continue
				}
			}

			return nil, fmt.Errorf("APP_INITIALIZATION_STATE data not found")
		}

		raw, ok := rawI.(string)
		if !ok {
			return nil, fmt.Errorf("could not convert to string, got type %T", rawI)
		}

		const prefix = `)]}'`

		raw = strings.TrimSpace(strings.TrimPrefix(raw, prefix))

		return []byte(raw), nil
	}

	return nil, fmt.Errorf("APP_INITIALIZATION_STATE data not found after retries")
}

func (j *PlaceJob) getReviewCount(data []byte) int {
	tmpEntry, err := EntryFromJSON(data, true)
	if err != nil {
		return 0
	}

	return tmpEntry.ReviewCount
}

func (j *PlaceJob) UseInResults() bool {
	return j.UsageInResultststs
}

// extractMenuPhotos clicks the "Menu" photo tab and scrolls through the carousel
// collecting all unique menu image URLs. It parses the total from aria-label
// and scrolls the carousel container horizontally to force all items to render.
func extractMenuPhotos(page scrapemate.BrowserPage) []string {
	// Step 1: Scroll down to reveal photo category tabs, then click "Menu"
	clicked, err := page.Eval(`async () => {
		const sc = document.querySelector('.m6QErb.DxyBCb.kA9KIf.dS8AEf')
			|| document.querySelector('.m6QErb.DxyBCb.kA9KIf')
			|| document.querySelector('.m6QErb');
		if (sc) {
			for (let i = 0; i < 5; i++) {
				sc.scrollBy(0, 300);
				await new Promise(r => setTimeout(r, 400));
			}
		}
		await new Promise(r => setTimeout(r, 800));

		const tabs = document.querySelectorAll('div.Gpq6kf.NlVald, div.Gpq6kf');
		for (const tab of tabs) {
			if (tab.textContent.trim() === 'Menu') {
				const parent = tab.closest('div.LRkQ2');
				if (parent) { parent.click(); return true; }
				tab.click();
				return true;
			}
		}
		return false;
	}`)
	if err != nil || clicked == nil {
		return nil
	}

	clickedBool, _ := clicked.(bool)
	if !clickedBool {
		return nil // No menu tab — not an error, just no menu photos for this place
	}

	time.Sleep(3 * time.Second)

	// Step 2: Collect all menu photo URLs from all carousels on the page.
	// After clicking the Menu tab, Google Maps shows menu photos across multiple
	// carousel sections. Each carousel renders ~4 items in headless viewport,
	// but collecting from all of them gives us the full set.
	result, err := page.Eval(`async () => {
		const allUrls = new Set();

		function collectUrls() {
			document.querySelectorAll('button.K4UgGe img.DaSXdd').forEach(img => {
				const src = img.src || img.getAttribute('data-src') || '';
				if (src && src.includes('googleusercontent.com')) {
					allUrls.add(src);
				}
			});
		}

		// Get expected total from first aria-label "Photo X of Y"
		let total = 0;
		const firstBtn = document.querySelector('button.K4UgGe[aria-label]');
		if (firstBtn) {
			const match = firstBtn.getAttribute('aria-label').match(/of\s+(\d+)/);
			if (match) total = parseInt(match[1]);
		}

		collectUrls();
		const initialCount = allUrls.size;

		// Scroll each carousel container to reveal more items
		const carousels = document.querySelectorAll('div.fp2VUc');
		for (const carousel of carousels) {
			const scrollable = carousel.querySelector('div.dryRY')
				|| carousel.querySelector('div.cRLbXd');
			if (scrollable) {
				for (let i = 0; i < 20; i++) {
					scrollable.scrollBy(400, 0);
					await new Promise(r => setTimeout(r, 200));
					collectUrls();
				}
			}
			// Also try the Next button in each carousel
			for (let i = 0; i < 20; i++) {
				const nextBtn = carousel.querySelector('button.XMkGfe');
				if (!nextBtn) break;
				const prev = allUrls.size;
				nextBtn.click();
				await new Promise(r => setTimeout(r, 400));
				collectUrls();
				if (allUrls.size === prev && i > 3) break;
			}
		}

		// Upscale thumbnail URLs to full size
		const fullUrls = Array.from(allUrls).map(u =>
			u.replace(/=w\d+-h\d+-[^\s"]*/, '=w1200-h1200-p-k-no')
		);

		return {
			urls: fullUrls,
			debug: 'expected=' + total + ',initial=' + initialCount + ',final=' + allUrls.size
		};
	}`)
	if err != nil {
		fmt.Printf("Warning: menu photo extraction failed: %v\n", err)
		return nil
	}

	resultMap, ok := result.(map[string]any)
	if !ok {
		return nil
	}

	if debugStr, ok := resultMap["debug"].(string); ok {
		fmt.Printf("Menu photo debug: %s\n", debugStr)
	}

	rawURLs, ok := resultMap["urls"].([]any)
	if !ok || len(rawURLs) == 0 {
		return nil
	}

	urls := make([]string, 0, len(rawURLs))
	for _, u := range rawURLs {
		if s, ok := u.(string); ok && s != "" {
			urls = append(urls, s)
		}
	}

	fmt.Printf("Menu photos extracted: %d\n", len(urls))

	return urls
}

const js = `
(function() {
	if (!window.APP_INITIALIZATION_STATE || !window.APP_INITIALIZATION_STATE[3]) {
		return null;
	}
	const appState = window.APP_INITIALIZATION_STATE[3];
	
	// Search all properties of appState for arrays containing JSON strings
	for (const key of Object.keys(appState)) {
		const arr = appState[key];
		if (Array.isArray(arr)) {
			// Check indices 6 and 5 (where place data typically is)
			for (const idx of [6, 5]) {
				const item = arr[idx];
				if (typeof item === 'string' && item.startsWith(")]}'")) {
					return item;
				}
			}
		}
	}
	return null;
})()
`
