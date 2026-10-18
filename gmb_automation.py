#!/usr/bin/env python3
"""
GMB Automation - Simple flow:
1. Open business.google.com
2. Search store code
3. Press Enter
4. Detect search results
5. Click add post button
6. Fill: description, photo, CTA, WA link
"""

import logging
import os
import sys
import csv
import json
from pathlib import Path
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions

try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False

from dotenv import load_dotenv

load_dotenv()

# Config
DESCRIPTION = os.getenv("DESCRIPTION", "").strip()
PHOTO = os.getenv("PHOTO", "").strip()
CTA = os.getenv("CTA", "Book").strip()
WA_LINK = os.getenv("WA_LINK", "").strip()
CHROME_PROFILE = os.getenv("CHROME_PROFILE", "./chrome-profile")
GMB_URL = os.getenv("GMB_URL", "https://business.google.com/")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_STORES = int(os.getenv("MAX_STORES", "1"))
FAST_MODE = os.getenv("FAST_MODE", "false").lower() == "true"
SKIP_SCREENSHOTS = os.getenv("SKIP_SCREENSHOTS", "false").lower() == "true"
SLEEP_MULT = float(os.getenv("SLEEP_MULTIPLIER", "1.0"))

# CTA helpers - floating dropdown renders after clicking "Tidak ada"
DEFAULT_CTA_LABEL = "Tidak ada"
CTA_MAP = {
    "Book": ["Reservasi", "Book", "Pesan sekarang", "Booking"],  # Reservasi = Book in Indonesian GMB
    "Order": ["Order", "Pesan"],
    "Call": ["Call", "Telepon", "Hubungi"],
    "Learn more": ["Learn more", "Pelajari lebih lanjut"],
    "Sign up": ["Sign up", "Daftar"],
}
def get_cta_candidates(cta: str):
    # Return map candidates PLUS the CTA itself for exact match
    return CTA_MAP.get(cta, [cta]) + [cta]

STORES_FILE = Path("stores.txt")
STATUS_FILE = Path("status.csv")
MULTI_POST_CONFIG_FILE = Path("multi_post_config.json")
MULTI_POST_STATUS_FILE = Path("multi_post_status.csv")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
SCREENSHOT_DIR = LOG_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "gmb_automation.log", encoding="utf-8"),
        logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)),
    ],
)
logger = logging.getLogger(__name__)


def sleep_opt(seconds: float):
    """Sleep with SLEEP_MULTIPLIER and FAST_MODE"""
    import time
    if FAST_MODE:
        time.sleep(seconds * SLEEP_MULT * 0.6)
    else:
        time.sleep(seconds * SLEEP_MULT)


def validate_config():
    if not DESCRIPTION:
        raise ValueError("DESCRIPTION not set")
    if not PHOTO:
        raise ValueError("PHOTO not set")
    if not WA_LINK:
        raise ValueError("WA_LINK not set")
    if not STORES_FILE.exists():
        raise FileNotFoundError(f"stores.txt not found")

    photo_path = Path(PHOTO)
    if not photo_path.is_absolute():
        photo_path = Path.cwd() / PHOTO
    if not photo_path.exists():
        raise FileNotFoundError(f"Photo not found: {photo_path}")

    logger.info(f"Config OK: DESCRIPTION='{DESCRIPTION[:40]}...', PHOTO={PHOTO}, CTA={CTA}, WA_LINK={'*' * len(WA_LINK)}")


def load_multi_post_config():
    """Load and validate multi-post configuration from JSON"""
    if not MULTI_POST_CONFIG_FILE.exists():
        raise FileNotFoundError(f"multi_post_config.json not found")

    with open(MULTI_POST_CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    post_types = config.get("post_types", [])

    # Validate exactly 3 post types
    if len(post_types) != 3:
        raise ValueError(f"Expected 3 post types, found {len(post_types)}")

    for i, post in enumerate(post_types):
        # Validate required fields
        required = ["id", "name", "caption", "image", "cta", "url"]
        for field in required:
            if field not in post or not post[field]:
                raise ValueError(f"Post type {i}: missing or empty '{field}'")

        # Validate image exists
        img_path = Path(post["image"])
        if not img_path.is_absolute():
            img_path = Path.cwd() / post["image"]
        if not img_path.exists():
            raise FileNotFoundError(f"Post type {i} image not found: {img_path}")

        # Validate URL is non-empty
        if not post["url"].strip():
            raise ValueError(f"Post type {i}: URL is empty")

    logger.info(f"Multi-post config loaded: {len(post_types)} post types")
    for post in post_types:
        logger.info(f"  - {post['id']}: {post['name']}")

    return post_types


def init_multi_post_status_csv():
    """Initialize multi-post status CSV if it doesn't exist"""
    if not MULTI_POST_STATUS_FILE.exists():
        with open(MULTI_POST_STATUS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["store_code", "property_identifier", "property_name", "post_type_id", "status", "attempts", "timestamp", "error"])
            writer.writeheader()
        logger.info("Created multi_post_status.csv")


def load_multi_post_status():
    """Load multi-post status from CSV"""
    status = {}
    if MULTI_POST_STATUS_FILE.exists():
        with open(MULTI_POST_STATUS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row["store_code"], row["property_identifier"], row["post_type_id"])
                status[key] = {
                    "status": row["status"],
                    "attempts": int(row.get("attempts", 0)),
                    "error": row.get("error", "")
                }
    return status


def update_multi_post_status(store_code, prop_id, prop_name, post_type_id, status, attempts=0, error=""):
    """Update multi-post status in CSV"""
    all_status = load_multi_post_status()
    key = (store_code, prop_id, post_type_id)
    all_status[key] = {
        "status": status,
        "attempts": attempts,
        "error": error
    }

    with open(MULTI_POST_STATUS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["store_code", "property_identifier", "property_name", "post_type_id", "status", "attempts", "timestamp", "error"])
        writer.writeheader()
        for (code, pid, ptid), st in all_status.items():
            writer.writerow({
                "store_code": code,
                "property_identifier": pid,
                "property_name": prop_name,
                "post_type_id": ptid,
                "status": st["status"],
                "attempts": st["attempts"],
                "timestamp": datetime.now().isoformat(),
                "error": st["error"],
            })


def load_stores():
    stores = []
    with open(STORES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            # Format: STORE_CODE|WA_LINK
            if len(parts) == 2:
                store_code, wa_link = parts[0].strip(), parts[1].strip()
                if store_code and wa_link:
                    stores.append({"code": store_code, "wa_link": wa_link})
            else:
                logger.warning(f"Invalid line (need 2 columns STORE_CODE|WA_LINK): {line}")
    logger.info(f"Loaded {len(stores)} stores")
    return stores


def init_status_csv():
    if not STATUS_FILE.exists():
        with open(STATUS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["store_code", "status", "timestamp", "error"])
            writer.writeheader()
        logger.info("Created status.csv")


def load_status():
    status = {}
    if STATUS_FILE.exists():
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                status[row["store_code"]] = row["status"]
    return status


def update_status(store_code, status, error=""):
    all_status = load_status()
    all_status[store_code] = status

    with open(STATUS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["store_code", "status", "timestamp", "error"])
        writer.writeheader()
        for code, st in all_status.items():
            writer.writerow({
                "store_code": code,
                "status": st,
                "timestamp": datetime.now().isoformat(),
                "error": error,
            })
    logger.info(f"Store {store_code}: {status}")


def create_driver():
    options = ChromeOptions()
    options.add_argument(f"--user-data-dir={os.path.abspath(CHROME_PROFILE)}")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    if UNDETECTED_AVAILABLE:
        driver = uc.Chrome(options=options, version_main=None)
    else:
        driver = webdriver.Chrome(options=options)

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false})")
    return driver


def is_actually_logged_in(driver):
    """
    Verify if user is ACTUALLY logged in to Google by checking for
    authenticated-only elements on business.google.com.
    URL check alone is NOT reliable — GMB can show business.google.com
    even without login (landing page, embedded sign-in form, etc.)
    """
    import time

    # Check 1: If URL contains accounts.google.com → definitely NOT logged in
    if "accounts.google.com" in driver.current_url:
        logger.info("  URL contains accounts.google.com → NOT logged in")
        return False

    # Check 2: If URL is not on business.google.com at all → NOT logged in
    if "business.google.com" not in driver.current_url:
        logger.info(f"  URL is not business.google.com → NOT logged in (URL: {driver.current_url})")
        return False

    # Check 3: Look for elements that ONLY appear when authenticated
    # These are GMB dashboard elements that require a logged-in session
    authenticated_selectors = [
        # Search combobox (only visible on authenticated GMB dashboard)
        "//input[@role='combobox']",
        # User avatar / account icon in top-right
        "//a[contains(@href, 'accounts.google.com/SignOutOptions')]",
        "//img[contains(@class, 'avatar') or contains(@class, 'profile')]",
        # Business listing elements
        "//div[contains(@class, 'business-name')]",
        # GMB navigation items only visible when logged in
        "//*[@data-business-id]",
    ]

    for selector in authenticated_selectors:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            visible_elements = [e for e in elements if e.is_displayed()]
            if visible_elements:
                logger.info(f"  Found authenticated element: {selector} → LOGGED IN")
                return True
        except Exception:
            continue

    # Check 4: Look for sign-in / login buttons (indicates NOT logged in)
    not_logged_in_indicators = [
        "//a[contains(@href, 'accounts.google.com/ServiceLogin')]",
        "//*[contains(text(), 'Sign in')]",
        "//*[contains(text(), 'Masuk')]",
        "//*[contains(text(), 'Login')]",
    ]

    for selector in not_logged_in_indicators:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            visible_elements = [e for e in elements if e.is_displayed()]
            if visible_elements:
                logger.info(f"  Found sign-in indicator: {selector} → NOT logged in")
                return False
        except Exception:
            continue

    # Check 5: Try to find the search bar by waiting briefly
    try:
        from selenium.common.exceptions import TimeoutException
        search_bar = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
        )
        if search_bar.is_displayed():
            logger.info("  Search combobox found and visible → LOGGED IN")
            return True
    except Exception:
        pass

    # If none of the checks matched, assume NOT logged in
    logger.info("  No authenticated elements found → NOT logged in")
    return False


def login_to_google(driver):
    """
    Check if already logged in. If not, open login page and wait for user to complete login.
    Session is saved in persistent Chrome profile for reuse.
    """
    import time

    try:
        logger.info("=" * 70)
        logger.info("CHECKING GOOGLE LOGIN STATUS")
        logger.info("=" * 70)

        # Check if already logged in by navigating to GMB
        logger.info("Checking if already authenticated...")
        driver.get(GMB_URL)
        time.sleep(3)

        # Verify ACTUAL login status (not just URL)
        if is_actually_logged_in(driver):
            logger.info("[OK] Already logged in! Using saved session.")
            logger.info("=" * 70)
            return True

        # Not logged in — prompt user to log in
        logger.info("Not authenticated. Opening login page...")
        logger.info("=" * 70)
        logger.info("GOOGLE LOGIN REQUIRED")
        logger.info("=" * 70)
        logger.info("Please log in to your Google account in the Chrome window.")
        logger.info("After logging in, press Enter in this terminal to continue.")
        logger.info("=" * 70)

        # If not already at Google login page, navigate there
        if "accounts.google.com" not in driver.current_url:
            driver.get("https://accounts.google.com/ServiceLogin?continue=https://business.google.com/")
            time.sleep(3)

        logger.info("Chrome browser is open. Please log in now.")

        # Wait for user to press Enter
        input("\nPress Enter after you have successfully logged in: ")

        logger.info("Continuing with automation...")
        time.sleep(2)

        # Verify login was successful — navigate to GMB and check properly
        driver.get(GMB_URL)
        time.sleep(3)

        if is_actually_logged_in(driver):
            logger.info("[OK] Login successful! Session will be saved for next use.")
            logger.info("=" * 70)
            return True
        else:
            logger.error("[FAIL] Login verification failed. Please make sure you are logged in to Google.")
            logger.error("Try running the script again after logging in manually.")
            return False

    except Exception as e:
        logger.error(f"Login check failed: {e}")
        return False


def fill_form_and_publish(driver, profile_name: str, wa_link: str):
    """Fill form and publish post for a single profile. Returns True if success."""
    try:
        import time

        # Step 6: Fill form
        logger.info(f"Filling form for: {profile_name}")
        sleep_opt(1.5)

        # Switch to main content first
        driver.switch_to.default_content()
        sleep_opt(0.5)

        # Check for iframes in modal
        iframes = driver.find_elements(By.XPATH, "//iframe")
        logger.info(f"Found {len(iframes)} iframes on page")

        desc_field = None

        # Try each iframe to find description field
        for i, iframe in enumerate(iframes):
            try:
                logger.info(f"Checking iframe {i}...")
                driver.switch_to.frame(iframe)
                sleep_opt(0.3)

                textareas = driver.find_elements(By.XPATH, "//textarea")
                logger.info(f"  Iframe {i}: found {len(textareas)} textareas")

                if textareas:
                    desc_field = textareas[0]
                    logger.info(f"Found description in iframe {i}")
                    break

                driver.switch_to.default_content()
            except Exception as e:
                logger.debug(f"Iframe {i} check failed: {e}")
                try:
                    driver.switch_to.default_content()
                except:
                    pass
                continue

        # If not in iframe, try main content
        if not desc_field:
            logger.info("Checking main content for textarea...")
            driver.switch_to.default_content()
            sleep_opt(0.3)
            textareas = driver.find_elements(By.XPATH, "//textarea")
            logger.info(f"Main content: found {len(textareas)} textareas")
            if textareas:
                desc_field = textareas[0]
                logger.info("Found textarea in main content")

        if not desc_field:
            logger.error("Description field not found")
            try:
                driver.save_screenshot(str(SCREENSHOT_DIR / f"{profile_name}_desc_field_error.png"))
            except:
                pass
            return False

        # Click and fill
        try:
            desc_field.click()
        except:
            driver.execute_script("arguments[0].click();", desc_field)

        sleep_opt(0.3)
        desc_field.clear()
        desc_field.send_keys(DESCRIPTION)
        logger.info("Description filled")
        sleep_opt(0.5)

        # IMPORTANT: Switch back to main content after filling description in iframe
        logger.info("Switching back to main content...")
        driver.switch_to.default_content()
        time.sleep(1)

        # Upload photo - search across main content and all iframes
        logger.info("Uploading photo...")
        file_input = None

        # Try main content first
        try:
            file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
            if file_inputs:
                file_input = file_inputs[0]
                logger.info("File input found in main content")
        except:
            pass

        # If not found, search in iframes
        if not file_input:
            iframes = driver.find_elements(By.XPATH, "//iframe")
            for i, iframe in enumerate(iframes):
                try:
                    driver.switch_to.frame(iframe)
                    file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                    if file_inputs:
                        file_input = file_inputs[0]
                        logger.info(f"File input found in iframe {i}")
                        break
                    driver.switch_to.default_content()
                except:
                    try:
                        driver.switch_to.default_content()
                    except:
                        pass

        if not file_input:
            # Try waiting
            driver.switch_to.default_content()
            try:
                file_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
                )
                logger.info("File input found after wait")
            except Exception as e:
                logger.error(f"File input not found: {e}")
                try:
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{profile_name}_no_file_input.png"))
                except:
                    pass
                return False

        photo_path = Path(PHOTO)
        if not photo_path.is_absolute():
            photo_path = Path.cwd() / PHOTO

        if not photo_path.exists():
            logger.error(f"Photo file not found: {photo_path}")
            return False

        file_input.send_keys(str(photo_path.absolute()))
        logger.info(f"Photo uploaded: {PHOTO}")
        time.sleep(3)

        # Select CTA
        logger.info(f"Selecting CTA: {CTA}")
        sleep_opt(0.5)

        cta_found = False

        # Helper: find and log all visible buttons
        def find_all_buttons():
            btns = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //span[@role='button'] | //a[@role='button']")
            logger.info(f"Found {len(btns)} buttons on page")
            for i, b in enumerate(btns):
                try:
                    t = (b.text or b.get_attribute('aria-label') or '').strip()
                    if t and b.is_displayed():
                        logger.info(f"  CTA scan [{i}]: '{t[:60]}'")
                except:
                    pass
            return btns

        # Also search in iframes for CTA elements
        def search_in_all_contexts(search_func):
            """Run search_func in main content and all iframes until it returns True"""
            driver.switch_to.default_content()
            if search_func():
                return True
            iframes = driver.find_elements(By.XPATH, "//iframe")
            for i, iframe in enumerate(iframes):
                try:
                    driver.switch_to.frame(iframe)
                    if search_func():
                        return True
                    driver.switch_to.default_content()
                except:
                    try:
                        driver.switch_to.default_content()
                    except:
                        pass
            return False

        try:
            # Find +Tombol / +Button / Add a button
            tombol_btn = None
            buttons = find_all_buttons()

            # Search keywords for the CTA button trigger
            cta_trigger_keywords = ['tombol', 'button', 'add a button', 'tambah tombol']

            for btn in buttons:
                try:
                    btn_text = (btn.text or btn.get_attribute('aria-label') or "").strip()
                    btn_text_lower = btn_text.lower()

                    for keyword in cta_trigger_keywords:
                        if keyword in btn_text_lower:
                            if btn.is_displayed():
                                tombol_btn = btn
                                logger.info(f"Found CTA trigger button: '{btn_text}'")
                                break
                    if tombol_btn:
                        break
                except:
                    continue

            # If not found in main, try iframes
            if not tombol_btn:
                logger.info("CTA trigger not found in main content, checking iframes...")
                iframes = driver.find_elements(By.XPATH, "//iframe")
                for i, iframe in enumerate(iframes):
                    try:
                        driver.switch_to.frame(iframe)
                        buttons = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //span[@role='button']")
                        for btn in buttons:
                            try:
                                btn_text = (btn.text or btn.get_attribute('aria-label') or "").strip()
                                btn_text_lower = btn_text.lower()
                                for keyword in cta_trigger_keywords:
                                    if keyword in btn_text_lower:
                                        if btn.is_displayed():
                                            tombol_btn = btn
                                            logger.info(f"Found CTA trigger in iframe {i}: '{btn_text}'")
                                            break
                                if tombol_btn:
                                    break
                            except:
                                continue
                        if tombol_btn:
                            break
                        driver.switch_to.default_content()
                    except:
                        try:
                            driver.switch_to.default_content()
                        except:
                            pass

            if tombol_btn:
                driver.execute_script("arguments[0].scrollIntoView(true);", tombol_btn)
                sleep_opt(0.3)
                driver.execute_script("arguments[0].click();", tombol_btn)
                logger.info("Clicked +Tombol button")
                time.sleep(2)

                # Find and click CTA combobox (Tidak ada / None)
                logger.info("Looking for CTA combobox...")
                try:
                    cta_combos = driver.find_elements(By.XPATH, "//*[contains(text(),'Tidak ada')]")
                    for combo in cta_combos:
                        if combo.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", combo)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", combo)
                            logger.info("Clicked CTA combobox")
                            time.sleep(2)
                            break
                except Exception as e:
                    logger.debug(f"CTA combobox click failed: {e}")

                # Search for CTA option
                candidates = get_cta_candidates(CTA)
                logger.info(f"CTA candidates: {candidates}")

                for cand in candidates:
                    try:
                        logger.info(f"  Searching for: '{cand}'")
                        opts = driver.find_elements(By.XPATH, f"//*[normalize-space(.)='{cand}'][@role='option' or @role='menuitem'] | //*[normalize-space(.)='{cand}'][contains(@class, 'option')]")
                        if not opts:
                            # Broader search
                            opts = driver.find_elements(By.XPATH, f"//*[normalize-space(.)='{cand}']")
                        for opt in opts:
                            try:
                                if opt.is_displayed():
                                    logger.info(f"    Found and clicking '{cand}'")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", opt)
                                    sleep_opt(0.2)
                                    driver.execute_script("arguments[0].click();", opt)
                                    logger.info(f"Selected CTA: {cand}")
                                    cta_found = True
                                    break
                            except:
                                continue
                        if cta_found:
                            break
                    except Exception as e:
                        logger.debug(f"CTA search failed: {e}")

            else:
                logger.warning("CTA trigger button not found in main content or iframes")

        except Exception as e:
            logger.warning(f"CTA selection failed: {e}")

        if not cta_found:
            logger.warning(f"Could not select CTA '{CTA}' - continuing anyway")

        sleep_opt(0.5)

        # IMPORTANT: Switch back to main content before searching for URL field
        driver.switch_to.default_content()
        time.sleep(1)

        # Fill WA link - search in main content and all iframes
        logger.info("Filling WA link...")
        sleep_opt(1)

        url_field = None

        def find_url_field_in_current_context():
            """Find URL/link input field in the current context (main or iframe)"""
            nonlocal url_field
            all_inputs = driver.find_elements(By.XPATH, "//input[@type='text' or @type='url' or not(@type)]")
            logger.info(f"Found {len(all_inputs)} inputs in current context")

            for inp in all_inputs:
                try:
                    if not inp.is_displayed():
                        continue
                    inp_placeholder = inp.get_attribute('placeholder') or ""
                    inp_aria = inp.get_attribute('aria-label') or ""
                    inp_name = inp.get_attribute('name') or ""
                    inp_id = inp.get_attribute('id') or ""

                    logger.info(f"  Input: placeholder='{inp_placeholder}', aria='{inp_aria}', name='{inp_name}', id='{inp_id}'")

                    # Check for link-related field
                    all_attrs = (inp_placeholder + inp_aria + inp_name + inp_id).lower()
                    if any(x in all_attrs for x in ['link', 'url', 'whatsapp', 'http', 'website', 'tautan']):
                        url_field = inp
                        logger.info("Found URL field by label")
                        return True
                except:
                    continue

            # Fallback: first visible empty text input (not the search bar)
            for inp in all_inputs:
                try:
                    if inp.is_displayed() and (inp.get_attribute('value') or "") == "":
                        inp_role = inp.get_attribute('role') or ""
                        if inp_role != 'combobox':  # skip search bar
                            url_field = inp
                            logger.info("Using first empty text input as URL field (fallback)")
                            return True
                except:
                    continue
            return False

        # Search main content first
        if not find_url_field_in_current_context():
            # Search in iframes
            logger.info("URL field not found in main content, checking iframes...")
            iframes = driver.find_elements(By.XPATH, "//iframe")
            for i, iframe in enumerate(iframes):
                try:
                    driver.switch_to.frame(iframe)
                    logger.info(f"Checking iframe {i} for URL field...")
                    if find_url_field_in_current_context():
                        logger.info(f"Found URL field in iframe {i}")
                        break
                    driver.switch_to.default_content()
                except:
                    try:
                        driver.switch_to.default_content()
                    except:
                        pass

        if url_field:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", url_field)
                sleep_opt(0.3)
                url_field.clear()
                url_field.send_keys(wa_link)
                logger.info(f"WA link filled")
            except Exception as e:
                logger.error(f"Failed to fill URL: {e}")
                return False
        else:
            logger.warning("URL field not found in any context")
            try:
                driver.switch_to.default_content()
                driver.save_screenshot(str(SCREENSHOT_DIR / f"{profile_name}_url_field_not_found.png"))
            except:
                pass
            return False

        # Switch back to main content before publishing
        try:
            driver.switch_to.default_content()
        except:
            pass

        # Publish
        if not DRY_RUN:
            logger.info("Publishing post...")
            sleep_opt(1)

            try:
                publish_btn = None

                # Publish button xpaths - exact matches first to avoid false positives
                publish_xpaths = [
                    "//button[normalize-space(.)='Post']",
                    "//button[normalize-space(.)='Pos']",
                    "//button[normalize-space(.)='Publish']",
                    "//button[normalize-space(.)='Kirim']",
                    "//button[normalize-space(.)='Submit']",
                    "//button[@aria-label='Post']",
                    "//button[@aria-label='Pos']",
                    "//button[@aria-label='Publish']",
                    "//div[@role='button'][normalize-space(.)='Post']",
                    "//div[@role='button'][normalize-space(.)='Pos']",
                    "//div[@role='button'][normalize-space(.)='Publish']",
                    "//*[@role='button'][normalize-space(.)='Post']",
                    "//*[@role='button'][normalize-space(.)='Pos']",
                ]

                def search_publish_in_context(context_name):
                    """Search for publish button in current context"""
                    nonlocal publish_btn
                    for xp in publish_xpaths:
                        try:
                            btns = driver.find_elements(By.XPATH, xp)
                            for btn in btns:
                                if btn.is_displayed():
                                    btn_text = (btn.text or btn.get_attribute('aria-label') or '').strip()
                                    logger.info(f"Found publish button in {context_name}: '{btn_text}' with xpath: {xp}")
                                    publish_btn = btn
                                    return True
                        except:
                            continue

                # If still not found, search by button containing common action keywords
                if not publish_btn:
                    logger.warning("Standard xpaths failed. Full page button scan...")
                    time.sleep(1)

                    # Save screenshot before scanning
                    try:
                        screenshot_path = str(SCREENSHOT_DIR / f"{profile_name}_before_button_scan.png")
                        driver.save_screenshot(screenshot_path)
                        logger.info(f"Debug screenshot: {screenshot_path}")
                    except:
                        pass

                    # Find ALL interactive elements
                    all_buttons = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //a[@role='button'] | //input[@type='button'] | //input[@type='submit']")
                    logger.info(f"Found {len(all_buttons)} total interactive elements")

                    for idx, btn in enumerate(all_buttons):
                        try:
                            btn_text = (btn.text or btn.get_attribute('innerText') or btn.get_attribute('aria-label') or '').strip()
                            btn_text_lower = btn_text.lower()

                            # Skip "Create post" and navigation buttons
                            if any(skip in btn_text_lower for skip in ['create', 'buat', 'menu', 'search', 'google', 'close', 'back', 'cancel', 'batal']):
                                continue

                            # Match publish/post/submit keywords
                            if any(kw == btn_text_lower for kw in ['post', 'pos', 'publish', 'kirim', 'submit', 'simpan']):
                                if btn.is_displayed():
                                    logger.info(f"Found publish button via scan in {context_name}: '{btn_text}'")
                                    publish_btn = btn
                                    return True
                        except:
                            continue
                    return False

                # Step 1: Search in main content
                logger.info("Searching for publish button in main content...")
                if not search_publish_in_context("main content"):
                    # Step 2: Search in ALL iframes
                    logger.info("Publish button not in main content, checking iframes...")
                    iframes = driver.find_elements(By.XPATH, "//iframe")
                    for i, iframe in enumerate(iframes):
                        try:
                            driver.switch_to.frame(iframe)
                            logger.info(f"Checking iframe {i} for publish button...")
                            if search_publish_in_context(f"iframe {i}"):
                                logger.info(f"Publish button found in iframe {i}")
                                break
                            driver.switch_to.default_content()
                        except:
                            try:
                                driver.switch_to.default_content()
                            except:
                                pass

                if not publish_btn:
                    logger.error("Publish button NOT FOUND in any context")
                    try:
                        driver.switch_to.default_content()
                        driver.save_screenshot(str(SCREENSHOT_DIR / f"{profile_name}_publish_button_not_found.png"))
                    except:
                        pass
                    return False

                logger.info("Clicking publish button...")
                driver.execute_script("arguments[0].scrollIntoView(true);", publish_btn)
                sleep_opt(0.5)

                try:
                    publish_btn.click()
                except Exception as e:
                    logger.warning(f"Direct click failed: {e}, trying JS click")
                    driver.execute_script("arguments[0].click();", publish_btn)

                logger.info("Publish button clicked")
                sleep_opt(1.5)

                logger.info(f"Post published successfully for: {profile_name}")

                # Switch back to main content
                try:
                    driver.switch_to.default_content()
                except:
                    pass

                return True

            except Exception as e:
                logger.error(f"Publish failed: {e}")
                try:
                    driver.switch_to.default_content()
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{profile_name}_publish_error.png"))
                except:
                    pass
                return False
        else:
            logger.info("DRY_RUN: Form filled but not published")
            return True

    except Exception as e:
        logger.error(f"Form fill/publish failed: {e}")
        return False


def process_store(driver, store_code: str, wa_link: str):
    """Process single store: search -> find ALL profiles -> post to each"""
    import time

    try:
        logger.info(f"Processing: {store_code}")
        update_status(store_code, "PROCESSING")

        # Step 1: Open GMB
        logger.info("Opening GMB...")
        driver.get(GMB_URL)
        sleep_opt(1)

        # Step 2: Find search field and search store code
        logger.info(f"Searching for: {store_code}")
        search_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
        )
        search_field.clear()
        search_field.send_keys(store_code)
        logger.info("Entered store code in search")
        sleep_opt(0.5)

        # Step 3: Press Enter
        search_field.send_keys(Keys.ENTER)
        logger.info("Pressed Enter")
        sleep_opt(2)

        # Debug: Check URL and take screenshot
        current_url = driver.current_url
        logger.info(f"Current URL: {current_url}")
        try:
            driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_after_search.png"))
        except:
            pass

        # Step 4: Find ALL add post buttons (all profiles for this store)
        logger.info("Looking for all add post buttons (profiles)...")

        # Wait for page to fully load after search
        time.sleep(5)

        # Try multiple times with increasing wait
        add_post_buttons = []
        for attempt in range(3):
            all_btns = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //a[@role='button'] | //span[@role='button']")
            logger.info(f"Attempt {attempt + 1}: Total buttons found: {len(all_btns)}")

            # Log all button texts for debugging
            if attempt == 0:
                for i, btn in enumerate(all_btns):
                    try:
                        btn_text = (btn.get_attribute('innerText') or btn.get_attribute('aria-label') or btn.get_attribute('title') or '').strip()
                        if btn_text and btn.is_displayed():
                            logger.info(f"  Button [{i}]: '{btn_text[:60]}'")
                    except:
                        continue

            for btn in all_btns:
                try:
                    btn_text = btn.get_attribute('innerText') or btn.get_attribute('aria-label') or btn.get_attribute('title') or ''
                    btn_text_lower = btn_text.lower().strip()

                    # Expanded matching: postingan, add post, buat post, create post, tambah postingan, + Postingan
                    match = False
                    if 'postingan' in btn_text_lower:
                        match = True
                    elif 'add post' in btn_text_lower:
                        match = True
                    elif 'post' in btn_text_lower and 'buat' in btn_text_lower:
                        match = True
                    elif 'create post' in btn_text_lower:
                        match = True
                    elif 'tambah' in btn_text_lower and 'post' in btn_text_lower:
                        match = True
                    elif 'add update' in btn_text_lower:
                        match = True
                    elif 'buat' in btn_text_lower and 'update' in btn_text_lower:
                        match = True

                    if match and btn.is_displayed():
                        # Avoid duplicates
                        if btn not in add_post_buttons:
                            add_post_buttons.append(btn)
                            logger.info(f"Found profile button [{len(add_post_buttons)}]: {btn_text[:50]}")
                except:
                    continue

            if add_post_buttons:
                break

            # Wait and retry
            logger.info(f"No buttons found yet, waiting... (attempt {attempt + 1}/3)")
            time.sleep(3)

        if not add_post_buttons:
            logger.error("No add post buttons found after 3 attempts")
            try:
                driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_no_add_post_buttons.png"))
                logger.info(f"Debug screenshot saved: {store_code}_no_add_post_buttons.png")
            except:
                pass
            raise Exception("No profiles found for store code")

        logger.info(f"Found {len(add_post_buttons)} profiles to post to")

        # Step 5: Post to each profile
        success_count = 0
        failed_count = 0
        processed_count = 0

        while processed_count < len(add_post_buttons):
            try:
                profile_idx = processed_count + 1
                logger.info(f"=== Processing profile {profile_idx}/{len(add_post_buttons)} ===")

                # Always re-fetch buttons from fresh search
                logger.info("Re-searching to get fresh button list...")
                driver.get(GMB_URL)
                sleep_opt(1)

                search_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
                )
                search_field.clear()
                search_field.send_keys(store_code)
                sleep_opt(0.5)
                search_field.send_keys(Keys.ENTER)
                logger.info("Re-searched store code")
                sleep_opt(1.5)

                # Find all buttons again
                all_btns = driver.find_elements(By.XPATH, "//button | //div[@role='button']")
                btn_count = 0
                add_post_btn = None

                for btn in all_btns:
                    try:
                        btn_text = btn.get_attribute('innerText') or btn.get_attribute('aria-label') or btn.get_attribute('title') or ''
                        btn_text_lower = btn_text.lower()
                        if 'postingan' in btn_text_lower or ('post' in btn_text_lower and 'buat' in btn_text_lower) or 'add post' in btn_text_lower:
                            if btn.is_displayed():
                                btn_count += 1
                                if btn_count == profile_idx:
                                    add_post_btn = btn
                                    logger.info(f"Found button for profile {profile_idx}")
                                    break
                    except:
                        continue

                if not add_post_btn:
                    logger.warning(f"Profile {profile_idx} button not found - all profiles likely processed")
                    break

                driver.execute_script("arguments[0].scrollIntoView(true);", add_post_btn)
                sleep_opt(0.3)
                driver.execute_script("arguments[0].click();", add_post_btn)
                logger.info(f"Clicked add post button for profile {profile_idx}")
                sleep_opt(1)

                # Fill form and publish for this profile
                if fill_form_and_publish(driver, f"Profile {profile_idx}", wa_link):
                    success_count += 1
                    logger.info(f"Profile {profile_idx} posted successfully")
                else:
                    failed_count += 1
                    logger.warning(f"Profile {profile_idx} post failed")

                processed_count += 1

            except Exception as e:
                logger.error(f"Profile {profile_idx} processing failed: {e}")
                failed_count += 1
                try:
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_profile{profile_idx}_error.png"))
                except:
                    pass

        # Update final status
        if success_count == len(add_post_buttons):
            logger.info(f"All {success_count} profiles posted successfully")
            update_status(store_code, "SUCCESS")
        elif success_count > 0:
            logger.info(f"Partial success: {success_count}/{len(add_post_buttons)} profiles posted")
            update_status(store_code, "PARTIAL", f"{success_count}/{len(add_post_buttons)} profiles")
        else:
            logger.error(f"Failed to post to any profile")
            update_status(store_code, "FAILED", "All profiles failed")

        return True

    except Exception as e:
        logger.error(f"Store processing failed: {e}")
        try:
            driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_error.png"))
        except:
            pass
        update_status(store_code, "FAILED", str(e))


def fill_form_and_publish_multi(driver, profile_name: str, post_config: dict, property_id: str):
    """Fill form and publish post with custom config. Returns True if success."""
    try:
        import time

        caption = post_config["caption"]
        image_path = post_config["image"]
        cta_label = post_config["cta"]
        url = post_config["url"]
        post_id = post_config["id"]

        logger.info(f"Publishing post {post_id} to {profile_name}")
        logger.info(f"  Caption: {caption[:50]}...")
        logger.info(f"  CTA: {cta_label}, URL: {url[:50]}...")
        sleep_opt(1.5)

        driver.switch_to.default_content()
        sleep_opt(0.5)

        iframes = driver.find_elements(By.XPATH, "//iframe")
        logger.info(f"Found {len(iframes)} iframes")

        desc_field = None

        for i, iframe in enumerate(iframes):
            try:
                logger.info(f"Checking iframe {i}...")
                driver.switch_to.frame(iframe)
                sleep_opt(0.3)

                textareas = driver.find_elements(By.XPATH, "//textarea")
                logger.info(f"  Iframe {i}: found {len(textareas)} textareas")

                if textareas:
                    desc_field = textareas[0]
                    logger.info(f"Found description in iframe {i}")
                    break

                driver.switch_to.default_content()
            except Exception as e:
                logger.debug(f"Iframe {i} check failed: {e}")
                try:
                    driver.switch_to.default_content()
                except:
                    pass
                continue

        if not desc_field:
            logger.info("Checking main content for textarea...")
            driver.switch_to.default_content()
            sleep_opt(0.3)
            textareas = driver.find_elements(By.XPATH, "//textarea")
            logger.info(f"Main content: found {len(textareas)} textareas")
            if textareas:
                desc_field = textareas[0]
                logger.info("Found textarea in main content")

        if not desc_field:
            logger.error(f"Description field not found for {post_id}")
            try:
                driver.save_screenshot(str(SCREENSHOT_DIR / f"{property_id}_{post_id}_desc_field_error.png"))
            except:
                pass
            return False

        try:
            desc_field.click()
        except:
            driver.execute_script("arguments[0].click();", desc_field)

        sleep_opt(0.3)
        desc_field.clear()
        desc_field.send_keys(caption)
        logger.info(f"Caption filled for {post_id}")
        sleep_opt(0.5)

        driver.switch_to.default_content()
        time.sleep(1)

        logger.info(f"Uploading image for {post_id}...")
        file_input = None

        try:
            file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
            if file_inputs:
                file_input = file_inputs[0]
                logger.info("File input found in main content")
        except:
            pass

        if not file_input:
            iframes = driver.find_elements(By.XPATH, "//iframe")
            for i, iframe in enumerate(iframes):
                try:
                    driver.switch_to.frame(iframe)
                    file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                    if file_inputs:
                        file_input = file_inputs[0]
                        logger.info(f"File input found in iframe {i}")
                        break
                    driver.switch_to.default_content()
                except:
                    try:
                        driver.switch_to.default_content()
                    except:
                        pass

        if not file_input:
            driver.switch_to.default_content()
            try:
                file_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
                )
                logger.info("File input found after wait")
            except Exception as e:
                logger.error(f"File input not found for {post_id}: {e}")
                try:
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{property_id}_{post_id}_no_file_input.png"))
                except:
                    pass
                return False

        img_file = Path(image_path)
        if not img_file.is_absolute():
            img_file = Path.cwd() / image_path

        if not img_file.exists():
            logger.error(f"Image file not found for {post_id}: {img_file}")
            return False

        file_input.send_keys(str(img_file.absolute()))
        logger.info(f"Image uploaded for {post_id}: {image_path}")
        time.sleep(3)

        logger.info(f"Selecting CTA for {post_id}: {cta_label}")
        sleep_opt(0.5)

        cta_found = False

        def find_all_buttons():
            btns = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //span[@role='button'] | //a[@role='button']")
            return btns

        try:
            tombol_btn = None
            buttons = find_all_buttons()

            cta_trigger_keywords = ['tombol', 'button', 'add a button', 'tambah tombol']

            for btn in buttons:
                try:
                    btn_text = (btn.text or btn.get_attribute('aria-label') or "").strip()
                    btn_text_lower = btn_text.lower()

                    for keyword in cta_trigger_keywords:
                        if keyword in btn_text_lower:
                            if btn.is_displayed():
                                tombol_btn = btn
                                logger.info(f"Found CTA trigger button: '{btn_text}'")
                                break
                    if tombol_btn:
                        break
                except:
                    continue

            if not tombol_btn:
                logger.info("CTA trigger not found in main content, checking iframes...")
                iframes = driver.find_elements(By.XPATH, "//iframe")
                for i, iframe in enumerate(iframes):
                    try:
                        driver.switch_to.frame(iframe)
                        buttons = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //span[@role='button']")
                        for btn in buttons:
                            try:
                                btn_text = (btn.text or btn.get_attribute('aria-label') or "").strip()
                                btn_text_lower = btn_text.lower()
                                for keyword in cta_trigger_keywords:
                                    if keyword in btn_text_lower:
                                        if btn.is_displayed():
                                            tombol_btn = btn
                                            logger.info(f"Found CTA trigger in iframe {i}: '{btn_text}'")
                                            break
                                if tombol_btn:
                                    break
                            except:
                                continue
                        if tombol_btn:
                            break
                        driver.switch_to.default_content()
                    except:
                        try:
                            driver.switch_to.default_content()
                        except:
                            pass

            if tombol_btn:
                driver.execute_script("arguments[0].scrollIntoView(true);", tombol_btn)
                sleep_opt(0.3)
                driver.execute_script("arguments[0].click();", tombol_btn)
                logger.info(f"Clicked +Tombol button for {post_id}")
                time.sleep(2)

                logger.info(f"Looking for CTA combobox for {post_id}...")
                try:
                    cta_combos = driver.find_elements(By.XPATH, "//*[contains(text(),'Tidak ada')]")
                    for combo in cta_combos:
                        if combo.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", combo)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", combo)
                            logger.info(f"Clicked CTA combobox for {post_id}")
                            time.sleep(2)
                            break
                except Exception as e:
                    logger.debug(f"CTA combobox click failed: {e}")

                candidates = get_cta_candidates(cta_label)
                logger.info(f"CTA candidates for {post_id}: {candidates}")

                for cand in candidates:
                    try:
                        logger.info(f"  Searching for: '{cand}'")
                        opts = driver.find_elements(By.XPATH, f"//*[normalize-space(.)='{cand}'][@role='option' or @role='menuitem'] | //*[normalize-space(.)='{cand}'][contains(@class, 'option')]")
                        if not opts:
                            opts = driver.find_elements(By.XPATH, f"//*[normalize-space(.)='{cand}']")
                        for opt in opts:
                            try:
                                if opt.is_displayed():
                                    logger.info(f"    Found and clicking '{cand}'")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", opt)
                                    sleep_opt(0.2)
                                    driver.execute_script("arguments[0].click();", opt)
                                    logger.info(f"Selected CTA for {post_id}: {cand}")
                                    cta_found = True
                                    break
                            except:
                                continue
                        if cta_found:
                            break
                    except Exception as e:
                        logger.debug(f"CTA search failed: {e}")

            else:
                logger.warning(f"CTA trigger button not found for {post_id}")

        except Exception as e:
            logger.warning(f"CTA selection failed for {post_id}: {e}")

        if not cta_found:
            logger.warning(f"Could not select CTA '{cta_label}' for {post_id} - continuing anyway")

        sleep_opt(0.5)

        driver.switch_to.default_content()
        time.sleep(1)

        logger.info(f"Filling URL for {post_id}...")
        sleep_opt(1)

        url_field = None

        def find_url_field_in_current_context():
            nonlocal url_field
            all_inputs = driver.find_elements(By.XPATH, "//input[@type='text' or @type='url' or not(@type)]")
            logger.info(f"Found {len(all_inputs)} inputs in current context")

            for inp in all_inputs:
                try:
                    if not inp.is_displayed():
                        continue
                    inp_placeholder = inp.get_attribute('placeholder') or ""
                    inp_aria = inp.get_attribute('aria-label') or ""
                    inp_name = inp.get_attribute('name') or ""
                    inp_id = inp.get_attribute('id') or ""

                    all_attrs = (inp_placeholder + inp_aria + inp_name + inp_id).lower()
                    if any(x in all_attrs for x in ['link', 'url', 'whatsapp', 'http', 'website', 'tautan']):
                        url_field = inp
                        logger.info("Found URL field by label")
                        return True
                except:
                    continue

            for inp in all_inputs:
                try:
                    if inp.is_displayed() and (inp.get_attribute('value') or "") == "":
                        inp_role = inp.get_attribute('role') or ""
                        if inp_role != 'combobox':
                            url_field = inp
                            logger.info("Using first empty text input as URL field (fallback)")
                            return True
                except:
                    continue
            return False

        if not find_url_field_in_current_context():
            logger.info(f"URL field not found in main content for {post_id}, checking iframes...")
            iframes = driver.find_elements(By.XPATH, "//iframe")
            for i, iframe in enumerate(iframes):
                try:
                    driver.switch_to.frame(iframe)
                    logger.info(f"Checking iframe {i} for URL field...")
                    if find_url_field_in_current_context():
                        logger.info(f"Found URL field in iframe {i}")
                        break
                    driver.switch_to.default_content()
                except:
                    try:
                        driver.switch_to.default_content()
                    except:
                        pass

        if url_field:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", url_field)
                sleep_opt(0.3)
                url_field.clear()
                url_field.send_keys(url)
                logger.info(f"URL filled for {post_id}")
            except Exception as e:
                logger.error(f"Failed to fill URL for {post_id}: {e}")
                return False
        else:
            logger.warning(f"URL field not found for {post_id}")
            try:
                driver.switch_to.default_content()
                driver.save_screenshot(str(SCREENSHOT_DIR / f"{property_id}_{post_id}_url_field_not_found.png"))
            except:
                pass
            return False

        try:
            driver.switch_to.default_content()
        except:
            pass

        if not DRY_RUN:
            logger.info(f"Publishing post {post_id}...")
            sleep_opt(1)

            try:
                publish_btn = None

                publish_xpaths = [
                    "//button[normalize-space(.)='Post']",
                    "//button[normalize-space(.)='Pos']",
                    "//button[normalize-space(.)='Publish']",
                    "//button[normalize-space(.)='Kirim']",
                    "//button[normalize-space(.)='Submit']",
                    "//button[@aria-label='Post']",
                    "//button[@aria-label='Pos']",
                    "//button[@aria-label='Publish']",
                    "//div[@role='button'][normalize-space(.)='Post']",
                    "//div[@role='button'][normalize-space(.)='Pos']",
                    "//div[@role='button'][normalize-space(.)='Publish']",
                    "//*[@role='button'][normalize-space(.)='Post']",
                    "//*[@role='button'][normalize-space(.)='Pos']",
                ]

                def search_publish_in_context(context_name):
                    nonlocal publish_btn
                    for xp in publish_xpaths:
                        try:
                            btns = driver.find_elements(By.XPATH, xp)
                            for btn in btns:
                                if btn.is_displayed():
                                    btn_text = (btn.text or btn.get_attribute('aria-label') or '').strip()
                                    logger.info(f"Found publish button in {context_name}: '{btn_text}'")
                                    publish_btn = btn
                                    return True
                        except:
                            continue

                logger.info(f"Searching for publish button for {post_id}...")
                if not search_publish_in_context("main content"):
                    logger.info(f"Publish button not in main content, checking iframes...")
                    iframes = driver.find_elements(By.XPATH, "//iframe")
                    for i, iframe in enumerate(iframes):
                        try:
                            driver.switch_to.frame(iframe)
                            logger.info(f"Checking iframe {i}...")
                            if search_publish_in_context(f"iframe {i}"):
                                logger.info(f"Publish button found in iframe {i}")
                                break
                            driver.switch_to.default_content()
                        except:
                            try:
                                driver.switch_to.default_content()
                            except:
                                pass

                if not publish_btn:
                    logger.error(f"Publish button NOT FOUND for {post_id}")
                    try:
                        driver.switch_to.default_content()
                        driver.save_screenshot(str(SCREENSHOT_DIR / f"{property_id}_{post_id}_publish_button_not_found.png"))
                    except:
                        pass
                    return False

                logger.info(f"Clicking publish button for {post_id}...")
                driver.execute_script("arguments[0].scrollIntoView(true);", publish_btn)
                sleep_opt(0.5)

                try:
                    publish_btn.click()
                except Exception as e:
                    logger.warning(f"Direct click failed: {e}, trying JS click")
                    driver.execute_script("arguments[0].click();", publish_btn)

                logger.info(f"Publish button clicked for {post_id}")
                sleep_opt(1.5)

                logger.info(f"Post {post_id} published successfully")

                try:
                    driver.switch_to.default_content()
                except:
                    pass

                return True

            except Exception as e:
                logger.error(f"Publish failed for {post_id}: {e}")
                try:
                    driver.switch_to.default_content()
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{property_id}_{post_id}_publish_error.png"))
                except:
                    pass
                return False
        else:
            logger.info(f"DRY_RUN: Form filled but not published for {post_id}")
            return True

    except Exception as e:
        logger.error(f"Form fill/publish failed for {post_id}: {e}")
        return False


def process_store_multi_post(driver, store_code: str, post_types: list):
    """Process single store: search -> find ALL properties -> post 3 types to each"""
    import time

    try:
        logger.info(f"=== MULTI-POST: Processing {store_code} ===")
        update_status(store_code, "PROCESSING")

        logger.info("Opening GMB...")
        driver.get(GMB_URL)
        sleep_opt(1)

        logger.info(f"Searching for: {store_code}")
        search_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
        )
        search_field.clear()
        search_field.send_keys(store_code)
        logger.info("Entered store code in search")
        sleep_opt(0.5)

        search_field.send_keys(Keys.ENTER)
        logger.info("Pressed Enter")
        sleep_opt(2)

        current_url = driver.current_url
        logger.info(f"Current URL: {current_url}")
        try:
            driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_multi_after_search.png"))
        except:
            pass

        logger.info("Looking for all add post buttons (properties)...")

        time.sleep(5)

        add_post_buttons = []
        for attempt in range(3):
            all_btns = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //a[@role='button'] | //span[@role='button']")
            logger.info(f"Attempt {attempt + 1}: Total buttons found: {len(all_btns)}")

            if attempt == 0:
                for i, btn in enumerate(all_btns):
                    try:
                        btn_text = (btn.get_attribute('innerText') or btn.get_attribute('aria-label') or btn.get_attribute('title') or '').strip()
                        if btn_text and btn.is_displayed():
                            logger.info(f"  Button [{i}]: '{btn_text[:60]}'")
                    except:
                        continue

            for btn in all_btns:
                try:
                    btn_text = btn.get_attribute('innerText') or btn.get_attribute('aria-label') or btn.get_attribute('title') or ''
                    btn_text_lower = btn_text.lower().strip()

                    match = False
                    if 'postingan' in btn_text_lower:
                        match = True
                    elif 'add post' in btn_text_lower:
                        match = True
                    elif 'post' in btn_text_lower and 'buat' in btn_text_lower:
                        match = True
                    elif 'create post' in btn_text_lower:
                        match = True
                    elif 'tambah' in btn_text_lower and 'post' in btn_text_lower:
                        match = True
                    elif 'add update' in btn_text_lower:
                        match = True
                    elif 'buat' in btn_text_lower and 'update' in btn_text_lower:
                        match = True

                    if match and btn.is_displayed():
                        if btn not in add_post_buttons:
                            add_post_buttons.append(btn)
                            logger.info(f"Found property button [{len(add_post_buttons)}]: {btn_text[:50]}")
                except:
                    continue

            if add_post_buttons:
                break

            logger.info(f"No buttons found yet, waiting... (attempt {attempt + 1}/3)")
            time.sleep(3)

        if not add_post_buttons:
            logger.error("No add post buttons found after 3 attempts")
            try:
                driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_multi_no_add_post_buttons.png"))
                logger.info(f"Debug screenshot saved: {store_code}_multi_no_add_post_buttons.png")
            except:
                pass
            update_status(store_code, "FAILED", "No profiles found")
            raise Exception("No profiles found for store code")

        logger.info(f"Found {len(add_post_buttons)} properties to post to")

        success_count = 0
        failed_count = 0
        processed_count = 0
        stats_by_property = {}

        while processed_count < len(add_post_buttons):
            try:
                profile_idx = processed_count + 1
                logger.info(f"\n=== Processing property {profile_idx}/{len(add_post_buttons)} ===")

                logger.info("Re-searching to get fresh button list...")
                driver.get(GMB_URL)
                sleep_opt(1)

                search_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
                )
                search_field.clear()
                search_field.send_keys(store_code)
                sleep_opt(0.5)
                search_field.send_keys(Keys.ENTER)
                logger.info("Re-searched store code")
                sleep_opt(1.5)

                all_btns = driver.find_elements(By.XPATH, "//button | //div[@role='button']")
                btn_count = 0
                add_post_btn = None

                for btn in all_btns:
                    try:
                        btn_text = btn.get_attribute('innerText') or btn.get_attribute('aria-label') or btn.get_attribute('title') or ''
                        btn_text_lower = btn_text.lower()
                        if 'postingan' in btn_text_lower or ('post' in btn_text_lower and 'buat' in btn_text_lower) or 'add post' in btn_text_lower:
                            if btn.is_displayed():
                                btn_count += 1
                                if btn_count == profile_idx:
                                    add_post_btn = btn
                                    logger.info(f"Found button for property {profile_idx}")
                                    break
                    except:
                        continue

                if not add_post_btn:
                    logger.warning(f"Property {profile_idx} button not found - all properties likely processed")
                    break

                property_id = f"prop_{store_code}_{profile_idx}"

                driver.execute_script("arguments[0].scrollIntoView(true);", add_post_btn)
                sleep_opt(0.3)
                driver.execute_script("arguments[0].click();", add_post_btn)
                logger.info(f"Clicked add post button for property {profile_idx}")
                sleep_opt(1)

                property_posts_ok = 0
                property_posts_failed = 0

                for post in post_types:
                    post_id = post["id"]
                    post_key = (store_code, property_id, post_id)
                    multi_status = load_multi_post_status()

                    if post_key in multi_status and multi_status[post_key]["status"] == "SUCCESS":
                        logger.info(f"Post {post_id} already SUCCESS for {property_id}, skipping")
                        property_posts_ok += 1
                        continue

                    if fill_form_and_publish_multi(driver, f"Property {profile_idx}", post, property_id):
                        update_multi_post_status(store_code, property_id, f"Property {profile_idx}", post_id, "SUCCESS" if not DRY_RUN else "DRY_RUN_READY")
                        property_posts_ok += 1
                        success_count += 1
                        logger.info(f"Post {post_id} published successfully for property {profile_idx}")
                    else:
                        update_multi_post_status(store_code, property_id, f"Property {profile_idx}", post_id, "FAILED")
                        property_posts_failed += 1
                        failed_count += 1
                        logger.warning(f"Post {post_id} failed for property {profile_idx}")

                    if post != post_types[-1]:
                        driver.get(GMB_URL)
                        sleep_opt(1)
                        search_field = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
                        )
                        search_field.clear()
                        search_field.send_keys(store_code)
                        sleep_opt(0.5)
                        search_field.send_keys(Keys.ENTER)
                        sleep_opt(1.5)

                        all_btns = driver.find_elements(By.XPATH, "//button | //div[@role='button']")
                        btn_count = 0
                        add_post_btn = None
                        for btn in all_btns:
                            try:
                                btn_text = btn.get_attribute('innerText') or btn.get_attribute('aria-label') or ''
                                btn_text_lower = btn_text.lower()
                                if 'postingan' in btn_text_lower or 'add post' in btn_text_lower:
                                    if btn.is_displayed():
                                        btn_count += 1
                                        if btn_count == profile_idx:
                                            add_post_btn = btn
                                            break
                            except:
                                continue

                        if add_post_btn:
                            driver.execute_script("arguments[0].scrollIntoView(true);", add_post_btn)
                            sleep_opt(0.3)
                            driver.execute_script("arguments[0].click();", add_post_btn)
                            sleep_opt(1)
                        else:
                            logger.warning(f"Could not re-find property button for next post")

                stats_by_property[property_id] = {"ok": property_posts_ok, "failed": property_posts_failed}
                processed_count += 1

            except Exception as e:
                logger.error(f"Property {profile_idx} processing failed: {e}")
                failed_count += 3
                try:
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_multi_property{profile_idx}_error.png"))
                except:
                    pass

        logger.info(f"\n=== MULTI-POST SUMMARY FOR {store_code} ===")
        logger.info(f"Total posts: {success_count + failed_count}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {failed_count}")

        if failed_count == 0 and success_count > 0:
            update_status(store_code, "SUCCESS")
        elif success_count > 0:
            update_status(store_code, "PARTIAL", f"{success_count} OK, {failed_count} failed")
        else:
            update_status(store_code, "FAILED", "No posts successful")

        return True

    except Exception as e:
        logger.error(f"Multi-post processing failed: {e}")
        try:
            driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_multi_error.png"))
        except:
            pass
        update_status(store_code, "FAILED", str(e))



    """Delete posts from ALL business profiles for a store

    Flow:
    1. Search store code → list profil bisnis muncul
    2. Find semua "lihat profil" buttons
    3. For each button:
       a. Klik "lihat profil" → tab baru terbuka
       b. Di profile page, cari button "Postingan"
       c. Klik "Postingan" → list post muncul
       d. For each post: klik titik 3 → klik delete
       e. Close tab, back to search
    """
    import time

    try:
        logger.info(f"Processing delete for: {store_code}")
        update_status(store_code, "PROCESSING")

        # Step 1: Open GMB
        logger.info("Opening GMB...")
        driver.get(GMB_URL)
        sleep_opt(1)

        # Step 2: Search store code
        logger.info(f"Searching for: {store_code}")
        search_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
        )
        search_field.clear()
        search_field.send_keys(store_code)
        logger.info("Entered store code")
        sleep_opt(0.5)

        search_field.send_keys(Keys.ENTER)
        logger.info("Pressed Enter")
        sleep_opt(1.5)

        # Step 3: Find all "lihat profil" / "see profile" buttons
        logger.info("Finding all 'lihat profil' buttons...")

        lihat_profil_buttons = []
        try:
            # Cari semua button yang text-nya mengandung "lihat profil" atau "see profile"
            buttons = driver.find_elements(By.XPATH, "//button | //a | //div[@role='button']")
            logger.info(f"Found {len(buttons)} clickable elements")

            for btn in buttons:
                try:
                    btn_text = btn.text or btn.get_attribute('aria-label') or ""
                    btn_text_lower = btn_text.lower()

                    if 'lihat profil' in btn_text_lower or 'see profile' in btn_text_lower:
                        if btn.is_displayed():
                            lihat_profil_buttons.append({
                                'element': btn,
                                'text': btn_text,
                                'href': btn.get_attribute('href') or ""
                            })
                            logger.info(f"  Found: {btn_text[:50]}")
                except:
                    pass
        except Exception as e:
            logger.error(f"Error finding buttons: {e}")

        logger.info(f"Found {len(lihat_profil_buttons)} 'lihat profil' buttons")

        if len(lihat_profil_buttons) == 0:
            logger.error("No 'lihat profil' buttons found")
            update_status(store_code, "FAILED", "No profile buttons found")
            return

        # Process each profile
        profile_ok = 0
        profile_failed = 0

        for profile_idx, btn_info in enumerate(lihat_profil_buttons):
            try:
                logger.info(f"\n=== Profile {profile_idx + 1}/{len(lihat_profil_buttons)} ===")

                # Get button reference dan URL sebelum navigate (untuk menghindari stale element)
                profile_url = btn_info.get('href')
                btn_text = btn_info.get('text')
                logger.info(f"Profile: {btn_text} | URL: {profile_url}")

                # Step 4a: Klik "lihat profil" button
                btn_elem = btn_info['element']

                # Record window handles sebelum klik
                windows_before = driver.window_handles
                logger.info(f"Windows before: {len(windows_before)}")

                # CHANGED: Navigate directly to profile URL instead of clicking button
                profile_url = btn_info.get('href')
                logger.info(f"Navigating directly to profile: {profile_url}")

                try:
                    driver.get(profile_url)
                    logger.info("Navigated to GMB profile page")
                    sleep_opt(2)
                except Exception as e:
                    logger.error(f"Navigation failed: {e}")
                    profile_failed += 1
                    continue

                # Take screenshot of profile page
                try:
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_profile_{profile_idx + 1}_gmb.png"))
                    logger.info(f"Screenshot: GMB profile page")
                except:
                    pass

                logger.info(f"Current URL: {driver.current_url}")

                # Step 5: Look for posts on GMB profile page directly
                # Posts might be in a list/carousel or need to find Postingan tab/button
                logger.info("Looking for 'Postingan' tab/button on profile...")

                postingan_btn = None
                buttons_on_page = driver.find_elements(By.XPATH, "//button | //a | //div[@role='button'] | //div[@role='tab']")
                logger.info(f"Found {len(buttons_on_page)} buttons/tabs on page")

                for btn in buttons_on_page:
                    try:
                        btn_text = btn.text or btn.get_attribute('aria-label') or ""
                        btn_text_lower = btn_text.lower()

                        if btn_text_lower == 'postingan' or 'post' in btn_text_lower:
                            if btn.is_displayed():
                                postingan_btn = btn
                                logger.info(f"Found 'Postingan' button/tab: {btn_text}")
                                break
                    except:
                        pass

                if postingan_btn:
                    logger.info("Clicking Postingan button/tab...")
                    driver.execute_script("arguments[0].scrollIntoView(true);", postingan_btn)
                    sleep_opt(0.3)
                    driver.execute_script("arguments[0].click();", postingan_btn)
                    logger.info("Clicked Postingan")
                    sleep_opt(1.5)
                else:
                    logger.info("No Postingan button found - posts might be visible already")
                    sleep_opt(1)

                # Take screenshot of postingan list/area
                try:
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_profile_{profile_idx + 1}_postingan_list.png"))
                    logger.info(f"Screenshot: postingan list area")
                except:
                    pass

                # Step 6: Find top-most post item dengan "Book your stay" caption
                logger.info("Finding top-most post item in list...")
                sleep_opt(0.5)

                js_find_top_post = """
                // Cari semua post items yang berisi "Book your stay"
                // Return yang paling atas (min top value)

                let posts = [];
                let allElements = document.querySelectorAll('div, article, li, [role="article"], [role="listitem"]');

                for (let elem of allElements) {
                    let text = elem.innerText || elem.textContent || '';
                    let rect = elem.getBoundingClientRect();

                    // Filter: berisi "book your stay", visible, reasonable size
                    if (text.toLowerCase().includes('book your stay') &&
                        text.length > 20 && text.length < 500 &&
                        rect.width > 80 && rect.height > 80 &&
                        rect.top >= 0 &&
                        elem.offsetParent !== null) {

                        // Cek bukan nested element
                        let parent = elem.parentElement;
                        let isNested = false;
                        for (let i = 0; i < 2; i++) {
                            if (parent && (parent.innerText || '').toLowerCase().includes('book your stay')) {
                                isNested = true;
                                break;
                            }
                            parent = parent ? parent.parentElement : null;
                        }

                        if (!isNested) {
                            posts.push({
                                elem: elem,
                                top: rect.top,
                                text: text.substring(0, 80),
                                tag: elem.tagName
                            });
                        }
                    }
                }

                // Sort by top position (find topmost)
                posts.sort((a, b) => a.top - b.top);

                if (posts.length > 0) {
                    let topPost = posts[0];
                    return {
                        found: true,
                        count: posts.length,
                        topText: topPost.text,
                        topTag: topPost.tag,
                        topPos: topPost.top
                    };
                }

                return {
                    found: false,
                    count: posts.length,
                    allElementsCount: allElements.length
                };
                """

                result = driver.execute_script(js_find_top_post)
                logger.info(f"Post search result: {result}")

                if not result.get('found'):
                    logger.warning(f"No posts found. Total elements: {result.get('allElementsCount')}")
                    profile_failed += 1
                    if new_windows:
                        driver.close()
                        sleep_opt(0.5)
                        driver.switch_to.window(windows_before[0])
                    continue

                logger.info(f"Found {result.get('count')} posts. Top post: {result.get('topText')}, Tag: {result.get('topTag')}")
                sleep_opt(0.3)

                # Step 7: Click top-most post caption
                logger.info("Clicking top-most post caption...")

                js_click_top_post = """
                // Cari dan klik post paling atas
                let posts = [];
                let allElements = document.querySelectorAll('div, article, li, [role="article"], [role="listitem"]');

                for (let elem of allElements) {
                    let text = elem.innerText || elem.textContent || '';
                    let rect = elem.getBoundingClientRect();

                    if (text.toLowerCase().includes('book your stay') &&
                        text.length > 20 && text.length < 500 &&
                        rect.width > 80 && rect.height > 80 &&
                        rect.top >= 0 &&
                        elem.offsetParent !== null) {

                        let parent = elem.parentElement;
                        let isNested = false;
                        for (let i = 0; i < 2; i++) {
                            if (parent && (parent.innerText || '').toLowerCase().includes('book your stay')) {
                                isNested = true;
                                break;
                            }
                            parent = parent ? parent.parentElement : null;
                        }

                        if (!isNested) {
                            posts.push({
                                elem: elem,
                                top: rect.top
                            });
                        }
                    }
                }

                // Sort by top (find topmost)
                posts.sort((a, b) => a.top - b.top);

                if (posts.length > 0) {
                    let topPost = posts[0].elem;
                    topPost.scrollIntoView({block: 'center'});

                    // Wait scroll
                    await new Promise(r => setTimeout(r, 300));

                    // Get center point
                    let rect = topPost.getBoundingClientRect();
                    let centerX = rect.left + rect.width / 2;
                    let centerY = rect.top + rect.height / 2;

                    // Find top-most element at that point
                    let clickTarget = document.elementFromPoint(centerX, centerY);
                    if (clickTarget) {
                        clickTarget.click();
                        return {success: true, clickedTag: clickTarget.tagName};
                    }
                }

                return {success: false};
                """

                try:
                    click_result = driver.execute_script(js_click_top_post)
                    if click_result.get('success'):
                        logger.info(f"Successfully clicked post. Clicked element: {click_result.get('clickedTag')}")
                        sleep_opt(1.5)

                        # Take screenshot to verify detail opened
                        try:
                            driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_profile_{profile_idx + 1}_post_detail.png"))
                            logger.info(f"Screenshot: post detail page")
                        except:
                            pass

                        logger.info(f"POST DETAIL OPENED SUCCESSFULLY FOR PROFILE {profile_idx + 1}")
                        profile_ok += 1

                        # TESTING ONLY - Do NOT delete
                        logger.info("TEST MODE: Not deleting, just verifying click works")

                    else:
                        logger.warning("Failed to click post")
                        profile_failed += 1

                except Exception as e:
                    logger.error(f"Click post failed: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    profile_failed += 1

                # Close and return to search for next profile
                logger.info("Going back to search results for next profile...")
                driver.get(GMB_URL)
                sleep_opt(1)

                # Re-search store code
                search_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
                )
                search_field.clear()
                search_field.send_keys(store_code)
                sleep_opt(0.5)
                search_field.send_keys(Keys.ENTER)
                logger.info("Re-searched store code")
                sleep_opt(1.5)

            except Exception as e:
                logger.error(f"Profile {profile_idx + 1} error: {e}")
                profile_failed += 1
                try:
                    if new_windows:
                        driver.close()
                        sleep_opt(0.5)
                        driver.switch_to.window(windows_before[0])
                except:
                    pass

        # Summary
        logger.info(f"\n=== Delete Summary ===")
        logger.info(f"Profiles processed: {profile_ok}, Failed: {profile_failed}")

        if profile_ok > 0:
            update_status(store_code, "SUCCESS" if profile_failed == 0 else "PARTIAL", f"{profile_ok} OK, {profile_failed} failed")
        else:
            update_status(store_code, "FAILED", f"All {profile_failed} profiles failed")

    except Exception as e:
        logger.error(f"Delete posts failed: {e}")
        update_status(store_code, "FAILED", str(e))


def main():
    logger.info("=== GMB Automation Start ===")
    logger.info(f"DRY_RUN: {DRY_RUN}, MAX_STORES: {MAX_STORES}")

    # Menu pilihan mode
    print("\n" + "="*50)
    print("GMB AUTOMATION - PILIH MODE")
    print("="*50)
    print("1. Add Post (Buat postingan baru)")
    print("2. Delete Post (Hapus postingan)")
    print("3. Multi-Post (3 Content Types)")
    print("="*50)

    while True:
        choice = input("Pilih mode (1, 2, atau 3): ").strip()
        if choice in ["1", "2", "3"]:
            if choice == "1":
                mode = "add_post"
            elif choice == "2":
                mode = "delete_post"
            else:
                mode = "multi_post"
            break
        print("Input tidak valid. Masukkan 1, 2, atau 3")

    logger.info(f"Mode dipilih: {mode}")

    try:
        if mode == "multi_post":
            init_multi_post_status_csv()
            post_types = load_multi_post_config()
        else:
            validate_config()

        init_status_csv()

        driver = create_driver()

        if not login_to_google(driver):
            logger.error("Login failed")
            driver.quit()
            sys.exit(1)

        stores = load_stores()
        status_map = load_status()

        pending = [s for s in stores if status_map.get(s["code"]) not in ["SUCCESS", "FAILED", "PROCESSING"]]
        if not pending:
            logger.info("No pending stores")
            driver.quit()
            return

        logger.info(f"Processing {len(pending)} pending stores")
        max_process = min(MAX_STORES, len(pending)) if MAX_STORES > 0 else len(pending)

        if mode == "add_post":
            for store in pending[:max_process]:
                try:
                    process_store(driver, store["code"], store["wa_link"])
                except Exception as e:
                    logger.error(f"Error: {e}")
        elif mode == "delete_post":
            for store in pending[:max_process]:
                try:
                    delete_posts(driver, store["code"])
                except Exception as e:
                    logger.error(f"Error: {e}")
        else:  # multi_post
            for store in pending[:max_process]:
                try:
                    process_store_multi_post(driver, store["code"], post_types)
                except Exception as e:
                    logger.error(f"Error: {e}")

        final_status = load_status()
        success_stores = [code for code, status in final_status.items() if status == "SUCCESS"]
        failed_stores = [code for code, status in final_status.items() if status == "FAILED"]
        dryrun_stores = [code for code, status in final_status.items() if status == "DRY_RUN_READY"]
        partial_stores = [code for code, status in final_status.items() if status == "PARTIAL"]
        total = len(final_status)

        logger.info("=" * 70)
        logger.info("SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total Stores: {total}")
        logger.info("-" * 70)

        if success_stores:
            logger.info(f"[SUCCESS] ({len(success_stores)}): {', '.join(success_stores[:10])}")

        if failed_stores:
            logger.info(f"[FAILED] ({len(failed_stores)}): {', '.join(failed_stores[:10])}")

        if partial_stores:
            logger.info(f"[PARTIAL] ({len(partial_stores)}): {', '.join(partial_stores[:10])}")

        if dryrun_stores:
            logger.info(f"[DRY_RUN] ({len(dryrun_stores)}): {', '.join(dryrun_stores[:10])}")

        if mode == "multi_post":
            logger.info("-" * 70)
            logger.info("MULTI-POST DETAILS:")
            multi_status = load_multi_post_status()
            total_posts = len(multi_status)
            successful_posts = sum(1 for st in multi_status.values() if st["status"] in ["SUCCESS", "DRY_RUN_READY"])
            failed_posts = sum(1 for st in multi_status.values() if st["status"] == "FAILED")
            logger.info(f"Total post attempts: {total_posts}")
            logger.info(f"Successful posts: {successful_posts}")
            logger.info(f"Failed posts: {failed_posts}")

        logger.info("=" * 70)

        logger.info("=== GMB Automation End ===")
        driver.quit()

    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
