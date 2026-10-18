<<<<<<< HEAD
# GMB Automation

Automate Google Business Profile post creation via Selenium. Reads store codes from plain text file, creates posts with static description/photo and unique URLs per store.

## What it does

- Reads store codes + unique URLs from `stores.txt`
- Uses static description, photo, CTA from `.env`
- For each pending store: searches GMB by code, creates post, fills description, uploads photo, selects CTA, fills URL
- Publishes post (or dry-run preview)
- Tracks status per store in `status.csv`: PENDING → PROCESSING → SUCCESS (or FAILED)
- Screenshots errors to `logs/screenshots/`
- Logs to `logs/gmb_automation.log`

## Setup

### 1. Install Python 3.10+

```powershell
python --version
```

### 2. Clone/init project

```powershell
cd C:\Users\<user>\Downloads\GMB_Automation
```

### 3. Install dependencies

```powershell
py -m pip install -r requirements.txt
```

### 4. Prepare files

**stores.txt** — store codes + unique URLs:
```
STORE_CODE_001|https://wa.me/628123456789?text=Halo
STORE_CODE_002|https://wa.me/628123456790?text=Halo
STORE_CODE_003|https://wa.me/628123456791?text=Halo
```

Format: `store_code|url` (pipe-separated)

**photos/** — static photo for all stores:
```
photos/
  YOGA0913.jpg
```

### 5. Setup environment

Copy `.env.example` to `.env`:

```powershell
Copy-Item -Path ".env.example" -Destination ".env"
```

Edit `.env`:

```env
DESCRIPTION=Book your stay today and enjoy our special price
PHOTO=photos/YOGA0913.jpg
CTA=Book
DRY_RUN=true
MAX_STORES=1
```

All stores use the same description, photo, and CTA. Only URL is unique per store.

## Multi-Post Mode (Mode 3)

### Overview

Mode 3 publishes **three independent posts** to every property matching a store code. Each post has custom caption, image, CTA, and URL.

Example: Store code `YOGA0017` matches 2 properties → publishes 6 total posts (3 per property).

### Setup

#### 1. Create `multi_post_config.json`

Copy example from `multi_post_config.json`:

```json
{
  "post_types": [
    {
      "id": "post_1",
      "name": "Summer Promotion",
      "caption": "Summer Special! Book now.",
      "image": "photos/post_1.jpg",
      "cta": "Book",
      "url": "https://example.com/booking-summer"
    },
    {
      "id": "post_2",
      "name": "Winter Package",
      "caption": "Cozy winter getaway.",
      "image": "photos/post_2.jpg",
      "cta": "Book",
      "url": "https://example.com/booking-winter"
    },
    {
      "id": "post_3",
      "name": "New Year Deal",
      "caption": "Start 2024 with us!",
      "image": "photos/post_3.jpg",
      "cta": "Book",
      "url": "https://example.com/booking-newyear"
    }
  ]
}
```

**Requirements:**
- Exactly 3 post types
- Each must have: `id`, `name`, `caption`, `image`, `cta`, `url`
- Image paths must exist
- URLs must be valid

#### 2. Prepare images

Save 3 images to `photos/`:
```
photos/
  post_1.jpg
  post_2.jpg
  post_3.jpg
```

#### 3. Run Multi-Post mode

```powershell
py gmb_automation.py
```

```
GMB AUTOMATION - PILIH MODE
1. Add Post
2. Delete Post
3. Multi-Post (3 Content Types)

Pilih mode (1, 2, atau 3): 3
```

### Workflow

For each store code:

1. Search store code in GMB
2. Find ALL matching properties
3. For each property:
   - Publish Post 1 (caption, image, URL)
   - Publish Post 2 (caption, image, URL)
   - Publish Post 3 (caption, image, URL)
4. Track each property/post combination independently

### Status tracking

Results saved in `multi_post_status.csv`:

```
store_code,property_identifier,property_name,post_type_id,status,attempts,timestamp,error
YOGA0017,prop_YOGA0017_1,Property 1,post_1,SUCCESS,1,2026-10-17T...
YOGA0017,prop_YOGA0017_1,Property 1,post_2,SUCCESS,1,2026-10-17T...
YOGA0017,prop_YOGA0017_1,Property 1,post_3,SUCCESS,1,2026-10-17T...
YOGA0017,prop_YOGA0017_2,Property 2,post_1,SUCCESS,1,2026-10-17T...
YOGA0017,prop_YOGA0017_2,Property 2,post_2,FAILED,1,2026-10-17T...,URL field not found
```

Statuses:
- `SUCCESS` — post published
- `DRY_RUN_READY` — prepared in dry-run mode
- `FAILED` — error during publishing
- `PROCESSING` — currently processing

### Dry-run test

Edit `.env`:
```env
DRY_RUN=true
MAX_STORES=1
```

Run:
```powershell
py gmb_automation.py
# Select mode 3
```

Verifies:
- Config loads (3 post types)
- Images exist
- All posts can be filled (no publish)
- Updates `multi_post_status.csv` → `DRY_RUN_READY`

### Publish to real properties

Edit `.env`:
```env
DRY_RUN=false
MAX_STORES=1
```

Run same command. Posts published immediately.

### Resume safely

If interrupted:
1. Already-SUCCESS posts skipped
2. FAILED/PENDING posts retried
3. No duplicate posts

### Logs and screenshots

Multi-post logs in `logs/gmb_automation.log`:

```
=== MULTI-POST: Processing YOGA0017 ===
Found 2 properties to post to

=== Processing property 1/2 ===
Publishing post post_1 to Property 1
  Caption: Summer Special! Book now.
  CTA: Book, URL: https://example.com/booking-summer
Caption filled for post_1
Image uploaded for post_1: photos/post_1.jpg
Selected CTA for post_1: Book
URL filled for post_1
Post post_1 published successfully
...

=== MULTI-POST SUMMARY FOR YOGA0017 ===
Total posts: 6
Successful: 6
Failed: 0
```

Error screenshots saved to `logs/screenshots/`:
- `{store_code}_multi_{property_idx}_{post_id}_error.png`

### Limitations

- One store code can match multiple properties, but each is processed separately
- If property matching is unreliable (GMB UI changes), manually verify in logs and screenshots
- No automatic retry on network errors — rerun automation safely

All stores use the same description, photo, and CTA. Only URL is unique per store.



### First run — login to Google

```powershell
py gmb_automation.py
```

Chrome opens with persistent profile (`chrome-profile/`). 

**Manual step:** Log in to Google Business Profile. Session saves for next runs.

### Test dry-run (default)

```powershell
py gmb_automation.py
```

With `DRY_RUN=true` (default), automation:
1. Searches store by code
2. Creates post
3. Fills description, photo, CTA, URL
4. **Stops before publish**
5. Updates `status.csv` → `DRY_RUN_READY`

Check `logs/gmb_automation.log` for details. View `status.csv` for store status.

### Publish (single store test)

Edit `.env`:

```env
DRY_RUN=false
MAX_STORES=1
```

```powershell
py gmb_automation.py
```

Publishes one store. Check `status.csv` → `SUCCESS` or `FAILED`.

### Publish multiple stores

Edit `.env`:

```env
DRY_RUN=false
MAX_STORES=10
```

or:

```env
MAX_STORES=0
```

(0 = process all pending stores)

```powershell
py gmb_automation.py
```

## Status tracking

**status.csv** — persistent status per store:

```
store_code,status,timestamp,error
STORE_CODE_001,SUCCESS,2026-10-08T23:00:50.123456,
STORE_CODE_002,FAILED,2026-10-08T23:05:12.654321,Store code not found
STORE_CODE_003,DRY_RUN_READY,2026-10-08T23:10:33.987654,
```

Statuses:
- `PENDING` — not yet processed
- `PROCESSING` — currently processing
- `SUCCESS` — published
- `FAILED` — error occurred (see `error` column)
- `DRY_RUN_READY` — dry-run completed, ready to publish

**Idempotent:** Only PENDING stores are processed on each run. Completed stores (SUCCESS/FAILED/PROCESSING) are skipped. Restart safely.

## Locators (if GMB UI changes)

Edit `gmb_automation.py`. Each function has fallback locators marked:

```python
# TODO: Verify locator against current GBP DOM.
locators = [
    (By.XPATH, "//button[contains(., 'Add update')]"),
    (By.XPATH, "//button[contains(., 'Create')]"),
    ...
]
```

Functions with locators:
- `search_and_select_store()` — search field, search results
- `create_post()` — create/add update button
- `fill_description()` — description field
- `upload_photo()` — file input
- `select_cta()` — CTA button
- `fill_url()` — URL field
- `publish_post()` — publish button, confirmation

If all fallbacks fail:
1. Screenshot saved to `logs/screenshots/{store_code}_error.png`
2. Error logged
3. `status.csv` updated: status=FAILED, error message
4. Automation continues next store

Update `locators` list in any function. Test with `DRY_RUN=true`, `MAX_STORES=1` first.

## Logs

- **File:** `logs/gmb_automation.log`
- **Status:** `status.csv`
- **Screenshots:** `logs/screenshots/{store_code}_error.png`

Example log:

```
2026-10-08 23:30:22 | INFO | === GMB Automation Start ===
2026-10-08 23:30:22 | INFO | DRY_RUN: True, MAX_STORES: 1
2026-10-08 23:30:25 | INFO | Config validated: DESCRIPTION='Book your stay...', PHOTO=photos/YOGA0913.jpg, CTA=Book
2026-10-08 23:30:26 | INFO | Loaded 3 stores from stores.txt
2026-10-08 23:30:27 | INFO | Loaded status for 0 stores
2026-10-08 23:30:28 | INFO | GMB opened
2026-10-08 23:30:30 | INFO | Processing 3 pending stores
2026-10-08 23:30:32 | INFO | Processing store: STORE_CODE_001
2026-10-08 23:30:33 | INFO | Store STORE_CODE_001: Status updated to PROCESSING
2026-10-08 23:30:35 | INFO | Searching store: STORE_CODE_001
2026-10-08 23:30:38 | INFO | Store code 'STORE_CODE_001' entered in search
2026-10-08 23:30:40 | INFO | Store 'STORE_CODE_001' selected
2026-10-08 23:30:42 | INFO | Creating new post
2026-10-08 23:30:45 | INFO | Post creation initiated
2026-10-08 23:30:47 | INFO | Filling description
2026-10-08 23:30:50 | INFO | Description filled
2026-10-08 23:30:52 | INFO | Uploading photo: photos/YOGA0913.jpg
2026-10-08 23:31:00 | INFO | Photo uploaded
2026-10-08 23:31:02 | INFO | Selecting CTA: Book
2026-10-08 23:31:05 | INFO | CTA 'Book' selected
2026-10-08 23:31:07 | INFO | Filling URL: https://wa.me/628123456789
2026-10-08 23:31:10 | INFO | URL filled
2026-10-08 23:31:12 | INFO | Validating post
2026-10-08 23:31:13 | INFO | Post validation passed
2026-10-08 23:31:15 | INFO | DRY_RUN=true: Skipping publish
2026-10-08 23:31:16 | INFO | Store STORE_CODE_001: DRY_RUN completed, not publishing
2026-10-08 23:31:17 | INFO | Store STORE_CODE_001: Status updated to DRY_RUN_READY
2026-10-08 23:31:19 | INFO | === GMB Automation End ===
```

## Structure

```
GMB_Automation/
├── gmb_automation.py        # Main script
├── requirements.txt         # Python dependencies
├── .env.example            # Config template
├── .env                    # Config (created from .env.example, gitignored)
├── .gitignore             # Git ignore rules
├── README.md              # This file
├── stores.txt             # Store codes + URLs (pipe-separated)
├── status.csv             # Status tracking (auto-created)
├── chrome-profile/        # Persistent Chrome profile (gitignored)
├── photos/                # Static post photo
│   └── YOGA0913.jpg
└── logs/
    ├── gmb_automation.log
    └── screenshots/
        ├── STORE_CODE_001_error.png
        └── STORE_CODE_002_error.png
```

## Key Functions

- `create_driver()` — Chrome driver with persistent profile
- `load_stores()` — Read stores.txt
- `init_status_csv()` — Create/initialize status.csv
- `load_status()` — Read status.csv
- `update_status()` — Write to status.csv
- `search_and_select_store()` — Search GMB by store code
- `create_post()` — Click "Add update" / "Create"
- `fill_description()` — Enter post text
- `upload_photo()` — Send photo file
- `select_cta()` — Pick CTA button
- `fill_url()` — Enter unique URL for CTA
- `publish_post()` — Click Publish (or skip if DRY_RUN)
- `process_store()` — Run full workflow for one store
- `load_multi_post_config()` — Load 3 post types from JSON
- `init_multi_post_status_csv()` — Initialize multi-post tracking
- `load_multi_post_status()` — Read multi-post status
- `update_multi_post_status()` — Write multi-post result
- `fill_form_and_publish_multi()` — Publish post with custom config
- `process_store_multi_post()` — Multi-post workflow for all properties
- `main()` — Mode selection menu and dispatch

## Config

**stores.txt format:**
```
STORE_CODE_001|https://wa.me/628123456789?text=Halo
STORE_CODE_002|https://wa.me/628123456790?text=Halo
```

One store per line. Format: `store_code|url`.

**Comments:** Lines starting with `#` are ignored.

**.env:**
- `DESCRIPTION` — post text (same for all stores)
- `PHOTO` — path to photo (same for all stores)
- `CTA` — call-to-action button label
- `DRY_RUN` — true/false (default true)
- `MAX_STORES` — max stores to process (0 = all)
- `WAIT_TIMEOUT` — Selenium wait timeout in seconds

## Notes

- **Manual login:** No auto-login. First run, you log in to Google in the opened Chrome window.
- **2FA/CAPTCHA:** If Google prompts, handle it manually in the Chrome window. Script pauses.
- **Idempotent:** Only PENDING stores are processed. Restart safely.
- **Error isolation:** One store failure does not stop the batch.
- **DRY_RUN:** Default true. Review posts before publishing.
- **Static data:** Description, photo, CTA are identical for all stores. Only URL varies per store.

## Workflow summary

1. Load `stores.txt` (store codes + unique URLs)
2. Check `status.csv` for already-processed stores
3. For each pending store:
   - Search GMB by store code
   - Create post with static description + photo
   - Select CTA
   - Fill unique URL
   - Publish (or dry-run)
   - Update `status.csv`
4. Screenshot errors to `logs/screenshots/`
5. Log all events to `logs/gmb_automation.log`

## Installation quick copy-paste

```powershell
cd C:\Users\<user>\Downloads\GMB_Automation
py -m pip install -r requirements.txt
Copy-Item -Path ".env.example" -Destination ".env"
py gmb_automation.py
```
