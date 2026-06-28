# LiveLib Metadata for Calibre

`LiveLib Metadata` is a Calibre metadata source plugin for Russian-language book libraries.

It improves Calibre metadata lookup for books that are better represented on Russian book services than on the default Calibre sources. The plugin searches LiveLib, LitRes, and FantLab, then returns Russian descriptions, tags, identifiers, publication details, and covers.

## Features

- Searches LiveLib beta pages and parses structured book metadata.
- Uses the public LitRes API as the first source when it has a strong match.
- Uses FantLab as an additional fallback for genre and speculative fiction titles.
- Downloads Russian descriptions and genre tags.
- Imports ISBN, publisher, publication year, rating, and LiveLib vote count when available.
- Adds edition details to comments: series, page count, binding, paper type, weight, size, and age rating.
- Prefers high-resolution LiveLib cover URLs (`/o/...jpeg`) and falls back to preview covers when needed.
- Rejects weak title/author matches to avoid replacing a book with a same-title result by another author.

## Search Order

1. `litres:` identifier, when already present.
2. `livelib:` identifier, when already present.
3. LitRes public API search.
4. LiveLib beta search: `https://beta.livelib.ru/search?q=...`.
5. Old LiveLib search as a fallback: `https://www.livelib.ru/find/...`.
6. FantLab public API search.

## Installation

1. Download `LiveLib Metadata.zip` from the latest GitHub release.
2. Open Calibre.
3. Go to `Preferences -> Plugins -> Load plugin from file`.
4. Select `LiveLib Metadata.zip`.
5. Restart Calibre.
6. Go to `Preferences -> Metadata download` and make sure `LiveLib Metadata` is enabled.

## Updating

Download the new `LiveLib Metadata.zip` from the latest release and install it through `Load plugin from file` again. Calibre will replace the previous version after restart.

This repository also includes a GitHub Actions release workflow. When a new tag like `v0.3.2` is pushed, GitHub builds a fresh plugin zip and attaches it to the release automatically.

## Building Locally

```bash
./scripts/build-plugin.sh
```

The build output is written to:

```text
dist/LiveLib Metadata.zip
```

## Notes

Calibre has no native page-count field, so physical edition details are appended to comments under `Детали издания LiveLib`.

LiveLib and LitRes are third-party services. Their HTML/API behavior can change, so releases may update parsers and matching rules as needed.

## License

GPL-3.0-only.
