import unittest
import os
import json
import shutil
from unittest.mock import patch, MagicMock, mock_open
import main

class TestMain(unittest.TestCase):

    def setUp(self):
        """Set environment variables before tests."""
        self.mock_env = {
            "HATENA_CONSUMER_KEY": "test_consumer_key",
            "HATENA_CONSUMER_SECRET": "test_consumer_secret",
        }
        self.patcher = patch.dict(os.environ, self.mock_env)
        self.patcher.start()
        main.CONSUMER_KEY = self.mock_env["HATENA_CONSUMER_KEY"]
        main.CONSUMER_SECRET = self.mock_env["HATENA_CONSUMER_SECRET"]

    def tearDown(self):
        """Stop patches after tests."""
        self.patcher.stop()
        if os.path.exists("test_save_dir"):
            shutil.rmtree("test_save_dir")

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='{"oauth_token": "test_token", "oauth_token_secret": "test_secret"}')
    def test_load_or_create_tokens_existing(self, mock_file, mock_exists):
        """Test that tokens are loaded correctly if the token file exists."""
        mock_exists.return_value = True
        tokens = main.load_or_create_tokens()
        self.assertEqual(tokens["oauth_token"], "test_token")
        mock_file.assert_called_with(main.TOKEN_FILE, "r")

    @patch("os.path.exists")
    @patch("main.get_access_tokens")
    def test_load_or_create_tokens_not_existing(self, mock_get_access_tokens, mock_exists):
        """Test that the new token creation flow is called if the token file does not exist."""
        mock_exists.return_value = False
        mock_get_access_tokens.return_value = {"oauth_token": "new_token"}
        tokens = main.load_or_create_tokens()
        self.assertEqual(tokens["oauth_token"], "new_token")
        mock_get_access_tokens.assert_called_once()

    @patch("main.requests.get")
    @patch("main.OAuth1Session")
    @patch("builtins.open", new_callable=mock_open)
    def test_fetch_bookmarks_and_delete_success(self, mock_file, mock_oauth_session, mock_requests_get):
        """Test the case where fetching, saving, and deleting bookmarks succeeds."""
        # Mock settings for OAuth1Session
        mock_session_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bookmarks": [
                {
                    "entry": {
                        "url": "http://example.com",
                        "title": "Example Title"
                    }
                }
            ]
        }
        mock_session_instance.get.return_value = mock_response
        # Mock for delete method
        mock_delete_response = MagicMock()
        mock_delete_response.raise_for_status.return_value = None
        mock_session_instance.delete.return_value = mock_delete_response
        mock_oauth_session.return_value = mock_session_instance

        # Mock settings for requests.get (HTML fetching)
        mock_html_response = MagicMock()
        mock_html_response.status_code = 200
        mock_html_response.text = "<html><body><h1>Hello</h1></body></html>"
        mock_requests_get.return_value = mock_html_response

        # Call the function to be tested (dryrun=False is the default)
        main.fetch_bookmarks_by_tag("test_token", "test_secret", "test_save_dir")

        # Assertions
        mock_oauth_session.assert_called_with(
            client_key="test_consumer_key",
            client_secret="test_consumer_secret",
            resource_owner_key="test_token",
            resource_owner_secret="test_secret",
        )
        mock_session_instance.get.assert_called_once()
        mock_requests_get.assert_called_with("http://example.com", timeout=10)
        
        # Check file writing and delete API call
        mock_file().write.assert_called_once()
        self.assertEqual(main.DELETE_BOOKMARK_URL, "https://bookmark.hatenaapis.com/rest/1/my/bookmark")
        mock_session_instance.delete.assert_called_once_with(main.DELETE_BOOKMARK_URL, params={"url": "http://example.com"})


    @patch("main.requests.get")
    @patch("main.OAuth1Session")
    @patch("builtins.open", new_callable=mock_open)
    def test_fetch_bookmarks_with_dryrun_does_not_delete(self, mock_file, mock_oauth_session, mock_requests_get):
        """Test that bookmarks are not deleted when the --dryrun option is used."""
        # Mock settings for OAuth1Session
        mock_session_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bookmarks": [
                {
                    "entry": {
                        "url": "http://example.com",
                        "title": "Example Title"
                    }
                }
            ]
        }
        mock_session_instance.get.return_value = mock_response
        mock_oauth_session.return_value = mock_session_instance

        # Mock settings for requests.get (HTML fetching)
        mock_html_response = MagicMock()
        mock_html_response.status_code = 200
        mock_html_response.text = "<html><body><h1>Hello</h1></body></html>"
        mock_requests_get.return_value = mock_html_response

        # Call the function to be tested (dryrun=True)
        main.fetch_bookmarks_by_tag("test_token", "test_secret", "test_save_dir", dryrun=True)

        # Assertions
        mock_session_instance.get.assert_called_once()
        # Check that file writing is not performed during dryrun
        mock_file().write.assert_not_called()
        # Check that delete is not called
        mock_session_instance.delete.assert_not_called()


    @patch("main.OAuth1Session")
    def test_fetch_bookmarks_by_tag_no_bookmarks(self, mock_oauth_session):
        """Test the case where no bookmarks are found."""
        mock_session_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bookmarks": []}
        mock_session_instance.get.return_value = mock_response
        mock_oauth_session.return_value = mock_session_instance

        with patch('builtins.print') as mock_print:
            main.fetch_bookmarks_by_tag("test_token", "test_secret", "test_save_dir")
            # Check that "No bookmarks found" is printed
            self.assertTrue(any("No bookmarks found" in call[0][0] for call in mock_print.call_args_list))

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.load_or_create_tokens')
    @patch('main.fetch_bookmarks_by_tag')
    def test_main_success(self, mock_fetch, mock_load_tokens, mock_args):
        """Test that the main function runs successfully."""
        # Ensure that the SAVE_DIR environment variable is not set in this test
        with patch.dict(os.environ, self.mock_env, clear=True):
            mock_args.return_value = MagicMock(save_dir="some/dir", dryrun=False)
            mock_load_tokens.return_value = {
                "oauth_token": "test_token",
                "oauth_token_secret": "test_secret"
            }
            
            main.main()

            mock_load_tokens.assert_called_once()
            mock_fetch.assert_called_once_with("test_token", "test_secret", "some/dir", False)

    @patch('argparse.ArgumentParser.parse_args')
    @patch.dict(os.environ, {"HATENA_CONSUMER_KEY": "", "HATENA_CONSUMER_SECRET": ""})
    def test_main_no_env_vars(self, mock_args):
        """Test that the program exits with an error if environment variables are not set."""
        main.CONSUMER_KEY = ""
        main.CONSUMER_SECRET = ""
        with patch('builtins.print') as mock_print:
            main.main()
            self.assertTrue(any("environment variables are not set" in call[0][0] for call in mock_print.call_args_list))


if __name__ == "__main__":
    unittest.main()
