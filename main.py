#!/usr/bin/env -S uv run --script
#
# /// script
# name = "hatebu-web-clipper-for-obsidian"
# version = "0.2.0"
# description = "Fetch Hatena Bookmarks by tag using Hatena Bookmark API."
# dependencies = [
#     "requests-oauthlib>=1.3.1",
#     "python-dotenv>=1.0.1",
#     "markitdown[all]>=0.1.2",
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
import logging
from typing import Optional, Dict, Any, List
from markitdown import MarkItDown
from pathvalidate import sanitize_filename
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class HatebuClipper:
    """
    A class to fetch, convert, and manage Hatena Bookmarks.
    """
    # --- Constants ---
    TOKEN_FILE = "tokens.json"
    API_URLS = {
        "request_token": "https://www.hatena.com/oauth/initiate",
        "authorization": "https://www.hatena.ne.jp/oauth/authorize",
        "access_token": "https://www.hatena.com/oauth/token",
        "search_api": "https://b.hatena.ne.jp/my/search/json",
        "delete_bookmark": "https://bookmark.hatenaapis.com/rest/1/my/bookmark",
    }

    def __init__(self, consumer_key: str, consumer_secret: str, save_dir: Optional[str] = None, dryrun: bool = False, delete_bookmark: bool = True):
        """
        Initializes the HatebuClipper.

        Args:
            consumer_key: Hatena API consumer key.
            consumer_secret: Hatena API consumer secret.
            save_dir: Directory to save Markdown files.
            dryrun: If True, no files will be written or bookmarks deleted.
            delete_bookmark: If False, bookmarks will not be deleted.
        """
        if not all([consumer_key, consumer_secret]):
            raise ValueError("Consumer key and secret must be provided.")

        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.save_dir = save_dir
        self.dryrun = dryrun
        self.delete_bookmark = delete_bookmark
        self.hatena_session: Optional[OAuth1Session] = None
        self.md_converter = MarkItDown()

    def _get_access_tokens(self) -> Optional[Dict[str, str]]:
        """Execute OAuth flow to get and save new access tokens."""
        params = {"scope": "read_public,read_private,write_public,write_private"}
        oauth = OAuth1Session(client_key=self.consumer_key, client_secret=self.consumer_secret, callback_uri="oob")

        logging.info("Getting request token...")
        try:
            fetch_response = oauth.fetch_request_token(self.API_URLS["request_token"], params=params)
        except Exception as e:
            logging.error(f"Failed to get request token: {e}")
            return None

        resource_owner_key = fetch_response.get("oauth_token")
        resource_owner_secret = fetch_response.get("oauth_token_secret")

        authorization_url = oauth.authorization_url(self.API_URLS["authorization"])
        print("-" * 50)
        print("Please access the following URL to authenticate:")
        print(authorization_url)
        print("-" * 50)
        verifier = input("Please enter the PIN code (Verifier): ")

        oauth = OAuth1Session(
            client_key=self.consumer_key, client_secret=self.consumer_secret,
            resource_owner_key=resource_owner_key, resource_owner_secret=resource_owner_secret,
            verifier=verifier,
        )

        logging.info("Getting access token...")
        try:
            oauth_tokens = oauth.fetch_access_token(self.API_URLS["access_token"])
            with open(self.TOKEN_FILE, "w") as f:
                json.dump(oauth_tokens, f)
            logging.info(f"Access tokens saved to {self.TOKEN_FILE}.")
            return oauth_tokens
        except Exception as e:
            logging.error(f"Failed to get access token: {e}")
            return None

    def _load_or_create_tokens(self) -> Optional[Dict[str, str]]:
        """Load saved tokens or start the creation flow."""
        if os.path.exists(self.TOKEN_FILE):
            logging.info(f"Loading access tokens from {self.TOKEN_FILE}.")
            with open(self.TOKEN_FILE, "r") as f:
                return json.load(f)

        logging.warning(f"Could not find {self.TOKEN_FILE}. Starting new authentication flow.")
        return self._get_access_tokens()

    def authenticate(self) -> bool:
        """Authenticate and create an OAuth session."""
        tokens = self._load_or_create_tokens()
        if not tokens:
            logging.error("Authentication failed. Could not get tokens.")
            return False

        access_token = tokens.get("oauth_token")
        access_token_secret = tokens.get("oauth_token_secret")

        if not all([access_token, access_token_secret]):
            logging.error("Access token or secret is missing in the token file.")
            return False

        self.hatena_session = OAuth1Session(
            client_key=self.consumer_key, client_secret=self.consumer_secret,
            resource_owner_key=access_token, resource_owner_secret=access_token_secret
        )
        logging.info("Authentication successful.")
        return True

    def _fetch_bookmark_list(self, tag: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch a list of bookmarks for a given tag."""
        if not self.hatena_session:
            logging.error("Session not authenticated.")
            return None

        params = {"q": tag}
        logging.info(f"Searching for bookmarks with tag '{tag}'...")
        try:
            response = self.hatena_session.get(self.API_URLS["search_api"], params=params)
            response.raise_for_status()
            data = response.json()
            bookmarks = data.get("bookmarks", [])
            if not bookmarks:
                logging.info("No bookmarks found for the specified tag.")
                if "error" in data:
                    logging.error(f"API Error: {data['error']}")
            return bookmarks
        except (requests.RequestException, json.JSONDecodeError) as e:
            logging.error(f"Failed to fetch or parse bookmarks: {e}")
            return None

    def _download_and_convert(self, url: str) -> str:
        """Download data from a URL and convert it to Markdown."""

        logging.info(f"Downloading data from {url}...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data_content = response.text

        logging.info("Converting data to Markdown...")
        data_stream = io.BytesIO(data_content.encode('utf-8'))
        try:
            result = self.md_converter.convert(data_stream, input_filename="page.data")
        except Exception as e:
            logging.error(f"Failed to convert data to Markdown: {e}")
            return ""

        return result.text_content

    def _save_markdown(self, title: str, content: str):
        """Save Markdown content to a file."""
        if not self.save_dir:
            logging.warning("Save directory not specified. Skipping save.")
            return

        safe_title = sanitize_filename(title)
        yyyymmdd = datetime.date.today().strftime('%Y%m%d')
        file_name = f"{yyyymmdd}_{safe_title}.md"
        file_path = os.path.join(self.save_dir, file_name)

        logging.info(f"Saving Markdown to {file_path}...")
        if self.dryrun:
            logging.info(f"DRY RUN: Skipping file write to {file_path}.")
            return

        os.makedirs(self.save_dir, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _delete_bookmark(self, url: str):
        """Delete a bookmark from Hatena."""
        if not self.hatena_session:
            logging.error("Session not authenticated.")
            return

        logging.info(f"Deleting bookmark for {url}...")
        if self.dryrun:
            logging.info(f"DRY RUN: Skipping bookmark deletion for {url}.")
            return

        response = self.hatena_session.delete(self.API_URLS["delete_bookmark"], params={"url": url})
        response.raise_for_status()
        logging.info("Bookmark deleted successfully.")

    def run(self, tag: str):
        """
        Main process to fetch, convert, save, and delete bookmarks.
        """
        if not self.authenticate():
            return

        bookmarks = self._fetch_bookmark_list(tag)
        if not bookmarks:
            return

        logging.info(f"--- Found {len(bookmarks)} bookmarks for tag '{tag}' ---")
        for bookmark in bookmarks:
            entry = bookmark.get("entry", {})
            url = entry.get("url")
            title = entry.get("title", "No Title")

            if not url:
                logging.warning("Bookmark with no URL found. Skipping.")
                continue

            logging.info(f"\n--- Processing: {title} ({url}) ---")
            markdown_content = self._download_and_convert(url)

            if markdown_content:
                if not self.save_dir:
                    print("\n--- Markdown Output ---")
                    print(markdown_content)
                    print("--- End of Markdown ---\n")
                else:
                    self._save_markdown(title, markdown_content)

            if not self.delete_bookmark:
                return

            self._delete_bookmark(url)

        logging.info("--- All bookmarks processed. ---")


def main():
    """
    Parses command-line arguments and runs the clipper.
    """
    load_dotenv()

    parser = argparse.ArgumentParser(description="Fetch Hatena Bookmarks and convert to Markdown.")
    parser.add_argument("--save-dir", type=str, default=os.getenv("SAVE_DIR"),
                        help="Directory to save Markdown files. Overrides SAVE_DIR env var.")
    parser.add_argument("--tag", type=str, default=os.getenv("TARGET_TAG_NAME", "obsidian"),
                        help="Tag to search for. Overrides TARGET_TAG_NAME env var.")
    parser.add_argument("--dryrun", action="store_true", help="Dry-run mode. No files written or bookmarks deleted.")
    parser.add_argument("--delete-bookmark", type=lambda x: (str(x).lower() == 'true'), default=True,
                        help="Delete bookmark after processing. (default: True)")
    args = parser.parse_args()

    consumer_key = os.getenv("HATENA_CONSUMER_KEY")
    consumer_secret = os.getenv("HATENA_CONSUMER_SECRET")

    try:
        clipper = HatebuClipper(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            save_dir=args.save_dir,
            dryrun=args.dryrun,
            delete_bookmark=args.delete_bookmark
        )
    except ValueError as e:
        logging.error(f"Initialization failed: {e}")
        print("Please set HATENA_CONSUMER_KEY and HATENA_CONSUMER_SECRET in .env file or as environment variables.")

    clipper.run(tag=args.tag)

if __name__ == "__main__":
    main()
