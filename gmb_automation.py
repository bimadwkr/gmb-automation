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
DELETE_STATUS_FILE = Path("delete_status.csv")
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


def init_delete_status_csv():
    if not DELETE_STATUS_FILE.exists():
        with open(DELETE_STATUS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["store_code", "status", "timestamp", "error"])
            writer.writeheader()
        logger.info("Created delete_status.csv")


def load_delete_status():
    status = {}
    if DELETE_STATUS_FILE.exists():
        with open(DELETE_STATUS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                status[row["store_code"]] = row["status"]
    return status


def update_delete_status(store_code, status, error=""):
    all_status = load_delete_status()
    all_status[store_code] = status

    with open(DELETE_STATUS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["store_code", "status", "timestamp", "error"])
        writer.writeheader()
        for code, st in all_status.items():
            writer.writerow({
                "store_code": code,
                "status": st,
                "timestamp": datetime.now().isoformat(),
                "error": error,
            })
    logger.info(f"Store {store_code} [Delete]: {status}")


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
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-translate")
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
        time.sleep(1.5)  # Wait longer for page to fully load/redirect

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
            time.sleep(1.0)

        logger.info("Chrome browser is open. Please log in now.")

        # Wait for user to press Enter
        input("\nPress Enter after you have successfully logged in: ")

        logger.info("Continuing with automation...")
        time.sleep(1.0)

        # Verify login was successful — navigate to GMB and check properly
        driver.get(GMB_URL)
        time.sleep(1.5)

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
        time.sleep(1.0)

        # Switch to main content first
        driver.switch_to.default_content()
        time.sleep(0.1)

        # Check for iframes in modal
        iframes = driver.find_elements(By.XPATH, "//iframe")
        logger.info(f"Found {len(iframes)} iframes on page")

        desc_field = None

        # Try each iframe to find description field
        for i, iframe in enumerate(iframes):
            try:
                logger.info(f"Checking iframe {i}...")
                driver.switch_to.frame(iframe)
                time.sleep(0.15)

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
            time.sleep(0.15)
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

        time.sleep(0.15)
        desc_field.clear()
        desc_field.send_keys(DESCRIPTION)
        logger.info("Description filled")
        time.sleep(0.1)

        # IMPORTANT: Switch back to main content after filling description in iframe
        logger.info("Switching back to main content...")
        driver.switch_to.default_content()
        time.sleep(0.1)

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
        time.sleep(1.5)  # Wait longer for photo to upload

        # IMPORTANT: Make sure we're on main content before searching for CTA
        driver.switch_to.default_content()
        time.sleep(0.1)

        # Select CTA
        logger.info(f"Selecting CTA: {CTA}")
        time.sleep(0.1)

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
                time.sleep(0.15)
                driver.execute_script("arguments[0].click();", tombol_btn)
                logger.info("Clicked CTA trigger button")
                time.sleep(0.6)

                # Find and click CTA combobox (Tidak ada / None)
                logger.info("Looking for CTA combobox...")
                try:
                    cta_combo_keywords = ['Tidak ada', 'None', 'No button']
                    for kw in cta_combo_keywords:
                        cta_combos = driver.find_elements(By.XPATH, f"//*[contains(text(),'{kw}')]")
                        for combo in cta_combos:
                            if combo.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView(true);", combo)
                                time.sleep(0.1)
                                driver.execute_script("arguments[0].click();", combo)
                                logger.info(f"Clicked CTA combobox ('{kw}')")
                                time.sleep(0.6)
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
                                    time.sleep(0.1)
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

        time.sleep(0.1)

        # IMPORTANT: Switch back to main content before searching for URL field
        driver.switch_to.default_content()
        time.sleep(0.1)

        # Fill WA link - search in main content and all iframes
        logger.info("Filling WA link...")
        time.sleep(0.6)

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
                time.sleep(0.15)
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
            time.sleep(0.6)

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

                    # Fallback: scan all buttons but EXCLUDE "Create post" / "Create" buttons
                    all_buttons = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //input[@type='submit']")
                    for btn in all_buttons:
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
                time.sleep(0.1)

                try:
                    publish_btn.click()
                except Exception as e:
                    logger.warning(f"Direct click failed: {e}, trying JS click")
                    driver.execute_script("arguments[0].click();", publish_btn)

                logger.info("Publish button clicked")
                time.sleep(1.0)

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
        time.sleep(0.6)

        # Step 2: Find search field and search store code
        logger.info(f"Searching for: {store_code}")
        search_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
        )
        search_field.clear()
        search_field.send_keys(store_code)
        logger.info("Entered store code in search")
        time.sleep(0.1)

        # Step 3: Press Enter
        search_field.send_keys(Keys.ENTER)
        logger.info("Pressed Enter")
        time.sleep(1.0)

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
        time.sleep(1.5)

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
            time.sleep(1.0)

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

        for profile_idx, add_post_btn in enumerate(add_post_buttons, 1):
            try:
                logger.info(f"=== Processing profile {profile_idx}/{len(add_post_buttons)} ===")

                # Re-fetch button to avoid stale reference
                # (DOM may change after first post)
                if profile_idx > 1:
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
                                        break
                        except:
                            continue

                if not add_post_btn:
                    logger.warning(f"Profile {profile_idx} button not found (may have been posted already)")
                    continue

                driver.execute_script("arguments[0].scrollIntoView(true);", add_post_btn)
                time.sleep(0.15)
                driver.execute_script("arguments[0].click();", add_post_btn)
                logger.info(f"Clicked add post button for profile {profile_idx}")
                time.sleep(0.6)

                # Fill form and publish for this profile
                if fill_form_and_publish(driver, f"Profile {profile_idx}", wa_link):
                    success_count += 1
                    logger.info(f"Profile {profile_idx} posted successfully")
                else:
                    failed_count += 1
                    logger.warning(f"Profile {profile_idx} post failed")

                # After posting, go back to search results to find next profile
                if profile_idx < len(add_post_buttons):
                    logger.info("Returning to search results for next profile...")
                    driver.get(GMB_URL)
                    time.sleep(0.6)

                    # Re-search store code
                    search_field = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
                    )
                    search_field.clear()
                    search_field.send_keys(store_code)
                    time.sleep(0.1)
                    search_field.send_keys(Keys.ENTER)
                    time.sleep(1.0)

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


def delete_posts(driver, store_code: str):
    """Delete posts containing 'WhatsApp' from all business profiles for a store"""
    import time
    import re

    try:
        logger.info(f"Processing delete for store: {store_code} (DRY_RUN={DRY_RUN})")
        update_delete_status(store_code, "PROCESSING")

        # Step 1: Open GMB
        logger.info("Opening GMB...")
        driver.get(GMB_URL)
        time.sleep(0.6)

        # Step 2: Search store code
        logger.info(f"Searching for: {store_code}")
        search_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
        )
        search_field.clear()
        search_field.send_keys(store_code)
        time.sleep(0.1)
        search_field.send_keys(Keys.ENTER)
        time.sleep(1.0)

        # Step 3: Find all profile buttons ("lihat profil" / "see profile" / post buttons / cards)
        logger.info("Finding all profile buttons...")
        lihat_profil_buttons = []
        try:
            buttons = driver.find_elements(By.XPATH, "//button | //a | //div[@role='button'] | //span[@role='button']")
            for btn in buttons:
                try:
                    btn_text = btn.text or btn.get_attribute('aria-label') or btn.get_attribute('title') or ""
                    btn_text_lower = btn_text.lower().strip()

                    # Exclude global/unrelated buttons
                    if any(skip in btn_text_lower for skip in ['create post', 'buat postingan', 'business profile manager', 'pengelola profil bisnis']):
                        continue

                    if any(kw in btn_text_lower for kw in ['lihat profil', 'see profile', 'view profile', 'profil', 'profile', 'postingan', 'post', 'add post']):
                        if btn.is_displayed():
                            href = btn.get_attribute('href') or ""
                            if not any(b['element'] == btn or (href and b['href'] == href) for b in lihat_profil_buttons):
                                # Prioritize buttons with href or 'profile' / 'profil'
                                if href or 'profile' in btn_text_lower or 'profil' in btn_text_lower:
                                    lihat_profil_buttons.append({
                                        'element': btn,
                                        'text': btn_text,
                                        'href': href
                                    })
                                    logger.info(f"  Found profile button: {btn_text[:50]} (href: {href})")
                except:
                    pass
        except Exception as e:
            logger.error(f"Error finding profile buttons: {e}")

        logger.info(f"Found {len(lihat_profil_buttons)} profile buttons")

        if len(lihat_profil_buttons) == 0:
            logger.info("No explicit profile buttons found; treating current page as profile.")
            lihat_profil_buttons.append({
                'element': None,
                'text': 'Current Page',
                'href': ''
            })

        profile_ok = 0
        profile_failed = 0
        total_whatsapp_found = 0
        total_deleted = 0
        dry_run_matches = 0

        for profile_idx, btn_info in enumerate(lihat_profil_buttons):
            try:
                logger.info(f"\n=== Profile {profile_idx + 1}/{len(lihat_profil_buttons)} ===")
                profile_url = btn_info.get('href')
                btn_text = btn_info.get('text')
                logger.info(f"Profile: {btn_text} | URL: {profile_url}")

                if profile_url:
                    driver.get(profile_url)
                else:
                    driver.execute_script("arguments[0].click();", btn_info['element'])
                time.sleep(1.2)

                # Screenshot profile page
                try:
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_profile_{profile_idx + 1}_gmb.png"))
                except:
                    pass

                # Step 4: Look for 'Postingan' tab/button
                logger.info("Looking for 'Postingan' tab/button on profile...")
                postingan_btn = None
                buttons_on_page = driver.find_elements(By.XPATH, "//button | //a | //div[@role='button'] | //div[@role='tab']")
                for btn in buttons_on_page:
                    try:
                        b_text = btn.text or btn.get_attribute('aria-label') or ""
                        b_text_lower = b_text.lower()
                        if b_text_lower == 'postingan' or 'post' in b_text_lower:
                            if btn.is_displayed():
                                postingan_btn = btn
                                logger.info(f"Found 'Postingan' tab/button: {b_text}")
                                break
                    except:
                        pass

                if postingan_btn:
                    driver.execute_script("arguments[0].scrollIntoView(true);", postingan_btn)
                    time.sleep(0.15)
                    driver.execute_script("arguments[0].click();", postingan_btn)
                    time.sleep(1.0)
                else:
                    logger.info("No explicit Postingan button found - checking posts area directly")
                    time.sleep(0.6)

                # Step 5: Find matching WhatsApp posts using JS
                js_find_whatsapp_posts = """
                let cards = document.querySelectorAll('div[role="article"], article, div[role="listitem"]');
                let matches = [];
                for (let i = 0; i < cards.length; i++) {
                    let card = cards[i];
                    if (!card.offsetParent) continue;
                    let text = card.innerText || card.textContent || '';
                    let normalized = text.replace(/\\s+/g, ' ').trim();
                    let regex = /\\bwhatsapp\\b/i;
                    if (regex.test(normalized)) {
                        let rect = card.getBoundingClientRect();
                        if (rect.width > 40 && rect.height > 40 && rect.top >= 0) {
                            matches.push({
                                index: i,
                                text: normalized.substring(0, 120),
                                top: rect.top
                            });
                        }
                    }
                }
                matches.sort((a, b) => a.top - b.top);
                return matches;
                """

                whatsapp_posts = driver.execute_script(js_find_whatsapp_posts) or []
                logger.info(f"Inspected profile posts. Found {len(whatsapp_posts)} WhatsApp posts.")

                if not whatsapp_posts:
                    logger.info(f"No WhatsApp posts found on profile {profile_idx + 1}")
                    if len(lihat_profil_buttons) > 1:
                        driver.get(GMB_URL)
                        time.sleep(0.6)
                    continue

                total_whatsapp_found += len(whatsapp_posts)

                if DRY_RUN:
                    logger.info(f"DRY RUN MODE: Found {len(whatsapp_posts)} WhatsApp posts on profile {profile_idx + 1}. Not deleting.")
                    for p in whatsapp_posts:
                        logger.info(f"  [DRY RUN MATCH] Text: {p['text']}")
                    dry_run_matches += len(whatsapp_posts)
                    profile_ok += 1
                    if len(lihat_profil_buttons) > 1:
                        driver.get(GMB_URL)
                        time.sleep(0.6)
                    continue

                # Step 6: Delete each matching WhatsApp post
                profile_deleted_count = 0
                for post_idx in range(len(whatsapp_posts)):
                    try:
                        posts_current = driver.execute_script(js_find_whatsapp_posts) or []
                        if not posts_current:
                            logger.info("No more WhatsApp posts found during deletion loop.")
                            break

                        target_post_info = posts_current[0]
                        logger.info(f"Processing WhatsApp post: {target_post_info['text']}")

                        js_scroll_and_click_menu = """
                        let cards = document.querySelectorAll('div[role="article"], article, div[role="listitem"]');
                        let targetCard = null;

                        for (let card of cards) {
                            let text = card.innerText || card.textContent || '';
                            if (text.match(/\\bwhatsapp\\b/i)) {
                                let rect = card.getBoundingClientRect();
                                if (rect.width > 20 && rect.height > 20 && rect.top >= -200) {
                                    targetCard = card;
                                    break;
                                }
                            }
                        }

                        if (!targetCard) {
                            let all = document.querySelectorAll('*');
                            for (let el of all) {
                                if (el.children.length === 0 && (el.innerText || '').match(/\\bwhatsapp\\b/i)) {
                                    let card = el.closest('div[role="article"], article, div[role="listitem"], div');
                                    if (card) {
                                        targetCard = card;
                                        break;
                                    }
                                }
                            }
                        }

                        if (targetCard) {
                            targetCard.scrollIntoView({block: 'center'});

                            let searchRoot = targetCard.closest('[data-id]') || targetCard.closest('[role="none"]') || targetCard.parentElement.parentElement || targetCard.parentElement;

                            let candidates = searchRoot.querySelectorAll('button, [role="button"], span[role="button"], div[role="button"], svg, i');
                            let validCandidates = [];

                            for (let c of candidates) {
                                let el = c.tagName.toLowerCase() === 'svg' || c.tagName.toLowerCase() === 'i' ? c.closest('button, [role="button"], span, div') : c;
                                if (!el) continue;

                                let txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                                if (txt.includes('whatsapp') || txt.includes('book') || txt.includes('pesan') || txt.includes('reservasi') || txt.length > 40) {
                                    continue;
                                }

                                let rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    validCandidates.push({
                                        element: el,
                                        right: rect.right,
                                        top: rect.top,
                                        html: el.outerHTML.substring(0, 100)
                                    });
                                }
                            }

                            validCandidates.sort((a, b) => b.right - a.right);

                            if (validCandidates.length > 0) {
                                let best = validCandidates[0].element;
                                best.click();
                                return {
                                    success: true,
                                    message: 'Clicked menu button by excluding caption text',
                                    clickedHTML: best.outerHTML.substring(0, 100),
                                    count: validCandidates.length
                                };
                            } else {
                                let allBtns = searchRoot.querySelectorAll('button, [role="button"]');
                                for (let b of allBtns) {
                                    let t = (b.innerText || '').trim();
                                    if (!t.toLowerCase().includes('whatsapp') && t.length < 30) {
                                        b.click();
                                        return {success: true, message: 'Clicked fallback non-text button'};
                                    }
                                }

                                let btnInfo = [];
                                for (let b of allBtns) {
                                    btnInfo.push({text: b.innerText, aria: b.getAttribute('aria-label'), html: b.outerHTML.substring(0, 80)});
                                }
                                return {
                                    success: false,
                                    message: 'Menu button not found by exclusion filter',
                                    buttons: btnInfo,
                                    wrapperHTML: searchRoot.outerHTML.substring(0, 300)
                                };
                            }
                        }
                        return {success: false, message: 'Target card with WhatsApp not found'};
                        """

                        menu_res = driver.execute_script(js_scroll_and_click_menu) or {}
                        logger.info(f"Menu action result: {menu_res}")
                        if not menu_res.get('success'):
                            logger.warning(f"Could not open menu for post. Details: {menu_res}")
                            try:
                                driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_menu_not_found.png"))
                            except:
                                pass
                            continue

                        time.sleep(0.8)

                        js_click_delete = """
                        let menuItems = document.querySelectorAll('[role="menuitem"], li, button, a, div[role="option"]');
                        for (let item of menuItems) {
                            let txt = (item.innerText || item.textContent || '').trim().toLowerCase();
                            if (txt === 'delete' || txt === 'hapus' || txt.includes('delete') || txt.includes('hapus')) {
                                item.click();
                                return {success: true, actionText: txt};
                            }
                        }
                        return {success: false};
                        """
                        del_res = driver.execute_script(js_click_delete) or {}
                        logger.info(f"Delete option click result: {del_res}")
                        if not del_res.get('success'):
                            logger.warning("Delete menu option not found. Closing menu and skipping.")
                            try:
                                driver.find_element(By.TAG_NAME, 'body').click()
                            except:
                                pass
                            time.sleep(0.5)
                            continue

                        time.sleep(0.8)

                        js_confirm_deletion = """
                        let buttons = document.querySelectorAll('button, [role="button"]');
                        for (let btn of buttons) {
                            let txt = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                            let aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                            if (txt === 'delete' || txt === 'hapus' || txt === 'confirm' || txt === 'ya' || txt === 'ok' ||
                                aria.includes('delete') || aria.includes('hapus') || aria.includes('confirm')) {
                                if (!txt.includes('cancel') && !txt.includes('batal') && !aria.includes('cancel')) {
                                    btn.click();
                                    return {success: true, btnText: txt || aria};
                                }
                            }
                        }
                        return {success: false, message: 'No confirmation dialog or button needed'};
                        """
                        conf_res = driver.execute_script(js_confirm_deletion) or {}
                        logger.info(f"Confirmation result: {conf_res}")

                        time.sleep(1.5)
                        profile_deleted_count += 1
                        total_deleted += 1
                        logger.info("Successfully deleted WhatsApp post and verified.")

                    except Exception as e:
                        logger.error(f"Error deleting post: {e}")

                if profile_deleted_count > 0 or len(whatsapp_posts) > 0:
                    profile_ok += 1
                else:
                    profile_failed += 1

                driver.get(GMB_URL)
                time.sleep(0.6)

            except Exception as e:
                logger.error(f"Profile {profile_idx + 1} error: {e}")
                profile_failed += 1
                try:
                    driver.get(GMB_URL)
                    time.sleep(0.6)
                except:
                    pass

        if DRY_RUN:
            if dry_run_matches > 0:
                update_delete_status(store_code, "DRY_RUN_READY", f"Found {dry_run_matches} WhatsApp posts (Dry Run)")
            else:
                update_delete_status(store_code, "NO_MATCHES", "No WhatsApp posts found")
        else:
            if total_deleted > 0:
                status_val = "SUCCESS" if profile_failed == 0 else "PARTIAL"
                update_delete_status(store_code, status_val, f"Deleted {total_deleted} posts across profiles")
            elif total_whatsapp_found == 0:
                update_delete_status(store_code, "NO_MATCHES", "No WhatsApp posts found")
            else:
                update_delete_status(store_code, "FAILED", f"Found {total_whatsapp_found} WhatsApp posts but failed to delete")

    except Exception as e:
        logger.error(f"Delete posts failed for {store_code}: {e}")
        update_delete_status(store_code, "FAILED", str(e))


def main():
    logger.info("=== GMB Automation Start ===")
    logger.info(f"DRY_RUN: {DRY_RUN}, MAX_STORES: {MAX_STORES}")

    print("\n" + "="*50)
    print("GMB AUTOMATION - PILIH MODE")
    print("="*50)
    print("1. Add Post (Buat postingan baru)")
    print("2. Delete Post (Hapus postingan)")
    print("="*50)

    while True:
        choice = input("Pilih mode (1 atau 2): ").strip()
        if choice in ["1", "2"]:
            mode = "add_post" if choice == "1" else "delete_post"
            break
        print("Input tidak valid. Masukkan 1 atau 2")

    logger.info(f"Mode dipilih: {mode}")

    try:
        validate_config()
        if mode == "add_post":
            init_status_csv()
        else:
            init_delete_status_csv()

        driver = create_driver()

        if not login_to_google(driver):
            logger.error("Login failed")
            driver.quit()
            sys.exit(1)

        stores = load_stores()

        if mode == "add_post":
            status_map = load_status()
            pending = [s for s in stores if status_map.get(s["code"]) not in ["SUCCESS", "FAILED", "PROCESSING"]]
        else:
            delete_status_map = load_delete_status()
            pending = [s for s in stores if delete_status_map.get(s["code"]) not in ["SUCCESS", "FAILED", "PROCESSING"]]

        if not pending:
            logger.info("No pending stores")
            driver.quit()
            return

        logger.info(f"Processing {len(pending)} pending stores for {mode}")
        max_process = min(MAX_STORES, len(pending)) if MAX_STORES > 0 else len(pending)

        if mode == "add_post":
            for store in pending[:max_process]:
                try:
                    process_store(driver, store["code"], store["wa_link"])
                except Exception as e:
                    logger.error(f"Error: {e}")
        else:
            for store in pending[:max_process]:
                try:
                    delete_posts(driver, store["code"])
                except Exception as e:
                    logger.error(f"Error: {e}")

        if mode == "add_post":
            final_status = load_status()
            success_stores = [code for code, status in final_status.items() if status == "SUCCESS"]
            failed_stores = [code for code, status in final_status.items() if status == "FAILED"]
            dryrun_stores = [code for code, status in final_status.items() if status == "DRY_RUN_OK"]
        else:
            final_status = load_delete_status()
            success_stores = [code for code, status in final_status.items() if status == "SUCCESS"]
            failed_stores = [code for code, status in final_status.items() if status == "FAILED"]
            dryrun_stores = [code for code, status in final_status.items() if status == "DRY_RUN_READY"]

        total = len(final_status)

        logger.info("=" * 70)
        logger.info("SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total Stores: {total}")
        logger.info("-" * 70)

        if success_stores:
            logger.info(f"[SUCCESS] ({len(success_stores)}): {', '.join(success_stores)}")

        if failed_stores:
            logger.info(f"[FAILED] ({len(failed_stores)}): {', '.join(failed_stores)}")

        if dryrun_stores:
            logger.info(f"[DRY_RUN] ({len(dryrun_stores)}): {', '.join(dryrun_stores)}")

        logger.info("=" * 70)
        logger.info("=== GMB Automation End =='")
        driver.quit()

    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
