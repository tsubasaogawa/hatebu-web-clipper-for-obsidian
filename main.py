#!/usr/bin/env -S uv run --script
# 
# /// script
# name = "hatebu-web-clipper-for-obsidian"
# version = "0.1.0"
# description = "Fetch Hatena Bookmarks by tag using Hatena Bookmark API."
# dependencies = [
#     "requests-oauthlib>=1.3.1",
#     "python-dotenv>=1.0.1",
#     "markitdown>=0.1.2",
#     "requests>=2.32.3",
#     "pathvalidate>=3.2.0",
# ]
# requires-python = ">=3.10"
# ///

import os
import json
import requests
import io
import datetime
import argparse
from markitdown import MarkItDown
from pathvalidate import sanitize_filename
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

# .envファイルを読み込む
load_dotenv()

# --- 1. 定数設定 ---
CONSUMER_KEY = os.getenv("HATENA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("HATENA_CONSUMER_SECRET")
TOKEN_FILE = "tokens.json"

# Hatena OAuth エンドポイント
REQUEST_TOKEN_URL = "https://www.hatena.com/oauth/initiate"
AUTHORIZATION_URL = "https://www.hatena.ne.jp/oauth/authorize"
ACCESS_TOKEN_URL = "https://www.hatena.com/oauth/token"

# --- 2. APIリクエスト情報 (ご指定のエンドポイントに更新) ---
TAG = os.getenv("TARGET_TAG_NAME", "obsidian")
SEARCH_API_URL = "https://b.hatena.ne.jp/my/search/json"
DELETE_BOOKMARK_URL = "https://bookmark.hatenaapis.com/rest/1/my/bookmark"


def get_access_tokens():
    """
    OAuth認証フローを実行し、アクセストークンを取得して保存する。
    """
    # Step 1: リクエストトークンの取得
    # 必要な権限を scope で指定する (read_public, read_private, write_public, write_private)
    params = {"scope": "read_public,read_private,write_public,write_private"}
    hatena_oauth = OAuth1Session(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        callback_uri="oob" # Out-of-Band
    )

    print("リクエストトークンを取得しています...")
    try:
        fetch_response = hatena_oauth.fetch_request_token(REQUEST_TOKEN_URL, params=params)
    except Exception as e:
        print(f"❌ エラー: リクエストトークンの取得に失敗しました。{e}")
        return None

    resource_owner_key = fetch_response.get("oauth_token")
    resource_owner_secret = fetch_response.get("oauth_token_secret")

    # Step 2: ユーザー認証とVerifierの取得
    authorization_url = hatena_oauth.authorization_url(AUTHORIZATION_URL)
    print("-" * 50)
    print("以下のURLにアクセスしてアプリケーションを認証してください：")
    print(authorization_url)
    print("-" * 50)

    verifier = input("認証後に表示されるPINコード（Verifier）を入力してください: ")

    # Step 3: アクセストークンの取得
    hatena_oauth = OAuth1Session(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
    )

    print("アクセストークンを取得しています...")
    try:
        oauth_tokens = hatena_oauth.fetch_access_token(ACCESS_TOKEN_URL)
    except Exception as e:
        print(f"❌ エラー: アクセストークンの取得に失敗しました。{e}")
        return None

    # 取得したトークンを保存
    with open(TOKEN_FILE, "w") as f:
        json.dump(oauth_tokens, f)
    print(f"🔑 アクセストークンを {TOKEN_FILE} に保存しました。")

    return oauth_tokens


def load_or_create_tokens():
    """
    保存されたトークンを読み込む。なければ新規作成フローを呼び出す。
    """
    if os.path.exists(TOKEN_FILE):
        print(f"{TOKEN_FILE} からアクセストークンを読み込みます。")
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    else:
        print(f"{TOKEN_FILE} が見つかりません。新規に認証フローを開始します。")
        return get_access_tokens()


def fetch_bookmarks_by_tag(access_token, access_token_secret, save_dir, dryrun=False):
    """
    はてなブックマークの指定されたAPIを使い、タグでブックマークを取得する。
    """
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        print(f"Markdownファイルを '{save_dir}' に保存します。")

    md = MarkItDown() # MarkItDownのインスタンスを作成
    # OAuth1セッションを作成
    try:
        hatena = OAuth1Session(
            client_key=CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret,
        )
    except Exception as e:
        print(f"OAuthセッションの作成中にエラーが発生しました: {e}")
        return

    # APIにリクエストを送信
    params = {"q": f"{TAG}"}
    print(f"🔍 '{TAG}' タグでブックマークを検索しています (エンドポイント: {SEARCH_API_URL})...")

    try:
        response = hatena.get(SEARCH_API_URL, params=params)
        response.raise_for_status()
    except Exception as e:
        print(f"APIリクエスト中にエラーが発生しました: {e}")
        if 'response' in locals() and response is not None:
            print(f"ステータスコード: {response.status_code}")
            print(f"レスポンス: {response.text}")
        return

    # --- 結果のパース (JSON形式) ---
    try:
        data = response.json()
        # レスポンスに 'bookmarks' キーが存在するかチェック
        bookmarks = data.get("bookmarks", [])

        if not bookmarks:
            print("指定されたタグのブックマークは見つかりませんでした。")
            # レスポンスにエラーメッセージが含まれているか確認
            if "error" in data:
                print(f"APIからのエラーメッセージ: {data['error']}")
            return

        print(f"\n✅ --- 「{TAG}」タグのブックマーク一覧 ({len(bookmarks)}件) ---")
        for bookmark in bookmarks:
            # JSONレスポンスの構造に合わせてキーを指定
            entry = bookmark.get("entry", {})
            url = entry.get("url")
            title = entry.get("title", "No Title")
            safe_title = sanitize_filename(title)

            if not url:
                print("URLが見つかりませんでした。スキップします。")
                continue

            try:
                print(f"⬇️  Downloading HTML from {url}...")
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                html_content = response.text

                print("🔄 Converting HTML to Markdown...")
                html_stream = io.BytesIO(html_content.encode('utf-8'))
                result = md.convert(html_stream, input_filename="page.html")
                markdown_content = result.text_content

                if save_dir:
                    yyyymmdd = datetime.date.today().strftime('%Y%m%d')
                    file_name = f"{yyyymmdd}_{safe_title}.md"
                    file_path = os.path.join(save_dir, file_name)

                    print(f"💾 Saving Markdown to {file_path}...")
                    if not dryrun:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(markdown_content)

                    print(f"✅ Saved successfully.")

                    # ブックマークを削除
                    if not dryrun:
                        print(f"🗑️ Deleting bookmark for {url}...")
                        try:
                            delete_response = hatena.delete(DELETE_BOOKMARK_URL, params={"url": url})
                            delete_response.raise_for_status()
                            print("✅ Bookmark deleted successfully.")
                        except Exception as e:
                            print(f"❌ Error deleting bookmark for {url}: {e}")
                            if 'delete_response' in locals() and delete_response is not None:
                                print(f"ステータスコード: {delete_response.status_code}")
                                print(f"レスポンス: {delete_response.text}")
                    else:
                        print(f"DRY RUN: Skipping bookmark deletion for {url}.")

                else:
                    # 保存先が指定されていない場合は標準出力する
                    print("\n--- Markdown Output ---")
                    print(markdown_content)
                    print("--- End of Markdown ---\n")

            except requests.RequestException as e:
                print(f"❌ Error fetching URL {url}: {e}")
            except Exception as e:
                print(f"❌ An unexpected error occurred during conversion: {e}")


    except json.JSONDecodeError:
        print("❌ JSONのパース中にエラーが発生しました。レスポンスがJSON形式ではない可能性があります。")
        print(f"レスポンス内容:\n{response.text}")
        return

def main():
    """
    メイン処理
    """
    parser = argparse.ArgumentParser(description="Fetch Hatena Bookmarks and convert to Markdown.")
    parser.add_argument("--save-dir", type=str, help="Directory to save Markdown files. SAVE_DIR environment variable will be used if specified.")
    parser.add_argument("--dryrun", action="store_true", help="Dry-run.")
    args = parser.parse_args()

    save_dir = os.getenv("SAVE_DIR", args.save_dir)

    # .envファイルから環境変数を再読み込み
    # これにより、CONSUMER_KEYとCONSUMER_SECRETが正しく設定される
    global CONSUMER_KEY, CONSUMER_SECRET
    CONSUMER_KEY = os.getenv("HATENA_CONSUMER_KEY")
    CONSUMER_SECRET = os.getenv("HATENA_CONSUMER_SECRET")

    # 認証情報が設定されているかチェック
    if not all([CONSUMER_KEY, CONSUMER_SECRET]):
        print("🚫 エラー: 必要な環境変数が設定されていません。")
        print("HATENA_CONSUMER_KEY, HATENA_CONSUMER_SECRET を .env ファイルに設定するか、環境変数として設定してください。")
        return

    # トークンを取得または読み込み
    tokens = load_or_create_tokens()
    if tokens:
        access_token = tokens.get("oauth_token")
        access_token_secret = tokens.get("oauth_token_secret")

        if access_token and access_token_secret:
            fetch_bookmarks_by_tag(access_token, access_token_secret, save_dir, args.dryrun)
        else:
            print("❌ エラー: トークンファイルからアクセストークンを正しく読み込めませんでした。")

if __name__ == "__main__":
    main()
