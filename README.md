# LiveLib Metadata for Calibre

**LiveLib Metadata** is a [Calibre](https://calibre-ebook.com/) metadata source plugin for
Russian-language books. It fills the gap left by Calibre's default (mostly English) sources by
pulling titles, authors, descriptions, tags, ratings, publication details, and covers from the
biggest Russian book services — **LitRes**, **LiveLib**, and **FantLab**.

If you keep a Russian-language library and Calibre's built-in sources return English metadata,
poor matches, or no cover at all, this plugin is for you.

---

## Features

- **Three Russian sources in one plugin.** Queries LitRes (public API), LiveLib (beta pages), and
  FantLab, then merges and ranks the results by how well title and author match your book.
- **Multiple covers from every matched source.** When a book is found on more than one service,
  Calibre's cover picker shows covers from *all* of them (LitRes **and** LiveLib **and** FantLab),
  not just the top hit — so you can choose the one you like.
- **High-resolution covers.** Prefers the original LiveLib `/o/...jpeg` image and falls back to a
  preview automatically if the original is unavailable.
- **Rich Russian metadata.** Imports Russian descriptions, genre tags, rating and vote count, ISBN,
  publisher, and publication year.
- **Edition details in comments.** Series, page count, binding type, paper type, weight, size, and
  age rating are appended to the book's comments under **«Детали издания LiveLib»**, since Calibre
  has no native fields for most of these.
- **Accurate matching.** Rejects weak title/author matches so a book is not overwritten by a
  same-title work from a different author.
- **Identifiers.** Stores `litres`, `livelib`, and `fantlab` identifiers so repeat lookups and cover
  downloads are fast and exact.

---

## Search order

The plugin tries sources in order of reliability and stops escalating once it already has a strong
title + author match:

1. `litres:` identifier — used directly when the book already has one.
2. `livelib:` identifier — used directly when the book already has one.
3. **LitRes** public API search.
4. **LiveLib** fast beta search (`beta.livelib.ru/search`).
5. **LiveLib** legacy search (`www.livelib.ru/find`) — only when steps 3–4 found nothing strong.
6. **FantLab** public API search.

Skipping the slow legacy LiveLib search on a strong match keeps a typical lookup fast.

---

## Installation

1. Download `LiveLib.Metadata.zip` from the [latest release](https://github.com/GanbarovEmin/calibre-livelib-metadata-plugin/releases/latest).
2. Open Calibre.
3. Go to **Preferences → Plugins → Load plugin from file**.
4. Select the downloaded `LiveLib.Metadata.zip`.
5. Restart Calibre.
6. Go to **Preferences → Metadata download** and make sure **LiveLib Metadata** is enabled (and,
   optionally, drag it above other sources to prioritise it).

## Updating

Download the newest `LiveLib.Metadata.zip` from the releases page and install it again through
**Load plugin from file**. Calibre replaces the previous version after a restart.

---

## Usage

1. Select a book (or several) in Calibre.
2. Click **Edit metadata → Download metadata and covers** (or right-click → *Edit metadata*).
3. Pick the best match and cover from the results.

**Tips**

- Better input gives better matches. A clean Russian title plus the author name in the book's fields
  produces the most accurate results.
- If you already know the book on LitRes or LiveLib, add its `litres:` or `livelib:` identifier in
  Calibre — the plugin will then fetch that exact edition.
- Use **Download only covers** if you just want artwork; the plugin returns covers from all matched
  sources so you can compare.

---

## How it works

Calibre calls the plugin in two phases:

- **Identify** — searches the sources, builds candidate matches, and caches each source's cover URL.
  Cover *images* are intentionally **not** downloaded during this phase, which keeps identification
  fast.
- **Download cover** — collects the cached cover URLs from every matched source, expands each into
  its resolution variants, de-duplicates, and hands them all to Calibre's cover picker.

Physical edition details that Calibre cannot store natively are written into the book's comments
under **«Детали издания LiveLib»**.

---

## Building locally

```bash
./scripts/build-plugin.sh
```

The build writes the installable archive to:

```text
dist/LiveLib.Metadata.zip
```

## Releasing

Releases are automated. Pushing a tag like `v0.3.3` triggers the GitHub Actions workflow
(`.github/workflows/release.yml`), which builds a fresh plugin zip and publishes a GitHub release
with `RELEASE_NOTES.md` as the body.

---

## Troubleshooting

- **No results / no cover.** LiveLib and LitRes occasionally change their HTML and API responses.
  Update to the latest release, which usually ships updated parsers.
- **Wrong book returned.** Make sure the title and author in Calibre are correct; the plugin
  deliberately rejects weak matches, so a slightly wrong title can leave it with nothing to return.
- **Network / access issues.** The plugin talks to third-party Russian services; regional blocking or
  rate limiting on their side can cause empty results.

## Notes

Calibre has no native page-count or binding fields, so physical edition details are appended to
comments rather than stored as columns.

LiveLib, LitRes, and FantLab are third-party services. Their HTML/API behaviour can change at any
time, so releases may update parsers and matching rules as needed.

## Contributing

Issues and pull requests are welcome. When reporting a matching or cover problem, please include the
book title and author, and the plugin log from Calibre's job window — it makes the failure much
easier to reproduce.

## License

[GPL-3.0-only](LICENSE).
