import unittest
import os
import json
from unittest.mock import patch, MagicMock, mock_open
import main

class TestMain(unittest.TestCase):

    def setUp(self):
        """テストの前に環境変数を設定"""
        self.mock_env = {
            "HATENA_CONSUMER_KEY": "test_consumer_key",
            "HATENA_CONSUMER_SECRET": "test_consumer_secret",
        }
        self.patcher = patch.dict(os.environ, self.mock_env)
        self.patcher.start()
        main.CONSUMER_KEY = self.mock_env["HATENA_CONSUMER_KEY"]
        main.CONSUMER_SECRET = self.mock_env["HATENA_CONSUMER_SECRET"]

    def tearDown(self):
        """テストの後にパッチを停止"""
        self.patcher.stop()

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='{"oauth_token": "test_token", "oauth_token_secret": "test_secret"}')
    def test_load_or_create_tokens_existing(self, mock_file, mock_exists):
        """トークンファイルが存在する場合、正しく読み込まれることをテスト"""
        mock_exists.return_value = True
        tokens = main.load_or_create_tokens()
        self.assertEqual(tokens["oauth_token"], "test_token")
        mock_file.assert_called_with(main.TOKEN_FILE, "r")

    @patch("os.path.exists")
    @patch("main.get_access_tokens")
    def test_load_or_create_tokens_not_existing(self, mock_get_access_tokens, mock_exists):
        """トークンファイルが存在しない場合、新規作成フローが呼ばれることをテスト"""
        mock_exists.return_value = False
        mock_get_access_tokens.return_value = {"oauth_token": "new_token"}
        tokens = main.load_or_create_tokens()
        self.assertEqual(tokens["oauth_token"], "new_token")
        mock_get_access_tokens.assert_called_once()

    @patch("main.requests.get")
    @patch("main.OAuth1Session")
    @patch("builtins.open", new_callable=mock_open)
    def test_fetch_bookmarks_by_tag_success(self, mock_file, mock_oauth_session, mock_requests_get):
        """ブックマークの取得とMarkdown保存が成功するケースをテスト"""
        # OAuth1Sessionのモック設定
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

        # requests.getのモック設定 (HTML取得)
        mock_html_response = MagicMock()
        mock_html_response.status_code = 200
        mock_html_response.text = "<html><body><h1>Hello</h1></body></html>"
        mock_requests_get.return_value = mock_html_response

        # テスト対象の関数を呼び出し
        main.fetch_bookmarks_by_tag("test_token", "test_secret", "test_save_dir")

        # アサーション
        mock_oauth_session.assert_called_with(
            client_key="test_consumer_key",
            client_secret="test_consumer_secret",
            resource_owner_key="test_token",
            resource_owner_secret="test_secret",
        )
        mock_session_instance.get.assert_called_once()
        mock_requests_get.assert_called_with("http://example.com", timeout=10)
        
        # ファイル書き込みが呼ばれたことを確認
        mock_file().write.assert_called_once()


    @patch("main.OAuth1Session")
    def test_fetch_bookmarks_by_tag_no_bookmarks(self, mock_oauth_session):
        """ブックマークが見つからないケースをテスト"""
        mock_session_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bookmarks": []}
        mock_session_instance.get.return_value = mock_response
        mock_oauth_session.return_value = mock_session_instance

        with patch('builtins.print') as mock_print:
            main.fetch_bookmarks_by_tag("test_token", "test_secret", "test_save_dir")
            # "見つかりませんでした" が出力されることを確認
            self.assertTrue(any("ブックマークは見つかりませんでした" in call[0][0] for call in mock_print.call_args_list))

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.load_or_create_tokens')
    @patch('main.fetch_bookmarks_by_tag')
    def test_main_success(self, mock_fetch, mock_load_tokens, mock_args):
        """main関数が正常に実行されることをテスト"""
        mock_args.return_value = MagicMock(save_dir="some/dir")
        mock_load_tokens.return_value = {
            "oauth_token": "test_token",
            "oauth_token_secret": "test_secret"
        }
        
        main.main()

        mock_load_tokens.assert_called_once()
        mock_fetch.assert_called_once_with("test_token", "test_secret", "some/dir")

    @patch('argparse.ArgumentParser.parse_args')
    @patch.dict(os.environ, {"HATENA_CONSUMER_KEY": "", "HATENA_CONSUMER_SECRET": ""})
    def test_main_no_env_vars(self, mock_args):
        """環境変数が設定されていない場合にエラー終了することをテスト"""
        main.CONSUMER_KEY = ""
        main.CONSUMER_SECRET = ""
        with patch('builtins.print') as mock_print:
            main.main()
            self.assertTrue(any("環境変数が設定されていません" in call[0][0] for call in mock_print.call_args_list))


if __name__ == "__main__":
    unittest.main()
