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

# Load .env file
load_dotenv()

CONSUMER_KEY = os.getenv("HATENA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("HATENA_CONSUMER_SECRET")
TOKEN_FILE = "tokens.json"

REQUEST_TOKEN_URL = "https://www.hatena.com/oauth/initiate"
AUTHORIZATION_URL = "https://www.hatena.ne.jp/oauth/authorize"
ACCESS_TOKEN_URL = "https://www.hatena.com/oauth/token"
SEARCH_API_URL = "https://b.hatena.ne.jp/my/search/json"
DELETE_BOOKMARK_URL = "https://bookmark.hatenaapis.com/rest/1/my/bookmark"

TAG = os.getenv("TARGET_TAG_NAME", "obsidian")


def get_access_tokens():
    """
    Execute the OAuth authentication flow to obtain and save access tokens.
    """
    # Step 1: Get Request Token
    # Specify necessary permissions with scope (read_public, read_private, write_public, write_private)
    params = {"scope": "read_public,read_private,write_public,write_private"}
    hatena_oauth = OAuth1Session(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        callback_uri="oob" # Out-of-Band
    )

    print("Getting request token...")
    try:
        fetch_response = hatena_oauth.fetch_request_token(REQUEST_TOKEN_URL, params=params)
    except Exception as e:
        print(f"❌ Error: Failed to get request token. {e}")
        return None

    resource_owner_key = fetch_response.get("oauth_token")
    resource_owner_secret = fetch_response.get("oauth_token_secret")

    # Step 2: User Authentication and Get Verifier
    authorization_url = hatena_oauth.authorization_url(AUTHORIZATION_URL)
    print("-" * 50)
    print("Please access the following URL to authenticate the application:")
    print(authorization_url)
    print("-" * 50)

    verifier = input("Please enter the PIN code (Verifier) displayed after authentication: ")

    # Step 3: Get Access Token
    hatena_oauth = OAuth1Session(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
    )

    print("Getting access token...")
    try:
        oauth_tokens = hatena_oauth.fetch_access_token(ACCESS_TOKEN_URL)
    except Exception as e:
        print(f"❌ Error: Failed to get access token. {e}")
        return None

    # Save the obtained tokens
    with open(TOKEN_FILE, "w") as f:
        json.dump(oauth_tokens, f)
    print(f"🔑 Access tokens saved to {TOKEN_FILE}.")

    return oauth_tokens


def load_or_create_tokens():
    """
    Load saved tokens. If not present, call the new creation flow.
    """
    if os.path.exists(TOKEN_FILE):
        print(f"Loading access tokens from {TOKEN_FILE}.")
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    else:
        print(f"Could not find {TOKEN_FILE}. Starting new authentication flow.")
        return get_access_tokens()


def fetch_bookmarks_by_tag(access_token, access_token_secret, save_dir, dryrun=False):
    """
    Fetch bookmarks by tag using the specified Hatena Bookmark API.
    """
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        print(f"Saving Markdown files to '{save_dir}'.")

    md = MarkItDown() # Create an instance of MarkItDown
    # Create an OAuth1 session
    try:
        hatena = OAuth1Session(
            client_key=CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret,
        )
    except Exception as e:
        print(f"An error occurred while creating the OAuth session: {e}")
        return

    # Send a request to the API
    params = {"q": f"{TAG}"}
    print(f"🔍 Searching for bookmarks with tag '{TAG}' (Endpoint: {SEARCH_API_URL})...")

    try:
        response = hatena.get(SEARCH_API_URL, params=params)
        response.raise_for_status()
    except Exception as e:
        print(f"An error occurred during the API request: {e}")
        if 'response' in locals() and response is not None:
            print(f"Status code: {response.status_code}")
            print(f"Response: {response.text}")
        return

    # --- Parse results (JSON format) ---
    try:
        data = response.json()
        # Check if 'bookmarks' key exists in the response
        bookmarks = data.get("bookmarks", [])

        if not bookmarks:
            print("No bookmarks found for the specified tag.")
            # Check if the response contains an error message
            if "error" in data:
                print(f"Error message from API: {data['error']}")
            return

        print(f"\n✅ --- Bookmark list for tag '{TAG}' ({len(bookmarks)} items) ---")
        for bookmark in bookmarks:
            # Specify keys according to the JSON response structure
            entry = bookmark.get("entry", {})
            url = entry.get("url")
            title = entry.get("title", "No Title")
            safe_title = sanitize_filename(title)

            if not url:
                print("URL not found. Skipping.")
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

                    # Delete bookmark
                    if not dryrun:
                        print(f"🗑️ Deleting bookmark for {url}...")
                        try:
                            delete_response = hatena.delete(DELETE_BOOKMARK_URL, params={"url": url})
                            delete_response.raise_for_status()
                            print("✅ Bookmark deleted successfully.")
                        except Exception as e:
                            print(f"❌ Error deleting bookmark for {url}: {e}")
                            if 'delete_response' in locals() and delete_response is not None:
                                print(f"Status code: {delete_response.status_code}")
                                print(f"Response: {delete_response.text}")
                    else:
                        print(f"DRY RUN: Skipping bookmark deletion for {url}.")

                else:
                    # If no save destination is specified, output to standard output
                    print("\n--- Markdown Output ---")
                    print(markdown_content)
                    print("--- End of Markdown ---\n")

            except requests.RequestException as e:
                print(f"❌ Error fetching URL {url}: {e}")
            except Exception as e:
                print(f"❌ An unexpected error occurred during conversion: {e}")


    except json.JSONDecodeError:
        print("❌ An error occurred while parsing JSON. The response may not be in JSON format.")
        print(f"Response content:\n{response.text}")
        return

def main():
    """
    Main process
    """
    parser = argparse.ArgumentParser(description="Fetch Hatena Bookmarks and convert to Markdown.")
    parser.add_argument("--save-dir", type=str, help="Directory to save Markdown files. SAVE_DIR environment variable will be used if specified.")
    parser.add_argument("--dryrun", action="store_true", help="Dry-run.")
    args = parser.parse_args()

    save_dir = os.getenv("SAVE_DIR", args.save_dir)

    # Reload environment variables from .env file
    # This ensures that CONSUMER_KEY and CONSUMER_SECRET are set correctly
    global CONSUMER_KEY, CONSUMER_SECRET
    CONSUMER_KEY = os.getenv("HATENA_CONSUMER_KEY")
    CONSUMER_SECRET = os.getenv("HATENA_CONSUMER_SECRET")

    # Check if authentication information is set
    if not all([CONSUMER_KEY, CONSUMER_SECRET]):
        print("🚫 Error: Required environment variables are not set.")
        print("Please set HATENA_CONSUMER_KEY and HATENA_CONSUMER_SECRET in the .env file or as environment variables.")
        return

    # Get or load tokens
    tokens = load_or_create_tokens()
    if tokens:
        access_token = tokens.get("oauth_token")
        access_token_secret = tokens.get("oauth_token_secret")

        if access_token and access_token_secret:
            fetch_bookmarks_by_tag(access_token, access_token_secret, save_dir, args.dryrun)
        else:
            print("❌ Error: Could not correctly load access tokens from the token file.")

if __name__ == "__main__":
    main()
