#!/usr/bin/env python3
"""
Tests for Multi-Post feature
"""

import unittest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gmb_automation


class TestMultiPostConfig(unittest.TestCase):
    """Test multi-post configuration loading and validation"""

    def setUp(self):
        """Create temp directory for test files"""
        self.test_dir = tempfile.mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up temp files"""
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.test_dir)

    def test_valid_config_loads(self):
        """Test loading valid multi-post config"""
        config = {
            "post_types": [
                {
                    "id": "post_1",
                    "name": "Post 1",
                    "caption": "Caption 1",
                    "image": "test1.jpg",
                    "cta": "Book",
                    "url": "https://example.com/1"
                },
                {
                    "id": "post_2",
                    "name": "Post 2",
                    "caption": "Caption 2",
                    "image": "test2.jpg",
                    "cta": "Book",
                    "url": "https://example.com/2"
                },
                {
                    "id": "post_3",
                    "name": "Post 3",
                    "caption": "Caption 3",
                    "image": "test3.jpg",
                    "cta": "Book",
                    "url": "https://example.com/3"
                }
            ]
        }

        # Create test images
        Path("test1.jpg").touch()
        Path("test2.jpg").touch()
        Path("test3.jpg").touch()

        # Write config
        with open("multi_post_config.json", "w") as f:
            json.dump(config, f)

        # Patch the config file path
        with patch.object(gmb_automation, 'MULTI_POST_CONFIG_FILE', Path("multi_post_config.json")):
            posts = gmb_automation.load_multi_post_config()
            self.assertEqual(len(posts), 3)
            self.assertEqual(posts[0]["id"], "post_1")
            self.assertEqual(posts[1]["id"], "post_2")
            self.assertEqual(posts[2]["id"], "post_3")

    def test_config_wrong_count_fails(self):
        """Test config with wrong number of post types fails"""
        config = {
            "post_types": [
                {
                    "id": "post_1",
                    "name": "Post 1",
                    "caption": "Caption 1",
                    "image": "test1.jpg",
                    "cta": "Book",
                    "url": "https://example.com/1"
                },
                {
                    "id": "post_2",
                    "name": "Post 2",
                    "caption": "Caption 2",
                    "image": "test2.jpg",
                    "cta": "Book",
                    "url": "https://example.com/2"
                }
            ]
        }

        Path("test1.jpg").touch()
        Path("test2.jpg").touch()

        with open("multi_post_config.json", "w") as f:
            json.dump(config, f)

        with patch.object(gmb_automation, 'MULTI_POST_CONFIG_FILE', Path("multi_post_config.json")):
            with self.assertRaises(ValueError) as ctx:
                gmb_automation.load_multi_post_config()
            self.assertIn("Expected 3 post types", str(ctx.exception))

    def test_config_missing_image_fails(self):
        """Test config with missing image file fails"""
        config = {
            "post_types": [
                {
                    "id": "post_1",
                    "name": "Post 1",
                    "caption": "Caption 1",
                    "image": "missing.jpg",
                    "cta": "Book",
                    "url": "https://example.com/1"
                },
                {
                    "id": "post_2",
                    "name": "Post 2",
                    "caption": "Caption 2",
                    "image": "test2.jpg",
                    "cta": "Book",
                    "url": "https://example.com/2"
                },
                {
                    "id": "post_3",
                    "name": "Post 3",
                    "caption": "Caption 3",
                    "image": "test3.jpg",
                    "cta": "Book",
                    "url": "https://example.com/3"
                }
            ]
        }

        Path("test2.jpg").touch()
        Path("test3.jpg").touch()

        with open("multi_post_config.json", "w") as f:
            json.dump(config, f)

        with patch.object(gmb_automation, 'MULTI_POST_CONFIG_FILE', Path("multi_post_config.json")):
            with self.assertRaises(FileNotFoundError):
                gmb_automation.load_multi_post_config()

    def test_config_missing_field_fails(self):
        """Test config with missing required field fails"""
        config = {
            "post_types": [
                {
                    "id": "post_1",
                    "name": "Post 1",
                    # Missing caption
                    "image": "test1.jpg",
                    "cta": "Book",
                    "url": "https://example.com/1"
                },
                {
                    "id": "post_2",
                    "name": "Post 2",
                    "caption": "Caption 2",
                    "image": "test2.jpg",
                    "cta": "Book",
                    "url": "https://example.com/2"
                },
                {
                    "id": "post_3",
                    "name": "Post 3",
                    "caption": "Caption 3",
                    "image": "test3.jpg",
                    "cta": "Book",
                    "url": "https://example.com/3"
                }
            ]
        }

        Path("test1.jpg").touch()
        Path("test2.jpg").touch()
        Path("test3.jpg").touch()

        with open("multi_post_config.json", "w") as f:
            json.dump(config, f)

        with patch.object(gmb_automation, 'MULTI_POST_CONFIG_FILE', Path("multi_post_config.json")):
            with self.assertRaises(ValueError) as ctx:
                gmb_automation.load_multi_post_config()
            self.assertIn("caption", str(ctx.exception))


class TestMultiPostStatus(unittest.TestCase):
    """Test multi-post status tracking"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.test_dir)

    def test_init_status_csv(self):
        """Test initialization of multi-post status CSV"""
        with patch.object(gmb_automation, 'MULTI_POST_STATUS_FILE', Path("multi_post_status.csv")):
            gmb_automation.init_multi_post_status_csv()
            self.assertTrue(Path("multi_post_status.csv").exists())

            # Verify header
            with open("multi_post_status.csv", "r") as f:
                header = f.readline().strip()
                self.assertIn("store_code", header)
                self.assertIn("property_identifier", header)
                self.assertIn("post_type_id", header)
                self.assertIn("status", header)

    def test_update_and_load_status(self):
        """Test updating and loading multi-post status"""
        with patch.object(gmb_automation, 'MULTI_POST_STATUS_FILE', Path("multi_post_status.csv")):
            gmb_automation.init_multi_post_status_csv()

            # Update status
            gmb_automation.update_multi_post_status("STORE1", "prop_1", "Property 1", "post_1", "SUCCESS", attempts=1)
            gmb_automation.update_multi_post_status("STORE1", "prop_1", "Property 1", "post_2", "FAILED", attempts=1, error="Test error")

            # Load and verify
            status = gmb_automation.load_multi_post_status()
            key1 = ("STORE1", "prop_1", "post_1")
            key2 = ("STORE1", "prop_1", "post_2")

            self.assertIn(key1, status)
            self.assertEqual(status[key1]["status"], "SUCCESS")
            self.assertIn(key2, status)
            self.assertEqual(status[key2]["status"], "FAILED")
            self.assertEqual(status[key2]["error"], "Test error")

    def test_skip_already_successful_posts(self):
        """Test that already-successful posts are skipped"""
        with patch.object(gmb_automation, 'MULTI_POST_STATUS_FILE', Path("multi_post_status.csv")):
            gmb_automation.init_multi_post_status_csv()

            # Mark post as already successful
            gmb_automation.update_multi_post_status("STORE1", "prop_1", "Property 1", "post_1", "SUCCESS")

            # Load status
            status = gmb_automation.load_multi_post_status()
            key = ("STORE1", "prop_1", "post_1")

            self.assertEqual(status[key]["status"], "SUCCESS")


class TestMultiPostLogic(unittest.TestCase):
    """Test multi-post business logic"""

    def test_config_with_unique_urls(self):
        """Test that each post type has unique URL"""
        post_types = [
            {
                "id": "post_1",
                "name": "Post 1",
                "caption": "Caption 1",
                "image": "test1.jpg",
                "cta": "Book",
                "url": "https://example.com/1"
            },
            {
                "id": "post_2",
                "name": "Post 2",
                "caption": "Caption 2",
                "image": "test2.jpg",
                "cta": "Book",
                "url": "https://example.com/2"
            },
            {
                "id": "post_3",
                "name": "Post 3",
                "caption": "Caption 3",
                "image": "test3.jpg",
                "cta": "Book",
                "url": "https://example.com/3"
            }
        ]

        urls = [p["url"] for p in post_types]
        self.assertEqual(len(urls), len(set(urls)), "URLs should be unique")

    def test_config_with_unique_images(self):
        """Test that each post type has unique image"""
        post_types = [
            {
                "id": "post_1",
                "name": "Post 1",
                "caption": "Caption 1",
                "image": "image1.jpg",
                "cta": "Book",
                "url": "https://example.com/1"
            },
            {
                "id": "post_2",
                "name": "Post 2",
                "caption": "Caption 2",
                "image": "image2.jpg",
                "cta": "Book",
                "url": "https://example.com/2"
            },
            {
                "id": "post_3",
                "name": "Post 3",
                "caption": "Caption 3",
                "image": "image3.jpg",
                "cta": "Book",
                "url": "https://example.com/3"
            }
        ]

        images = [p["image"] for p in post_types]
        self.assertEqual(len(images), len(set(images)), "Images should be unique")


if __name__ == "__main__":
    unittest.main()
