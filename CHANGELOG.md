# Changelog

## v0.3.1 - 2026-06-28

- Prefer high-resolution LiveLib cover URLs using the `/o/...jpeg` form.
- Fall back to preview cover URLs when the original image is unavailable.
- Preserve direct LiveLib identifiers when LiveLib schema points to a canonical/alternate edition.
- Add release-ready project documentation.

## v0.3.0 - 2026-06-28

- Add `beta.livelib.ru` search and book-page support.
- Parse LiveLib `application/ld+json` Book schema.
- Import ISBN, publisher, publication year, rating, vote count, and Russian tags.
- Append edition details to comments: series, pages, binding, paper type, weight, size, and age rating.
- Prefer LiveLib beta pages over the older ddos-guard-prone LiveLib surface.

## v0.2.0 - 2026-06-28

- Add LitRes public API search and detail lookup.
- Add FantLab fallback.
- Improve Russian matching and reject same-author/wrong-title LitRes results.
- Fix cover download behavior.

## v0.1.0 - 2026-06-28

- Initial local LiveLib metadata source.
