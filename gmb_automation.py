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
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
SCREENSHOT_DIR = LOG_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "gmb_automation.log"),
        logging.StreamHandler(sys.stdout),
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


def create_driver():
    options = ChromeOptions()
    options.add_argument(f"--user-data-dir={os.path.abspath(CHROME_PROFILE)}")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-blink-features=AutomationControlled")
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
        time.sleep(5)  # Wait longer for page to fully load/redirect

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
        time.sleep(3)

        # Verify login was successful — navigate to GMB and check properly
        driver.get(GMB_URL)
        time.sleep(5)

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
        time.sleep(3)

        # Switch to main content first
        driver.switch_to.default_content()
        time.sleep(1)

        # Check for iframes in modal
        iframes = driver.find_elements(By.XPATH, "//iframe")
        logger.info(f"Found {len(iframes)} iframes on page")

        desc_field = None

        # Try each iframe to find description field
        for i, iframe in enumerate(iframes):
            try:
                logger.info(f"Checking iframe {i}...")
                driver.switch_to.frame(iframe)
                time.sleep(0.5)

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
            time.sleep(0.5)
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

        time.sleep(0.5)
        desc_field.clear()
        desc_field.send_keys(DESCRIPTION)
        logger.info("Description filled")
        time.sleep(1)

        # Upload photo
        logger.info("Uploading photo...")
        file_input = None
        try:
            file_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
            )
            logger.info("File input found")
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
        time.sleep(1)

        cta_found = False

        try:
            # Find +Tombol button
            tombol_btn = None
            buttons = driver.find_elements(By.XPATH, "//button | //div[@role='button']")
            logger.info(f"Found {len(buttons)} buttons on page")

            for btn in buttons:
                try:
                    btn_text = btn.text or btn.get_attribute('aria-label') or ""
                    if 'Tombol' in btn_text or ('+' in btn_text and btn.is_displayed()):
                        tombol_btn = btn
                        logger.info(f"Found +Tombol button")
                        break
                except:
                    continue

            if tombol_btn:
                driver.execute_script("arguments[0].scrollIntoView(true);", tombol_btn)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", tombol_btn)
                logger.info("Clicked +Tombol button")
                time.sleep(2)

                # Find and click CTA combobox (Tidak ada)
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
                        for opt in opts:
                            try:
                                if opt.is_displayed():
                                    logger.info(f"    Found and clicking '{cand}'")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", opt)
                                    time.sleep(0.3)
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
                logger.warning("+Tombol button not found")

        except Exception as e:
            logger.warning(f"CTA selection failed: {e}")

        if not cta_found:
            logger.warning(f"Could not select CTA '{CTA}' - continuing anyway")

        time.sleep(1)

        # Fill WA link
        logger.info("Filling WA link...")
        time.sleep(2)

        url_field = None
        all_inputs = driver.find_elements(By.XPATH, "//input[@type='text' or @type='url']")
        logger.info(f"Found {len(all_inputs)} text inputs on page")

        for inp in all_inputs:
            try:
                if not inp.is_displayed():
                    continue

                inp_placeholder = inp.get_attribute('placeholder') or ""
                inp_value = inp.get_attribute('value') or ""
                inp_aria = inp.get_attribute('aria-label') or ""

                logger.info(f"  Input: placeholder='{inp_placeholder}', aria='{inp_aria}'")

                # Check for link-related field
                if any(x in inp_placeholder.lower() or x in inp_aria.lower() for x in ['link', 'url', 'whatsapp']):
                    url_field = inp
                    logger.info("Found URL field by label")
                    break
            except:
                continue

        # If not found, use first empty text input
        if not url_field:
            for inp in all_inputs:
                try:
                    if inp.is_displayed() and inp.get_attribute('value') == "":
                        url_field = inp
                        logger.info("Using first empty text input as URL field")
                        break
                except:
                    continue

        if url_field:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", url_field)
                time.sleep(0.5)
                url_field.clear()
                url_field.send_keys(wa_link)
                logger.info(f"WA link filled")
            except Exception as e:
                logger.error(f"Failed to fill URL: {e}")
                return False
        else:
            logger.warning("URL field not found")
            return False

        # Publish
        if not DRY_RUN:
            logger.info("Publishing post...")
            time.sleep(2)

            try:
                # Extended list of xpaths to find publish button
                xpaths = [
                    "//button[normalize-space(.)='Pos']",
                    "//button[contains(., 'Pos')]",
                    "//button[@aria-label='Pos']",
                    "//button[contains(., 'Publish')]",
                    "//button[normalize-space(.)='Publish']",
                    "//div[@role='button'][normalize-space(.)='Pos']",
                    "//div[@role='button'][contains(., 'Pos')]",
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pos')]",
                    "//*[@role='button'][normalize-space(.)='Pos']",
                ]

                publish_btn = None
                for xp in xpaths:
                    try:
                        logger.info(f"  Trying xpath: {xp[:50]}...")
                        btn = WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located((By.XPATH, xp))
                        )
                        if btn and btn.is_displayed():
                            logger.info(f"Found publish button with: {xp}")
                            publish_btn = btn
                            break
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
                            btn_text = (btn.text or btn.get_attribute('innerText') or btn.get_attribute('aria-label') or btn.get_attribute('value') or "").strip()
                            btn_class = btn.get_attribute('class') or ""
                            btn_id = btn.get_attribute('id') or ""
                            is_displayed = btn.is_displayed()

                            # Log every button
                            logger.info(f"  [{idx}] '{btn_text[:40]}' | id: {btn_id[:20]} | class: {btn_class[:30]} | visible: {is_displayed}")

                            # Look for publish/post/submit keywords
                            if any(keyword in btn_text.lower() for keyword in ['pos', 'publish', 'post', 'submit', 'kirim', 'simpan']):
                                if is_displayed:
                                    logger.info(f"✓ Found match at index {idx}: '{btn_text}'")
                                    publish_btn = btn
                                    break
                        except Exception as e:
                            logger.debug(f"Button {idx} error: {e}")
                            continue

                if not publish_btn:
                    logger.error("❌ Publish button NOT FOUND after full scan")
                    try:
                        screenshot_path = str(SCREENSHOT_DIR / f"{profile_name}_publish_button_not_found.png")
                        driver.save_screenshot(screenshot_path)
                        logger.error(f"Debug screenshot: {screenshot_path}")
                    except:
                        pass
                    return False

                logger.info("Clicking publish button...")
                driver.execute_script("arguments[0].scrollIntoView(true);", publish_btn)
                time.sleep(1)

                try:
                    publish_btn.click()
                except Exception as e:
                    logger.warning(f"Direct click failed: {e}, trying JS click")
                    driver.execute_script("arguments[0].click();", publish_btn)

                logger.info("Publish button clicked")
                time.sleep(3)

                logger.info(f"Post published successfully for: {profile_name}")
                return True

            except Exception as e:
                logger.error(f"Publish failed: {e}")
                try:
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
        time.sleep(2)

        # Step 2: Find search field and search store code
        logger.info(f"Searching for: {store_code}")
        search_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
        )
        search_field.clear()
        search_field.send_keys(store_code)
        logger.info("Entered store code in search")
        time.sleep(1)

        # Step 3: Press Enter
        search_field.send_keys(Keys.ENTER)
        logger.info("Pressed Enter")
        time.sleep(3)

        # Debug: Check URL and take screenshot
        current_url = driver.current_url
        logger.info(f"Current URL: {current_url}")
        try:
            driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_after_search.png"))
        except:
            pass

        # Step 4: Find ALL add post buttons (all profiles for this store)
        logger.info("Looking for all add post buttons (profiles)...")

        # Find all candidate buttons
        all_btns = driver.find_elements(By.XPATH, "//button | //div[@role='button']")
        logger.info(f"Total buttons found: {len(all_btns)}")

        add_post_buttons = []
        for btn in all_btns:
            try:
                btn_text = btn.get_attribute('innerText') or btn.get_attribute('aria-label') or btn.get_attribute('title') or ''
                btn_text_lower = btn_text.lower()

                if 'postingan' in btn_text_lower or ('post' in btn_text_lower and 'buat' in btn_text_lower) or 'add post' in btn_text_lower:
                    if btn.is_displayed():
                        add_post_buttons.append(btn)
                        logger.info(f"Found profile button [{len(add_post_buttons)}]: {btn_text[:50]}")
            except:
                continue

        if not add_post_buttons:
            logger.error("No add post buttons found")
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
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", add_post_btn)
                logger.info(f"Clicked add post button for profile {profile_idx}")
                time.sleep(2)

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
                    time.sleep(2)

                    # Re-search store code
                    search_field = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
                    )
                    search_field.clear()
                    search_field.send_keys(store_code)
                    time.sleep(1)
                    search_field.send_keys(Keys.ENTER)
                    time.sleep(3)

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
        time.sleep(2)

        # Step 2: Search store code
        logger.info(f"Searching for: {store_code}")
        search_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
        )
        search_field.clear()
        search_field.send_keys(store_code)
        logger.info("Entered store code")
        time.sleep(1)

        search_field.send_keys(Keys.ENTER)
        logger.info("Pressed Enter")
        time.sleep(3)

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
                    time.sleep(4)
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
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", postingan_btn)
                    logger.info("Clicked Postingan")
                    time.sleep(3)
                else:
                    logger.info("No Postingan button found - posts might be visible already")
                    time.sleep(2)

                # Take screenshot of postingan list/area
                try:
                    driver.save_screenshot(str(SCREENSHOT_DIR / f"{store_code}_profile_{profile_idx + 1}_postingan_list.png"))
                    logger.info(f"Screenshot: postingan list area")
                except:
                    pass

                # Step 6: Find top-most post item dengan "Book your stay" caption
                logger.info("Finding top-most post item in list...")
                time.sleep(1)

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
                        time.sleep(1)
                        driver.switch_to.window(windows_before[0])
                    continue

                logger.info(f"Found {result.get('count')} posts. Top post: {result.get('topText')}, Tag: {result.get('topTag')}")
                time.sleep(0.5)

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
                        time.sleep(3)

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
                time.sleep(2)

                # Re-search store code
                search_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@role='combobox']"))
                )
                search_field.clear()
                search_field.send_keys(store_code)
                time.sleep(1)
                search_field.send_keys(Keys.ENTER)
                logger.info("Re-searched store code")
                time.sleep(3)

            except Exception as e:
                logger.error(f"Profile {profile_idx + 1} error: {e}")
                profile_failed += 1
                try:
                    if new_windows:
                        driver.close()
                        time.sleep(1)
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
        init_status_csv()

        driver = create_driver()

        # Step 1: Login to Google (before accessing GMB)
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

        # Jalankan mode yang dipilih
        if mode == "add_post":
            for store in pending[:max_process]:
                try:
                    process_store(driver, store["code"], store["wa_link"])
                except Exception as e:
                    logger.error(f"Error: {e}")
        else:  # delete_post
            for store in pending[:max_process]:
                try:
                    delete_posts(driver, store["code"])
                except Exception as e:
                    logger.error(f"Error: {e}")

        # Summary
        final_status = load_status()
        success_stores = [code for code, status in final_status.items() if status == "SUCCESS"]
        failed_stores = [code for code, status in final_status.items() if status == "FAILED"]
        dryrun_stores = [code for code, status in final_status.items() if status == "DRY_RUN_OK"]
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

        logger.info("=== GMB Automation End ===")
        driver.quit()

    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
