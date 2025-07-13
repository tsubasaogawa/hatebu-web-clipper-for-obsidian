import unittest
import os
import json
import shutil
from unittest.mock import patch, MagicMock, mock_open
from main import HatebuClipper, main as main_func

class TestHatebuClipper(unittest.TestCase):

    def setUp(self):
        """Set up test environment."""
        self.consumer_key = "test_consumer_key"
        self.consumer_secret = "test_consumer_secret"
        self.save_dir = "test_save_dir"
        # Ensure the test save directory is clean before each test
        if os.path.exists(self.save_dir):
            shutil.rmtree(self.save_dir)

    def tearDown(self):
        """Clean up test environment."""
        if os.path.exists(self.save_dir):
            shutil.rmtree(self.save_dir)

    def test_init_raises_error_on_missing_keys(self):
        """Test that ValueError is raised if consumer keys are missing."""
        with self.assertRaises(ValueError):
            HatebuClipper(consumer_key=None, consumer_secret=self.consumer_secret)
        with self.assertRaises(ValueError):
            HatebuClipper(consumer_key=self.consumer_key, consumer_secret=None)

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data='{"oauth_token": "test_token", "oauth_token_secret": "test_secret"}')
    def test_load_or_create_tokens_existing(self, mock_file, mock_exists):
        """Test loading existing tokens."""
        clipper = HatebuClipper(self.consumer_key, self.consumer_secret)
        tokens = clipper._load_or_create_tokens()
        self.assertEqual(tokens["oauth_token"], "test_token")
        mock_file.assert_called_with(clipper.TOKEN_FILE, "r")

    @patch("os.path.exists", return_value=False)
    @patch("main.HatebuClipper._get_access_tokens")
    def test_load_or_create_tokens_not_existing(self, mock_get_access_tokens, mock_exists):
        """Test creating new tokens when file doesn't exist."""
        mock_get_access_tokens.return_value = {"oauth_token": "new_token"}
        clipper = HatebuClipper(self.consumer_key, self.consumer_secret)
        tokens = clipper._load_or_create_tokens()
        self.assertEqual(tokens["oauth_token"], "new_token")
        mock_get_access_tokens.assert_called_once()

    @patch("main.HatebuClipper.authenticate", return_value=True)
    @patch("main.HatebuClipper._fetch_bookmark_list")
    @patch("main.HatebuClipper._download_and_convert")
    @patch("main.HatebuClipper._save_markdown")
    @patch("main.HatebuClipper._delete_bookmark")
    def test_run_success_flow(self, mock_delete, mock_save, mock_convert, mock_fetch_list, mock_auth):
        """Test the successful run flow."""
        mock_fetch_list.return_value = [{"entry": {"url": "http://example.com", "title": "Example Title"}}]
        mock_convert.return_value = "# Example Content"

        clipper = HatebuClipper(self.consumer_key, self.consumer_secret, save_dir=self.save_dir)
        clipper.run(tag="test_tag")

        mock_auth.assert_called_once()
        mock_fetch_list.assert_called_once_with("test_tag")
        mock_convert.assert_called_once_with("http://example.com")
        mock_save.assert_called_once_with("Example Title", "# Example Content")
        mock_delete.assert_called_once_with("http://example.com")

    @patch("main.HatebuClipper.authenticate", return_value=True)
    @patch("main.HatebuClipper._fetch_bookmark_list")
    @patch("main.HatebuClipper._download_and_convert")
    @patch("builtins.open", new_callable=mock_open)
    def test_run_dryrun_flow(self, mock_open_file, mock_convert, mock_fetch_list, mock_auth):
        """Test that dryrun prevents file writing and bookmark deletion."""
        clipper = HatebuClipper(self.consumer_key, self.consumer_secret, save_dir=self.save_dir, dryrun=True)
        clipper.hatena_session = MagicMock()  # Mock the session to check delete call

        mock_fetch_list.return_value = [{"entry": {"url": "http://example.com", "title": "Example Title"}}]
        mock_convert.return_value = "# Example Content"

        clipper.run(tag="test_tag")

        mock_auth.assert_called_once()
        mock_fetch_list.assert_called_once_with("test_tag")
        mock_convert.assert_called_once_with("http://example.com")
        
        # Assert that file was not written and delete was not called
        mock_open_file.assert_not_called()
        clipper.hatena_session.delete.assert_not_called()

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.HatebuClipper')
    @patch.dict(os.environ, {
        "HATENA_CONSUMER_KEY": "env_key",
        "HATENA_CONSUMER_SECRET": "env_secret",
        "SAVE_DIR": "env/dir",
        "TARGET_TAG_NAME": "env_tag"
    })
    def test_main_function_with_args(self, mock_clipper_class, mock_args):
        """Test the main function correctly parses args and calls the clipper."""
        mock_args.return_value = MagicMock(save_dir="arg/dir", tag="arg_tag", dryrun=True)
        mock_clipper_instance = MagicMock()
        mock_clipper_class.return_value = mock_clipper_instance

        main_func()

        mock_clipper_class.assert_called_once_with(
            consumer_key="env_key",
            consumer_secret="env_secret",
            save_dir="arg/dir",  # Arg should override env var
            dryrun=True
        )
        mock_clipper_instance.run.assert_called_once_with(tag="arg_tag")

    @patch('argparse.ArgumentParser.parse_args')
    @patch.dict(os.environ, {"HATENA_CONSUMER_KEY": "", "HATENA_CONSUMER_SECRET": ""}, clear=True)
    def test_main_function_no_env_vars(self, mock_args):
        """Test main function exits gracefully if env vars are not set."""
        mock_args.return_value = MagicMock(save_dir=None, tag="test", dryrun=False)
        
        with patch('main.logging.error') as mock_log_error, \
             patch('builtins.print') as mock_print:
            
            main_func()
            
            mock_log_error.assert_called_once()
            self.assertIn("Initialization failed", mock_log_error.call_args[0][0])
            mock_print.assert_called_once()
            self.assertIn("Please set HATENA_CONSUMER_KEY", mock_print.call_args[0][0])

if __name__ == "__main__":
    unittest.main()
