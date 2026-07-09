# LiveLib Metadata for Calibre v0.3.3

Patch release of `LiveLib Metadata`, a Calibre metadata source plugin for Russian-language book libraries.

## Highlights

- Fixes missing LitRes covers by offering covers from every matched source (LitRes, LiveLib, FantLab) together.
- Faster identification: cover bytes are no longer downloaded during identify, and the slow legacy livelib.ru search is skipped when a strong match is already found.
- Searches LitRes, LiveLib, and FantLab.
- Uses LiveLib beta pages as the primary Russian metadata fallback.
- Downloads Russian descriptions, genres, ratings, ISBN, publisher, publication year, and edition details.
- Adds physical edition details to comments when Calibre has no native field for them.
- Prefers high-resolution LiveLib covers using `/o/...jpeg` URLs.
- Falls back to preview covers when an original cover is unavailable.

## Install

Download `LiveLib.Metadata.zip` from the release assets and install it in Calibre:

`Preferences -> Plugins -> Load plugin from file`

Restart Calibre after installation.

## Update

For future releases, download the newest `LiveLib.Metadata.zip` and install it through the same Calibre plugin dialog. Calibre will replace the older plugin after restart.
