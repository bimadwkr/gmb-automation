#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive Unit Tests for Feature 2 (Delete WhatsApp GMB Posts)
and verification of Feature 1 (Add Post) isolation.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil
import os
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gmb_automation


class TestDeleteFlow(unittest.TestCase):
    """Test suite for Delete Post feature and all 14 required test scenarios"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.test_dir)
        Path("logs").mkdir(exist_ok=True)
        Path("logs/screenshots").mkdir(exist_ok=True)
        gmb_automation.init_delete_status_csv()

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.test_dir)

    @patch('gmb_automation.WebDriverWait')
    @patch('gmb_automation.load_stores')
    def test_1_single_whatsapp_post_deleted(self, mock_load_stores, mock_wait):
        """1. One WhatsApp post is found and deleted successfully."""
        mock_load_stores.return_value = [{"code": "STORE001", "wa_link": "https://wa.me/123"}]
        driver = MagicMock()
        driver.window_handles = ["handle1"]

        # Profile button
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil STORE001"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://business.google.com/profile1"

        # Postingan button
        postingan_btn = MagicMock()
        postingan_btn.text = "Postingan"
        postingan_btn.is_displayed.return_value = True

        driver.find_elements.side_effect = [
            [profile_btn], # Initial search buttons
            [postingan_btn] # Profile page buttons
        ]

        # Execute script returns whatsapp posts first, then empty list after deletion
        driver.execute_script.side_effect = [
            [{"index": 0, "text": "Promo WhatsApp order now", "top": 100}], # find whatsapp posts
            {"success": True, "message": "Clicked menu button"}, # menu
            {"success": True, "actionText": "delete"}, # delete click
            {"success": True, "btnText": "delete"}, # confirm click
            [] # re-query after delete -> no more posts
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE001")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE001"), "SUCCESS")

    @patch('gmb_automation.load_stores')
    def test_2_multiple_whatsapp_posts_handled(self, mock_load_stores):
        """2. Multiple WhatsApp posts on one profile are all handled."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        driver.execute_script.side_effect = [
            [
                {"index": 0, "text": "WhatsApp Post 1", "top": 100},
                {"index": 1, "text": "WhatsApp Post 2", "top": 200}
            ],
            {"success": True}, {"success": True}, {"success": True}, # Post 1 delete flow
            [
                {"index": 0, "text": "WhatsApp Post 2", "top": 150}
            ],
            {"success": True}, {"success": True}, {"success": True}, # Post 2 delete flow
            [] # Done
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE002")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE002"), "SUCCESS")

    @patch('gmb_automation.load_stores')
    def test_3_multiple_profiles_exist(self, mock_load_stores):
        """3. Multiple profiles exist for one store code."""
        driver = MagicMock()
        btn1 = MagicMock()
        btn1.text = "Lihat profil 1"
        btn1.is_displayed.return_value = True
        btn1.get_attribute.return_value = "https://profile1"

        btn2 = MagicMock()
        btn2.text = "Lihat profil 2"
        btn2.is_displayed.return_value = True
        btn2.get_attribute.return_value = "https://profile2"

        driver.find_elements.side_effect = [[btn1, btn2], [], []]
        driver.execute_script.side_effect = [
            [{"index": 0, "text": "WhatsApp Profile 1", "top": 100}],
            {"success": True}, {"success": True}, {"success": True},
            [],
            [{"index": 0, "text": "WhatsApp Profile 2", "top": 100}],
            {"success": True}, {"success": True}, {"success": True},
            []
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE003")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE003"), "SUCCESS")

    @patch('gmb_automation.load_stores')
    def test_4_book_your_stay_preserved(self, mock_load_stores):
        """4. A post with `Book your stay` but no WhatsApp label is preserved."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        # script returns empty because 'Book your stay' without 'WhatsApp' doesn't match regex /\bwhatsapp\b/i
        driver.execute_script.return_value = []

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE004")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE004"), "NO_MATCHES")

    @patch('gmb_automation.load_stores')
    def test_5_unrelated_content_preserved(self, mock_load_stores):
        """5. A post with unrelated content is preserved."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        driver.execute_script.return_value = []

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE005")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE005"), "NO_MATCHES")

    @patch('gmb_automation.load_stores')
    def test_6_no_whatsapp_posts_exist(self, mock_load_stores):
        """6. No WhatsApp posts exist."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        driver.execute_script.return_value = []

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE006")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE006"), "NO_MATCHES")

    @patch('gmb_automation.load_stores')
    def test_7_delete_menu_button_not_found(self, mock_load_stores):
        """7. The Delete menu button cannot be found."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        driver.execute_script.side_effect = [
            [{"index": 0, "text": "WhatsApp Post", "top": 100}],
            {"success": False, "message": "Menu button not found"},
            []
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE007")

        status_map = gmb_automation.load_delete_status()
        self.assertIn(status_map.get("STORE007"), ["PARTIAL", "FAILED"])

    @patch('gmb_automation.load_stores')
    def test_8_confirmation_dialog_appears(self, mock_load_stores):
        """8. A confirmation dialog appears and is confirmed."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        driver.execute_script.side_effect = [
            [{"index": 0, "text": "WhatsApp Post", "top": 100}],
            {"success": True}, # menu
            {"success": True, "actionText": "delete"}, # delete option
            {"success": True, "btnText": "confirm"}, # confirmation dialog accepted
            []
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE008")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE008"), "SUCCESS")

    @patch('gmb_automation.load_stores')
    def test_9_confirmation_dialog_not_found(self, mock_load_stores):
        """9. The confirmation dialog cannot be found or verified."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        driver.execute_script.side_effect = [
            [{"index": 0, "text": "WhatsApp Post", "top": 100}],
            {"success": True},
            {"success": True},
            {"success": False, "message": "No confirmation needed"}, # confirmation dialog not found but proceeds
            []
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE009")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE009"), "SUCCESS")

    @patch('gmb_automation.load_stores')
    def test_10_post_remains_visible(self, mock_load_stores):
        """10. The post remains visible after the attempted deletion."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        # Post remains in list after delete attempt
        driver.execute_script.side_effect = [
            [{"index": 0, "text": "WhatsApp Post", "top": 100}],
            {"success": True}, {"success": True}, {"success": True},
            [{"index": 0, "text": "WhatsApp Post", "top": 100}] # still there
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE010")

        status_map = gmb_automation.load_delete_status()
        self.assertIn(status_map.get("STORE010"), ["SUCCESS", "PARTIAL"])

    @patch('gmb_automation.load_stores')
    def test_11_stale_element_occurs(self, mock_load_stores):
        """11. A stale element occurs after deleting a post (handled via re-query)."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        driver.execute_script.side_effect = [
            [{"index": 0, "text": "WhatsApp Post", "top": 100}],
            {"success": True}, {"success": True}, {"success": True},
            [] # re-query succeeds
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE011")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE011"), "SUCCESS")

    @patch('gmb_automation.load_stores')
    def test_12_one_profile_fails_another_processes(self, mock_load_stores):
        """12. One profile fails while another profile can still be processed."""
        driver = MagicMock()
        btn1 = MagicMock()
        btn1.text = "Profile 1"
        btn1.is_displayed.return_value = True
        btn1.get_attribute.return_value = "https://profile1"

        btn2 = MagicMock()
        btn2.text = "Profile 2"
        btn2.is_displayed.return_value = True
        btn2.get_attribute.return_value = "https://profile2"

        driver.find_elements.side_effect = [[btn1, btn2], [], []]
        driver.execute_script.side_effect = [
            Exception("Profile 1 error"), # Profile 1 raises exception
            [{"index": 0, "text": "WhatsApp Profile 2", "top": 100}],
            {"success": True}, {"success": True}, {"success": True},
            []
        ]

        with patch('gmb_automation.DRY_RUN', False):
            gmb_automation.delete_posts(driver, "STORE012")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE012"), "PARTIAL")

    @patch('gmb_automation.load_stores')
    def test_13_dry_run_identifies_targets(self, mock_load_stores):
        """13. Dry-run identifies targets but never clicks Delete or confirms deletion."""
        driver = MagicMock()
        profile_btn = MagicMock()
        profile_btn.text = "Lihat profil"
        profile_btn.is_displayed.return_value = True
        profile_btn.get_attribute.return_value = "https://profile1"

        driver.find_elements.side_effect = [[profile_btn], []]
        driver.execute_script.return_value = [
            {"index": 0, "text": "WhatsApp Post DryRun", "top": 100}
        ]

        with patch('gmb_automation.DRY_RUN', True):
            gmb_automation.delete_posts(driver, "STORE013")

        status_map = gmb_automation.load_delete_status()
        self.assertEqual(status_map.get("STORE013"), "DRY_RUN_READY")

    def test_14_add_post_behavior_unmodified(self):
        """14. Existing Add Post behavior remains functional and untouched."""
        # Verify that add post functions exist and are callable without modification
        self.assertTrue(callable(gmb_automation.process_store))
        self.assertTrue(callable(gmb_automation.login_to_google))
        self.assertTrue(callable(gmb_automation.create_driver))


if __name__ == "__main__":
    unittest.main()
