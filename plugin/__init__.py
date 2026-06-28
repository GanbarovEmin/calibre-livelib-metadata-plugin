from __future__ import absolute_import, division, print_function, unicode_literals

__license__ = 'GPL-3.0-only'
__copyright__ = '2026, Emin Ganbarov and contributors'

import json
import re
from datetime import datetime
from html import escape, unescape
from queue import Empty, Queue
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

from lxml import html

from calibre import as_unicode
from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source


BASE_URL = 'https://www.livelib.ru'
BETA_BASE_URL = 'https://beta.livelib.ru'
FANTLAB_BASE_URL = 'https://api.fantlab.ru'
LITRES_API_BASE = 'https://api.litres.ru/foundation/api'
LITRES_WEB_BASE = 'https://www.litres.ru'
USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/126.0.0.0 Safari/537.36'
)


def norm(value):
    value = (value or '').casefold().replace('ё', 'е')
    value = re.sub(r'[\W_]+', ' ', value, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', value).strip()


def score_match(query_title, query_authors, title, author):
    qt = norm(query_title)
    qa = norm(' '.join(query_authors or []))
    rt = norm(title)
    ra = norm(author)
    score = 0
    if qt and rt:
        if qt == rt:
            score += 80
        elif qt in rt or rt in qt:
            score += 45
        elif all(token in rt for token in qt.split()[:3]):
            score += 30
    if qa and ra:
        if qa == ra:
            score += 60
        elif qa in ra or ra in qa:
            score += 35
        else:
            q_tokens = set(qa.split())
            r_tokens = set(ra.split())
            score += 10 * len(q_tokens & r_tokens)
    return score


def title_match_enough(query_title, result_title):
    qt = norm(query_title)
    rt = norm(result_title)
    if not qt or not rt:
        return False
    if qt == rt or qt in rt or rt in qt:
        return True
    q_tokens = [token for token in qt.split() if len(token) > 1]
    r_tokens = set(rt.split())
    return len(set(q_tokens) & r_tokens) >= min(2, len(q_tokens))


def clean_html(raw):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw or '')


def safe_html_fromstring(raw):
    parser = html.HTMLParser(recover=True, huge_tree=True, encoding='utf-8')
    return html.fromstring(clean_html(raw), parser=parser)


def extract_balanced_json(text, start):
    start = text.find('{', start)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for pos in range(start, len(text)):
        char = text[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:pos + 1]
    return None


def decode_next_payload(raw):
    cleaned = clean_html(raw)
    chunks = []
    for match in re.finditer(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)</script>', cleaned, re.DOTALL):
        try:
            chunks.append(json.loads('"%s"' % match.group(1)))
        except Exception:
            continue
    if chunks:
        return '\n'.join(chunks)
    return unescape(cleaned).replace('\\"', '"').replace('\\/', '/')


def source_rating(value):
    try:
        rating = float(as_unicode(value).replace(',', '.'))
    except Exception:
        return None
    return rating / 2 if rating > 5 else rating


def extract_livelib_json(raw):
    try:
        root = safe_html_fromstring(raw)
        for script in root.xpath('//script[@type="application/ld+json"]/text()'):
            try:
                payload = json.loads(script)
            except Exception:
                continue
            entries = payload if isinstance(payload, list) else [payload]
            for entry in entries:
                graph = entry.get('@graph') if isinstance(entry, dict) else None
                for graph_entry in graph or []:
                    if graph_entry.get('@type') == 'Book':
                        return graph_entry
                if isinstance(entry, dict) and entry.get('@type') == 'Book':
                    return entry
    except Exception:
        pass

    match = re.search(r'"(\{\\?"@context\\?":\\?"https://schema\.org\\?".*?\})"', raw)
    if not match:
        return None
    data = match.group(1).replace('\\"', '"').replace('\\/', '/')
    try:
        payload = json.loads(data)
    except Exception:
        return None
    for entry in payload.get('@graph', []):
        if entry.get('@type') == 'Book':
            return entry
    return None


def livelib_id_from_url(url):
    return (url or '').split('/book/', 1)[-1].split('?', 1)[0].split('#', 1)[0]


def livelib_beta_url(url):
    livelib_id = livelib_id_from_url(url)
    return BETA_BASE_URL + '/book/' + livelib_id if livelib_id else url


def livelib_original_cover_url(url):
    if not url:
        return None
    match = re.match(r'(https?://s\d+\.livelib\.ru/boocover/\d+)/(?:\d+x\d+)/(.*?)/([^/?#]+)$', url)
    if not match:
        return None
    base, shard, filename = match.groups()
    filename = re.sub(r'\.(?:jpg|jpeg|png|webp)$', '.jpeg', filename, flags=re.IGNORECASE)
    return '%s/o/%s/%s' % (base, shard, filename)


def livelib_cover_candidates(url):
    urls = []
    original = livelib_original_cover_url(url)
    if original:
        urls.append(original)
    if url and url not in urls:
        urls.append(url)
    return urls


def compact_page_text(raw):
    try:
        root = safe_html_fromstring(raw)
        text = root.text_content()
    except Exception:
        text = raw
    text = text.replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def extract_between(text, label, next_labels):
    labels = '|'.join(re.escape(label) for label in next_labels)
    match = re.search(re.escape(label) + r'\s*(.*?)\s*(?:' + labels + r')', text)
    if match:
        return match.group(1).strip(' ,;')
    return None


def extract_livelib_page_details(raw):
    text = compact_page_text(raw)
    details = {}
    field_specs = [
        ('publisher', 'Издательство:', ['Серия:', 'ISBN:', 'Год издания:', 'Язык:', 'Подробная информация']),
        ('series', 'Серия:', ['ISBN:', 'Год издания:', 'Язык:', 'Тип обложки', 'Количество страниц', 'Подробная информация']),
        ('isbn', 'ISBN:', ['Год издания:', 'Язык:', 'Подробная информация']),
        ('year', 'Год издания:', ['Язык:', 'Тип обложки', 'Тип бумаги', 'Количество страниц', 'Возрастные ограничения:', 'Содержание', 'Подробная информация']),
        ('age', 'Возрастные ограничения:', ['Содержание', 'Награды', 'Подробная информация', 'Рейтинг LiveLib']),
        ('weight', 'Вес:', ['Размер:', 'Возрастные ограничения:', 'Подробная информация']),
        ('size', 'Размер:', ['Возрастные ограничения:', 'Подробная информация']),
        ('cover_type', 'Тип обложки -', ['Тип бумаги', 'Количество страниц', 'Возрастные ограничения:', 'Содержание', 'Награды', 'Подробная информация']),
        ('paper_type', 'Тип бумаги в книге -', ['Количество страниц', 'Возрастные ограничения:', 'Содержание', 'Награды', 'Подробная информация']),
    ]
    for key, label, next_labels in field_specs:
        value = extract_between(text, label, next_labels)
        if value:
            details[key] = value

    physical = re.search(r'((?:Мягкий|Твердый|Твёрдый|Кожаный|Интегральный|Электронная|Аудио)[^:]{0,80}?\d+\s*стр\.)', text)
    if physical:
        details['physical'] = physical.group(1).strip()
        pages = re.search(r'(\d+)\s*стр\.', details['physical'])
        if pages:
            details['pages'] = pages.group(1)

    pages = re.search(r'Количество страниц\s*-\s*(\d+)', text)
    if pages:
        details['pages'] = pages.group(1)

    if not details.get('physical'):
        physical_parts = []
        if details.get('cover_type'):
            physical_parts.append(details['cover_type'])
        if details.get('pages'):
            physical_parts.append('%s стр.' % details['pages'])
        if physical_parts:
            details['physical'] = ', '.join(physical_parts)

    language = extract_between(text, 'Язык:', [
        'Исполнитель:', 'Длительность:', 'Редактирование звука:', 'Корректор:',
        'Постер:', 'кодек / битрейт:', 'Вес:', 'Размер:',
        'Возрастные ограничения:', 'Содержание', 'Подробная информация'
    ])
    if language:
        language = re.sub(r'((?:Мягкий|Твердый|Твёрдый|Кожаный|Интегральный|Электронная|Аудио).*)$', '', language).strip(' ,;')
        if 'Русский' in language:
            language = 'Русский'
        if language:
            details['language'] = language

    if details.get('year'):
        year = re.search(r'\d{4}', details['year'])
        if year:
            details['year'] = year.group(0)
    if details.get('age'):
        age = re.search(r'\d+\+', details['age'])
        if age:
            details['age'] = age.group(0)
    return details


def append_edition_details(comments, details, rating_count=None):
    rows = []
    labels = [
        ('isbn', 'ISBN'),
        ('publisher', 'Издательство'),
        ('series', 'Серия'),
        ('year', 'Год издания'),
        ('language', 'Язык'),
        ('physical', 'Формат'),
        ('pages', 'Страниц'),
        ('cover_type', 'Тип обложки'),
        ('paper_type', 'Тип бумаги'),
        ('weight', 'Вес'),
        ('size', 'Размер'),
        ('age', 'Возрастные ограничения'),
    ]
    for key, label in labels:
        value = details.get(key)
        if value:
            rows.append('%s: %s' % (label, value))
    if rating_count:
        rows.append('Оценок LiveLib: %s' % rating_count)
    if not rows:
        return comments
    block = '<p><b>Детали издания LiveLib:</b><br/>%s</p>' % '<br/>'.join(escape(row) for row in rows)
    return ((comments or '') + block) if comments else block


class LiveLibMetadata(Source):
    name = 'LiveLib Metadata'
    description = 'Downloads Russian metadata and covers from LitRes, LiveLib, and FantLab'
    author = 'OpenAI Codex for Emin'
    version = (0, 3, 2)
    minimum_calibre_version = (6, 0, 0)

    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset([
        'title', 'authors', 'identifier:litres', 'identifier:livelib', 'identifier:fantlab',
        'identifier:isbn', 'comments', 'publisher', 'pubdate', 'tags', 'rating', 'languages'
    ])
    has_html_comments = True
    supports_gzip_transfer_encoding = True
    can_get_multiple_covers = True

    def fetch_url(self, url, timeout):
        headers = {
            'User-Agent': USER_AGENT,
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': BASE_URL + '/',
        }
        raw = urlopen(Request(url, headers=headers), timeout=timeout).read()
        return raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw

    def fetch_json(self, url, timeout):
        headers = {
            'User-Agent': USER_AGENT,
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.7',
            'Accept': 'application/json,text/plain,*/*',
            'Accept-Version': '2',
            'Referer': LITRES_WEB_BASE + '/',
        }
        raw = urlopen(Request(url, headers=headers), timeout=timeout).read()
        return json.loads(raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw)

    def absolutize_litres_cover(self, cover_url, art_id=None):
        if art_id:
            return 'https://cdn.litres.ru/pub/c/cover_415/%s' % art_id
        if not cover_url:
            return None
        if cover_url.startswith('//'):
            return 'https:' + cover_url
        if cover_url.startswith('/pub/'):
            return 'https://cdn.litres.ru' + cover_url
        if cover_url.startswith('/'):
            return LITRES_WEB_BASE + cover_url
        return cover_url

    def attach_cover_data(self, mi, cover_url, timeout):
        if not cover_url:
            return
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
            'Referer': BASE_URL + '/',
        }
        raw = None
        downloaded_url = cover_url
        for candidate_url in livelib_cover_candidates(cover_url):
            try:
                raw = urlopen(Request(candidate_url, headers=headers), timeout=timeout).read()
                downloaded_url = candidate_url
                break
            except Exception:
                continue
        if raw is None:
            raw = urlopen(Request(cover_url, headers=headers), timeout=timeout).read()
        fmt = 'jpeg'
        lowered = downloaded_url.lower()
        if lowered.endswith('.png'):
            fmt = 'png'
        elif lowered.endswith('.webp'):
            fmt = 'webp'
        mi.cover_data = (fmt, raw)
        mi.has_cover = True

    def get_book_url(self, identifiers):
        livelib_id = identifiers.get('livelib')
        if livelib_id:
            return ('livelib', livelib_id, BASE_URL + '/book/' + livelib_id)

    def id_from_url(self, url):
        match = re.search(r'livelib\.ru/book/([^/?#]+)', url or '')
        if match:
            return ('livelib', match.group(1))
        return None

    def identify(self, log, result_queue, abort, title=None, authors=None,
                 identifiers=None, timeout=30):
        identifiers = identifiers or {}
        direct_id = identifiers.get('livelib')
        candidates = []

        litres_id = identifiers.get('litres')
        if litres_id:
            candidates.append({
                'source': 'litres',
                'score': 1000,
                'id': litres_id,
                'title': title or '',
                'authors': authors or [],
            })
        elif direct_id:
            candidates.append({
                'source': 'livelib',
                'score': 1000,
                'url': BETA_BASE_URL + '/book/' + direct_id,
                'title': title or '',
                'author': (authors or [''])[0],
            })
        else:
            query = ' '.join([title or ''] + list(authors or [])).strip()
            if not query:
                return
            candidates = self.search_litres(log, title, authors, timeout)
            for url in (
                    BETA_BASE_URL + '/search?q=' + quote(query),
                    BASE_URL + '/find/' + quote(query),
            ):
                log.info('LiveLib search: ' + url)
                try:
                    raw = self.fetch_url(url, timeout)
                except Exception as err:
                    log.exception('LiveLib search failed: %s' % as_unicode(err))
                    raw = None
                if raw:
                    candidates.extend(self.parse_search_results(raw, title, authors))
            candidates.extend(self.search_fantlab(log, title, authors, timeout))
            candidates.sort(key=lambda row: row['score'], reverse=True)

        for candidate in candidates[:6]:
            if abort.is_set():
                return
            if candidate.get('source') == 'litres':
                try:
                    mi = self.fetch_litres_book(log, candidate, timeout)
                except Exception as err:
                    log.exception('LitRes detail failed for %s: %s' % (candidate.get('id'), as_unicode(err)))
                    mi = self.metadata_from_litres_candidate(candidate)
            elif candidate.get('source') == 'fantlab':
                mi = self.metadata_from_fantlab_candidate(candidate)
            else:
                try:
                    mi = self.fetch_book(log, candidate['url'], timeout)
                except Exception as err:
                    log.exception('LiveLib detail failed for %s: %s' % (candidate['url'], as_unicode(err)))
                    mi = self.metadata_from_search_candidate(candidate)
                if mi is not None and candidate.get('cover_url'):
                    livelib_id = (mi.identifiers or {}).get('livelib') or livelib_id_from_url(candidate.get('url'))
                    if livelib_id:
                        self.cache_identifier_to_cover_url(livelib_id, candidate['cover_url'])
                        mi.has_cover = True
            if mi is not None and candidate.get('cover_url') and not mi.cover_data[1]:
                try:
                    self.attach_cover_data(mi, candidate['cover_url'], timeout)
                except Exception as err:
                    log.exception('Cover download failed for %s: %s' % (candidate.get('cover_url'), as_unicode(err)))
            if mi is None:
                continue
            mi.source_relevance = -candidate['score']
            result_queue.put(mi)

    def search_litres(self, log, query_title, query_authors, timeout):
        queries = []
        if query_title:
            queries.append(' '.join([query_title] + list(query_authors or [])).strip())
            queries.append(query_title)
        candidates = []
        seen = set()
        for query in [q for q in queries if q]:
            params = [
                ('q', query), ('limit', '10'), ('offset', '0'),
                ('is_for_pda', 'false'), ('o', 'popular'),
                ('show_unavailable', 'false'),
            ]
            for type_name in ('text_book', 'audiobook', 'paper_book', 'podcast', 'podcast_episode', 'webtoon'):
                params.append(('types', type_name))
            url = LITRES_API_BASE + '/search?' + urlencode(params)
            log.info('LitRes search: ' + url)
            try:
                payload = self.fetch_json(url, timeout).get('payload') or {}
            except Exception as err:
                log.exception('LitRes search failed: %s' % as_unicode(err))
                continue
            for row in payload.get('data') or []:
                item = row.get('instance') or row
                art_id = item.get('id')
                if not art_id or art_id in seen:
                    continue
                persons = item.get('persons') or []
                authors = [p.get('full_name') for p in persons if p.get('role') == 'author' and p.get('full_name')]
                author_text = ', '.join(authors or [p.get('full_name') for p in persons if p.get('full_name')][:2])
                if query_authors and authors:
                    query_author_tokens = set(norm(' '.join(query_authors)).split())
                    result_author_tokens = set(norm(' '.join(authors)).split())
                    if not (query_author_tokens & result_author_tokens):
                        continue
                if not title_match_enough(query_title, item.get('title') or ''):
                    continue
                score = score_match(query_title, query_authors, item.get('title') or '', author_text)
                item_url = item.get('url') or ''
                if item.get('art_type') in (4, 10) or '/audiobook/' in item_url or '/podcast/' in item_url:
                    score -= 20
                if score < 55:
                    continue
                seen.add(art_id)
                cover_url = self.absolutize_litres_cover(item.get('cover_url'), art_id)
                candidates.append({
                    'source': 'litres',
                    'score': score + 5,
                    'id': str(art_id),
                    'title': item.get('title') or '',
                    'authors': authors or (author_text.split(', ') if author_text else ['Unknown']),
                    'url': item.get('url'),
                    'cover_url': cover_url,
                    'raw': item,
                })
        candidates.sort(key=lambda row: row['score'], reverse=True)
        return candidates

    def metadata_from_litres_candidate(self, candidate, item=None):
        item = item or candidate.get('raw') or {}
        title = item.get('title') or candidate.get('title') or ''
        persons = item.get('persons') or []
        authors = [p.get('full_name') for p in persons if p.get('role') == 'author' and p.get('full_name')]
        if not authors:
            authors = candidate.get('authors') or ['Unknown']
        mi = Metadata(title, authors)
        if (item.get('language_code') or '').lower() == 'ru':
            mi.language = 'rus'
        litres_id = str(item.get('id') or candidate.get('id') or '')
        if litres_id:
            mi.set_identifier('litres', litres_id)
        publishers = [p.get('full_name') for p in persons if p.get('role') == 'publisher' and p.get('full_name')]
        if publishers:
            mi.publisher = publishers[0]
        description = item.get('annotation') or item.get('description')
        if not description:
            meta = item.get('meta_tags') or {}
            root_meta = meta.get('root') if isinstance(meta, dict) else None
            if isinstance(root_meta, dict):
                description = root_meta.get('open_graph_description') or root_meta.get('description')
        if description:
            mi.comments = '<p>%s</p>' % as_unicode(description).strip()
        genres = item.get('genres') or item.get('genres_hierarchy') or []
        tags = []
        for genre in genres:
            if isinstance(genre, dict):
                name = genre.get('title') or genre.get('name')
                if name:
                    tags.append(name)
            elif genre:
                tags.append(as_unicode(genre))
        if tags:
            mi.tags = tags[:8]
        rating = item.get('rating') or {}
        try:
            value = rating.get('rated_avg') if isinstance(rating, dict) else rating
            if value:
                mi.rating = float(value) * 2 if float(value) <= 5 else float(value)
        except Exception:
            pass
        cover_url = self.absolutize_litres_cover(item.get('cover_url') or candidate.get('cover_url'), litres_id)
        if cover_url and litres_id:
            self.cache_identifier_to_cover_url(litres_id, cover_url)
            mi.has_cover = True
        return mi

    def fetch_litres_book(self, log, candidate, timeout):
        art_id = candidate.get('id')
        if not art_id:
            return self.metadata_from_litres_candidate(candidate)
        url = LITRES_API_BASE + '/arts/' + quote(str(art_id))
        log.info('LitRes detail: ' + url)
        payload = self.fetch_json(url, timeout).get('payload') or {}
        item = payload.get('data') or payload
        return self.metadata_from_litres_candidate(candidate, item=item)

    def parse_beta_search_payload(self, raw, query_title, query_authors):
        decoded = decode_next_payload(raw)
        candidates = []
        seen = set()
        pos = 0
        marker = '"searchData":'
        while True:
            pos = decoded.find(marker, pos)
            if pos < 0:
                break
            json_text = extract_balanced_json(decoded, pos + len(marker))
            pos += len(marker)
            if not json_text:
                continue
            try:
                data = json.loads(json_text)
            except Exception:
                continue
            rows = ((data.get('payload') or {}).get('data') or [])
            for row in rows:
                if row.get('type') != 'art_editions':
                    continue
                item = row.get('instance') or {}
                href = item.get('url') or ''
                if '/book/' not in href or href in seen:
                    continue
                author_names = [
                    author.get('full_name') for author in item.get('authors') or []
                    if author.get('full_name')
                ]
                result_author = ', '.join(author_names)
                result_title = item.get('title') or ''
                score = score_match(query_title, query_authors, result_title, result_author)
                if score < 50:
                    continue
                seen.add(href)
                cover_url = item.get('cover_url')
                if cover_url and cover_url.startswith('/'):
                    cover_url = BETA_BASE_URL + cover_url
                stats = item.get('stats') or {}
                rating = source_rating(stats.get('rating'))
                candidates.append({
                    'source': 'livelib',
                    'score': score + 8,
                    'url': urljoin(BETA_BASE_URL, href),
                    'title': result_title,
                    'author': result_author or (query_authors or ['Unknown'])[0],
                    'cover_url': cover_url,
                    'rating': as_unicode(rating) if rating is not None else None,
                })
        return candidates

    def parse_search_results(self, raw, query_title, query_authors):
        candidates = self.parse_beta_search_payload(raw, query_title, query_authors)
        seen = {candidate['url'] for candidate in candidates}
        try:
            root = safe_html_fromstring(raw)
        except Exception:
            candidates.sort(key=lambda row: row['score'], reverse=True)
            return candidates
        for block in root.xpath('//div[contains(@class, "object-edition")]'):
            link = block.xpath('.//div[contains(@class, "brow-title")]/a[contains(@class, "title")]')
            author = block.xpath('.//a[contains(@class, "description")]/text()')
            if not link or not author:
                continue
            href = link[0].get('href') or ''
            if not href.startswith('/book/'):
                continue
            url = urljoin(BASE_URL, href)
            if href in seen or url in seen:
                continue
            seen.add(href)
            seen.add(url)
            result_title = unescape(' '.join(link[0].xpath('.//text()'))).strip()
            result_author = unescape(author[0]).strip()
            score = score_match(query_title, query_authors, result_title, result_author)
            if score < 50:
                continue
            cover_url = None
            cover_style = block.xpath('.//span[contains(@class, "object-cover")]/@style')
            if cover_style:
                match = re.search(r'background:url\((.*?)\)', cover_style[0])
                if match:
                    cover_url = match.group(1)

            rating = None
            rating_text = block.xpath('.//span[@itemprop="ratingValue"]/text()')
            if rating_text:
                rating = rating_text[0].strip()

            candidates.append({
                'source': 'livelib',
                'score': score,
                'url': url,
                'title': result_title,
                'author': result_author,
                'cover_url': cover_url,
                'rating': rating,
            })

        for link in root.xpath('//a[contains(@href, "/book/") and normalize-space()]'):
            href = link.get('href') or ''
            url = urljoin(BETA_BASE_URL, href)
            if '/book/' not in href or href in seen or url in seen:
                continue
            result_title = unescape(' '.join(link.xpath('.//text()'))).strip()
            if not result_title:
                continue
            card = link
            author_names = []
            cover_url = None
            rating = None
            for _ in range(6):
                card = card.getparent()
                if card is None:
                    break
                author_names = [
                    unescape(' '.join(a.xpath('.//text()'))).strip()
                    for a in card.xpath('.//a[contains(@href, "/author/")]')
                    if unescape(' '.join(a.xpath('.//text()'))).strip()
                ]
                covers = card.xpath('.//img[contains(@src, "boocover")]/@src')
                if covers:
                    cover_url = covers[0]
                text = re.sub(r'\s+', ' ', card.text_content()).strip()
                match = re.search(r'(\d+(?:[,.]\d+)?)\s*\(\s*([\dKКkк,.\s]+)\s*\)', text)
                if match:
                    rating = match.group(1).replace(',', '.')
                if author_names or cover_url:
                    break
            result_author = ', '.join(dict.fromkeys(author_names)) if author_names else ''
            score = score_match(query_title, query_authors, result_title, result_author)
            if score < 50:
                continue
            seen.add(href)
            seen.add(url)
            if cover_url and cover_url.startswith('/'):
                cover_url = BETA_BASE_URL + cover_url
            candidates.append({
                'source': 'livelib',
                'score': score,
                'url': url,
                'title': result_title,
                'author': result_author or (query_authors or ['Unknown'])[0],
                'cover_url': cover_url,
                'rating': rating,
            })
        candidates.sort(key=lambda row: row['score'], reverse=True)
        return candidates

    def search_fantlab(self, log, query_title, query_authors, timeout):
        query = ' '.join([query_title or ''] + list(query_authors or [])).strip()
        if not query:
            return []
        url = FANTLAB_BASE_URL + '/search-txt?q=' + quote(query)
        log.info('FantLab fallback search: ' + url)
        try:
            raw = self.fetch_url(url, timeout)
            payload = json.loads(raw)
        except Exception as err:
            log.exception('FantLab search failed: %s' % as_unicode(err))
            return []

        candidates = []
        for item in payload.get('works') or []:
            title = item.get('name') or ''
            author_names = [
                a.get('name') for a in ((item.get('creators') or {}).get('authors') or [])
                if a.get('name')
            ]
            author = ', '.join(author_names)
            score = score_match(query_title, query_authors, title, author)
            if score < 50:
                continue
            if item.get('type') != 'work':
                score -= 10
            candidates.append({
                'source': 'fantlab',
                'score': score,
                'title': title,
                'authors': author_names or ['Unknown'],
                'id': item.get('id'),
                'url': 'https:' + item.get('url') if (item.get('url') or '').startswith('//') else item.get('url'),
                'comments': item.get('description') or '',
                'rating': (item.get('stat') or {}).get('rating'),
                'cover_url': FANTLAB_BASE_URL + item.get('image') if item.get('image') else None,
                'tags': [item.get('name_type')] if item.get('name_type') else [],
            })
        candidates.sort(key=lambda row: row['score'], reverse=True)
        return candidates

    def metadata_from_search_candidate(self, candidate):
        title = candidate.get('title') or ''
        author = candidate.get('author') or 'Unknown'
        if not title:
            return None
        mi = Metadata(title, [author])
        mi.language = 'rus'
        livelib_id = livelib_id_from_url(candidate.get('url'))
        if livelib_id:
            mi.set_identifier('livelib', livelib_id)
        # Do not overwrite an existing annotation with a bare source link.
        if candidate.get('summary'):
            mi.comments = '<p>%s</p>' % as_unicode(candidate.get('summary')).strip()
        try:
            if candidate.get('rating'):
                mi.rating = float(candidate['rating']) * 2
        except Exception:
            pass
        cover_url = candidate.get('cover_url')
        if cover_url and livelib_id:
            self.cache_identifier_to_cover_url(livelib_id, cover_url)
        return mi

    def metadata_from_fantlab_candidate(self, candidate):
        mi = Metadata(candidate.get('title') or '', candidate.get('authors') or ['Unknown'])
        mi.language = 'rus'
        fantlab_id = candidate.get('id')
        if fantlab_id:
            mi.set_identifier('fantlab', str(fantlab_id))
        if candidate.get('comments'):
            mi.comments = '<p>%s</p>' % candidate['comments'].replace('\n', '<br/>')
        if candidate.get('tags'):
            mi.tags = candidate['tags']
        try:
            if candidate.get('rating'):
                mi.rating = float(candidate['rating'])
        except Exception:
            pass
        cover_url = candidate.get('cover_url')
        if cover_url and fantlab_id:
            self.cache_identifier_to_cover_url(str(fantlab_id), cover_url)
            mi.has_cover = True
        return mi

    def fetch_book(self, log, url, timeout):
        url = livelib_beta_url(url)
        raw = self.fetch_url(url, timeout)
        data = extract_livelib_json(raw)
        if not data:
            return None

        author_data = data.get('author') or {}
        author_name = author_data.get('name') if isinstance(author_data, dict) else author_data
        title = data.get('name') or ''
        authors = [author_name] if author_name else ['Unknown']
        mi = Metadata(title, authors)
        mi.language = 'rus'

        livelib_id = livelib_id_from_url(url) or livelib_id_from_url(data.get('url'))
        if livelib_id:
            mi.set_identifier('livelib', livelib_id)

        details = extract_livelib_page_details(raw)

        isbn = check_isbn(data.get('isbn') or details.get('isbn'))
        if isbn:
            mi.isbn = isbn

        publisher = details.get('publisher')
        if not publisher:
            publisher_data = data.get('publisher') or {}
            if isinstance(publisher_data, dict):
                publisher = publisher_data.get('name')
            elif publisher_data:
                publisher = as_unicode(publisher_data)
        if publisher:
            mi.publisher = publisher

        year = details.get('year')
        if year:
            match = re.search(r'\d{4}', year)
            if match:
                try:
                    mi.pubdate = datetime(int(match.group(0)), 1, 1)
                except Exception:
                    pass

        description = data.get('description')
        comments = None
        if description:
            comments = '<p>%s</p>' % escape(description).replace('\n', '<br/>')

        genres = data.get('genre') or []
        if isinstance(genres, str):
            genres = [genres]
        mi.tags = [g for g in genres if g]

        rating = ((data.get('aggregateRating') or {}).get('ratingValue'))
        rating_count = ((data.get('aggregateRating') or {}).get('ratingCount'))
        try:
            # Calibre ratings are on a 0..10 scale.
            mi.rating = float(rating) * 2
        except Exception:
            pass

        mi.comments = append_edition_details(comments, details, rating_count=rating_count)

        image = data.get('image')
        if image and livelib_id:
            self.cache_identifier_to_cover_url(livelib_id, image)
            mi.has_cover = True

        return mi

    def get_cached_cover_url(self, identifiers):
        litres_id = (identifiers or {}).get('litres')
        if litres_id:
            return self.cached_identifier_to_cover_url(litres_id)
        livelib_id = (identifiers or {}).get('livelib')
        if livelib_id:
            return self.cached_identifier_to_cover_url(livelib_id)
        fantlab_id = (identifiers or {}).get('fantlab')
        if fantlab_id:
            return self.cached_identifier_to_cover_url(fantlab_id)
        return None

    def find_cover_url_direct(self, log, title=None, authors=None, timeout=30):
        for candidate in self.search_litres(log, title, authors, timeout):
            if candidate.get('cover_url'):
                return candidate['cover_url']
        query = ' '.join([title or ''] + list(authors or [])).strip()
        if query:
            for url in (
                    BETA_BASE_URL + '/search?q=' + quote(query),
                    BASE_URL + '/find/' + quote(query),
            ):
                try:
                    raw = self.fetch_url(url, timeout)
                    for candidate in self.parse_search_results(raw, title, authors):
                        if candidate.get('cover_url'):
                            return candidate['cover_url']
                except Exception as err:
                    log.exception('Direct LiveLib cover search failed: %s' % as_unicode(err))
        for candidate in self.search_fantlab(log, title, authors, timeout):
            if candidate.get('cover_url'):
                return candidate['cover_url']
        return None

    def download_cover(self, log, result_queue, abort, title=None, authors=None,
                       identifiers=None, timeout=30, get_best_cover=False):
        identifiers = identifiers or {}
        url = self.get_cached_cover_url(identifiers)
        if not url and (title or authors):
            q = Queue()
            self.identify(log, q, abort, title=title, authors=authors,
                          identifiers=identifiers, timeout=timeout)
            try:
                mi = q.get_nowait()
            except Empty:
                mi = None
            if mi:
                url = self.get_cached_cover_url(mi.identifiers)
        if not url and (title or authors):
            url = self.find_cover_url_direct(log, title=title, authors=authors, timeout=timeout)
        if url:
            self.download_multiple_covers(title, authors, livelib_cover_candidates(url), get_best_cover,
                                          timeout, result_queue, abort, log,
                                          prefs_name=None)
