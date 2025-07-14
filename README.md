# hatebu-web-clipper-for-obsidian

![screenshot](https://github.com/user-attachments/assets/4f428d5d-d9d8-4ab4-b87a-28f51d8061a5)

## Motivation

As of July 2025, there is no easy way to use the Obsidian Web Clipper on Android. A realistic method is to install Obsidian, Firefox, and the Obsidian Web Clipper extension on Android, but this is more cumbersome than on a PC (especially if Firefox is not your main browser).

Therefore, this command is executed on a PC to create Markdown for pages tagged with `obsidian`. Page rendering uses [microsoft/markitdown](https://github.com/microsoft/markitdown).

## Requirements

- Python >= 3.10
- [astral-sh/uv](https://github.com/astral-sh/uv)
- Hatena ID

## Usage

### 0. Obtain OAuth Consumer Key/Secret from the Hatena settings screen

- scope: read_public, read_private, write_public, write_private

### 1. Create .env from .env.tmpl

```bash
mv .env.tmpl .env
```

### 2. Fill in the necessary information in .env and save

### 3. Execute main.py

```bash
./main.py
```

The first time you run it, OAuth authentication is required, so please follow the instructions on the console to authenticate the application.

### Options

- `--save-dir`: Directory to save Markdown files. Overrides `SAVE_DIR` in the `.env` file.
- `--tag`: Tag to search for. Overrides `TARGET_TAG_NAME` in the `.env` file (default: `obsidian`).
- `--dryrun`: Dry-run mode. No files will be written or bookmarks deleted.
- `--delete-bookmark`: (true|false) Delete the bookmark after processing. Defaults to `true`.

## Limitations

- The quality of the clipped content is lower than that of the Obsidian Web Clipper (depends on the performance of markitdown).
