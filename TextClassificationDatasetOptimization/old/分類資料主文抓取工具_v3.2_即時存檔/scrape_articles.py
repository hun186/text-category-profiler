#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依來源索引 ZIP 批次抓取網頁正文，保留 #T#[類別]，並輸出獨立正文資料包。

設計原則：
1. 不修改原始元素據 ZIP。
2. 每一筆正文只寫入清理後主文，避免把類別標籤、索引摘要或網址混入訓練文本。
3. 使用 trafilatura 為主、readability 與 BeautifulSoup 為備援。
4. 不繞過登入、付費牆、CAPTCHA 或網站存取限制；失敗項目寫入 CSV。
5. 每篇文章抓取完成後立即寫入 TXT，並同步追加抓取結果 CSV。
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html as html_lib
import io
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.robotparser
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import trafilatura  # type: ignore
except Exception:
    trafilatura = None

try:
    from readability import Document  # type: ignore
except Exception:
    Document = None


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 "
    "ArticleTextCollector/1.0"
)

NOISE_TAGS = {
    "script", "style", "noscript", "nav", "footer", "header", "aside",
    "form", "button", "iframe", "svg", "canvas", "template", "dialog",
    "input", "select", "option", "textarea",
}

NOISE_TOKEN_RE = re.compile(
    r"(?:^|[-_\s])(?:ad|ads|advert|advertisement|advertising|promo|promoted|"
    r"sponsor|sponsored|banner|cookie|consent|gdpr|newsletter|subscribe|signup|"
    r"sign-up|login|register|social|share|sharing|related|recommend|recommended|"
    r"trending|popular|most-read|more-stories|sidebar|comment|comments|footer|"
    r"header|nav|navigation|menu|breadcrumb|modal|popup|overlay|paywall|meter|"
    r"outbrain|taboola|teaser|author-bio|author-box)(?:$|[-_\s])",
    re.I,
)

SHORT_NOISE_RE = re.compile(
    r"^(?:advertisement|ad|recommended stories|related stories|read more|"
    r"more from|sign up|subscribe|newsletter|share|follow us|listen|save|"
    r"copy link|show more|hide|skip to (?:main )?content|cookie preferences|"
    r"all rights reserved|©\s*\d{4}|loading|continue reading|latest news|"
    r"most popular|you may also like|sponsored content|promoted content)\b",
    re.I,
)

BLOCK_PAGE_RE = re.compile(
    r"(?:access denied|captcha|verify you are human|checking your browser|"
    r"enable javascript and cookies|temporarily unavailable|robot check|"
    r"unusual traffic|subscription required|sign in to continue|"
    r"this content is for subscribers|you have reached your article limit)",
    re.I,
)

WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

KNOWN_URL_FIXES = {
    "https://www.globalsecurity.orgwww.globalsecurity.org/": "https://www.globalsecurity.org/",
    "http://www.globalsecurity.orgwww.globalsecurity.org/": "http://www.globalsecurity.org/",
}


@dataclass(frozen=True)
class Entry:
    source_member: str
    category: str
    title: str
    url: str
    domain: str
    language: str
    source_type: str
    published: str
    index_kind: str = ""


@dataclass(frozen=True)
class IndexCandidate:
    title: str
    url: str
    published: str = ""
    source_name: str = ""


@dataclass
class IndexFetchResult:
    index_url: str
    ok: bool
    candidates: list[IndexCandidate]
    method: str = ""
    status_code: Optional[int] = None
    final_url: str = ""
    error: str = ""


@dataclass(frozen=True)
class ArticleTask:
    source_member: str
    category: str
    title: str
    url: str
    domain: str
    language: str
    source_type: str
    published: str
    origin_type: str
    index_title: str = ""
    index_url: str = ""
    search_rank: int = 0


@dataclass
class FetchResult:
    url: str
    ok: bool
    body: str = ""
    method: str = ""
    status_code: Optional[int] = None
    content_type: str = ""
    final_url: str = ""
    error: str = ""


_thread_local = threading.local()
_domain_lock_guard = threading.Lock()
_domain_locks: dict[str, threading.Lock] = {}
_domain_last_request: dict[str, float] = {}
_robots_cache: dict[str, tuple[bool, urllib.robotparser.RobotFileParser]] = {}
_robots_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1.0,
            status_forcelist=(408, 425, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
            "Accept-Language": "zh-TW,zh;q=0.8,en-US;q=0.7,en;q=0.6",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
        })
        _thread_local.session = session
    return session


def repair_url(url: str) -> str:
    url = html_lib.unescape(url.strip())
    for bad, good in KNOWN_URL_FIXES.items():
        if url.startswith(bad):
            url = good + url[len(bad):]
    return url


def parse_field(text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}[：:]\s*(.*)$", text, re.M)
    return m.group(1).strip() if m else ""


def parse_any_field(text: str, *names: str) -> str:
    for name in names:
        value = parse_field(text, name)
        if value:
            return value
    return ""


def detect_index_kind(url: str, source_type: str = "") -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/").lower()
    if host == "bing.com" and path == "/news/search":
        return "bing_news_search"

    marker = source_type.casefold()
    if any(x in marker for x in (
        "candidate source set", "news-search index", "候選來源集合", "新聞搜尋索引",
    )):
        return "unsupported_search_index"
    return ""


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    match = from_bytes(data).best()
    return str(match) if match else data.decode("utf-8", errors="replace")


def read_entries(input_zip: Path) -> list[Entry]:
    entries: list[Entry] = []
    with zipfile.ZipFile(input_zip) as zf:
        for member in zf.namelist():
            if not member.lower().endswith(".txt"):
                continue
            text = decode_text(zf.read(member))
            m = re.search(r"^#T#\[(.*?)\]\s*$", text, re.M)
            if not m:
                continue
            category = m.group(1).strip()
            title = parse_any_field(
                text, "原文標題", "來源標題（原文）", "來源標題(原文)", "Source title",
            )
            url = repair_url(parse_any_field(
                text, "原文連結", "原文／索引連結", "原文/索引連結",
                "原文或索引連結", "Original or index URL",
            ))
            if not title or not url:
                continue
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower().removeprefix("www.")
            source_type = parse_any_field(text, "來源型態", "Source type")
            entries.append(Entry(
                source_member=member,
                category=category,
                title=title,
                url=url,
                domain=domain,
                language=parse_any_field(
                    text, "語言", "語言版本", "來源語言索引",
                    "Language version", "Indexed source language",
                ),
                source_type=source_type,
                published=parse_any_field(text, "發布時間", "Publication date"),
                index_kind=detect_index_kind(url, source_type),
            ))
    if not entries:
        raise ValueError(
            "ZIP 中沒有找到含 #T#[類別]、來源標題與原文／索引連結的 TXT。"
        )
    return entries


def safe_component(value: str, max_len: int = 120) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    value = value.translate(str.maketrans({
        "<": "＜", ">": "＞", ":": "：", '"': "＂", "/": "／",
        "\\": "＼", "|": "｜", "?": "？", "*": "＊",
    }))
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = "未命名"
    if value.upper() in WINDOWS_RESERVED:
        value = "_" + value
    if len(value) > max_len:
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
        value = value[: max_len - 11].rstrip() + "__" + digest
    return value


def build_output_names(entries: list[Entry]) -> dict[Entry, str]:
    used: dict[str, Counter[str]] = defaultdict(Counter)
    result: dict[Entry, str] = {}
    for entry in entries:
        base = safe_component(entry.title)
        key = base.casefold()
        used[entry.category][key] += 1
        number = used[entry.category][key]
        filename = f"{base}.txt" if number == 1 else f"{base}__{number}.txt"
        result[entry] = filename
    return result



TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "dclid", "msclkid", "ocid", "cmpid", "campaignid",
    "ref_src", "ref_url", "spm", "igshid", "mc_cid", "mc_eid",
}


def canonicalize_article_url(url: str) -> str:
    url = repair_url(url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    filtered_query = []
    for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        low = key.casefold()
        if low.startswith("utm_") or low in TRACKING_QUERY_KEYS:
            continue
        filtered_query.append((key, value))
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urllib.parse.urlunparse((
        parsed.scheme.lower(), parsed.netloc.lower(), path,
        parsed.params, urllib.parse.urlencode(filtered_query, doseq=True), "",
    ))


def decode_urlsafe_base64(value: str) -> str:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="strict")
        return decoded if decoded.startswith(("http://", "https://")) else ""
    except Exception:
        return ""


def unwrap_bing_url(raw_url: str, base_url: str = "https://www.bing.com/") -> str:
    if not raw_url:
        return ""
    url = html_lib.unescape(raw_url.strip())
    url = urllib.parse.urljoin(base_url, url)
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")

    if host == "bing.com":
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("url", "r", "target", "u"):
            for raw_value in query.get(key, []):
                value = urllib.parse.unquote(raw_value)
                candidates = [value]
                if value.startswith("a1"):
                    candidates.insert(0, decode_urlsafe_base64(value[2:]))
                else:
                    candidates.insert(0, decode_urlsafe_base64(value))
                for candidate in candidates:
                    if candidate.startswith(("http://", "https://")):
                        return canonicalize_article_url(candidate)
        return ""

    return canonicalize_article_url(url)


def is_probable_article_url(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host == "bing.com":
        return False
    if re.search(r"\.(?:jpg|jpeg|png|gif|webp|svg|ico|mp4|mp3|zip)(?:$|\?)", path):
        return False
    return True


def clean_candidate_title(title: str) -> str:
    title = html_lib.unescape(title or "")
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"\s*[|｜]\s*Bing\s*$", "", title, flags=re.I)
    return title


def make_bing_rss_url(index_url: str) -> str:
    parsed = urllib.parse.urlparse(index_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    kept = [(k, v) for k, v in query if k.casefold() not in {"form", "format"}]
    kept.append(("format", "rss"))
    return urllib.parse.urlunparse((
        parsed.scheme or "https", parsed.netloc or "www.bing.com", "/news/search", "",
        urllib.parse.urlencode(kept, doseq=True), "",
    ))


def parse_bing_rss(xml_text: str, max_results: int) -> list[IndexCandidate]:
    soup = BeautifulSoup(xml_text, "xml")
    candidates: list[IndexCandidate] = []
    seen: set[str] = set()
    for item in soup.find_all("item"):
        title_node = item.find("title")
        link_node = item.find("link")
        if not link_node:
            continue
        title = clean_candidate_title(title_node.get_text(" ", strip=True) if title_node else "")
        url = unwrap_bing_url(link_node.get_text(" ", strip=True))
        if not is_probable_article_url(url) or url in seen:
            continue
        published_node = item.find("pubDate")
        source_node = item.find("source")
        candidates.append(IndexCandidate(
            title=title or urllib.parse.urlparse(url).netloc,
            url=url,
            published=published_node.get_text(" ", strip=True) if published_node else "",
            source_name=source_node.get_text(" ", strip=True) if source_node else "",
        ))
        seen.add(url)
        if max_results > 0 and len(candidates) >= max_results:
            break
    return candidates


def parse_bing_html(html: str, base_url: str, max_results: int) -> list[IndexCandidate]:
    soup = BeautifulSoup(html, "lxml")
    selectors = [
        "a.title[href]", ".news-card a[href]", ".newsitem a[href]",
        "article a[href]", "main a[href]", "a[data-url]",
    ]
    anchors = []
    seen_nodes: set[int] = set()
    for selector in selectors:
        for anchor in soup.select(selector):
            identity = id(anchor)
            if identity not in seen_nodes:
                anchors.append(anchor)
                seen_nodes.add(identity)
    if not anchors:
        anchors = soup.find_all("a", href=True)

    candidates: list[IndexCandidate] = []
    seen_urls: set[str] = set()
    for anchor in anchors:
        raw_url = anchor.get("data-url") or anchor.get("data-href") or anchor.get("href") or ""
        url = unwrap_bing_url(raw_url, base_url)
        if not is_probable_article_url(url) or url in seen_urls:
            continue
        title = clean_candidate_title(
            " ".join(anchor.stripped_strings) or str(anchor.get("aria-label", ""))
        )
        if len(title) < 6:
            continue
        candidates.append(IndexCandidate(title=title, url=url))
        seen_urls.add(url)
        if max_results > 0 and len(candidates) >= max_results:
            break
    return candidates


def read_limited_response(response: requests.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > max_bytes:
            raise ValueError(f"內容超過限制 {max_bytes // (1024 * 1024)} MB")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_bing_index(
    entry: Entry,
    *,
    timeout: tuple[float, float],
    max_bytes: int,
    max_results: int,
    per_domain_delay: float,
    respect_robots: bool,
) -> IndexFetchResult:
    """展開 Bing News 索引。max_results=0 表示不設程式端上限。"""
    session = get_session()
    attempts: list[str] = []
    rss_url = make_bing_rss_url(entry.url)
    merged: list[IndexCandidate] = []
    seen_urls: set[str] = set()
    successful_methods: list[str] = []
    last_status: Optional[int] = None
    last_final_url = ""

    for method, request_url in (("bing-rss", rss_url), ("bing-html", entry.url)):
        try:
            if respect_robots and not robots_allowed(request_url, session, timeout):
                attempts.append(f"{method}: robots.txt 不允許抓取")
                continue
            domain_wait(urllib.parse.urlparse(request_url).netloc.lower(), per_domain_delay)
            response = session.get(request_url, timeout=timeout, allow_redirects=True, stream=True)
            status = response.status_code
            response.raise_for_status()
            data = read_limited_response(response, max_bytes)
            response._content = data
            text = response_to_text(response)

            # 正式模式（0）解析端點回傳的全部候選；有限模式只解析尚缺的數量。
            remaining = 0 if max_results <= 0 else max_results - len(merged)
            if max_results > 0 and remaining <= 0:
                break
            if method == "bing-rss":
                candidates = parse_bing_rss(text, remaining)
            else:
                candidates = parse_bing_html(text, response.url, remaining)

            added = 0
            for candidate in candidates:
                canonical = canonicalize_article_url(candidate.url) or candidate.url
                if canonical in seen_urls:
                    continue
                seen_urls.add(canonical)
                merged.append(IndexCandidate(
                    title=candidate.title,
                    url=canonical,
                    published=candidate.published,
                    source_name=candidate.source_name,
                ))
                added += 1
                if max_results > 0 and len(merged) >= max_results:
                    break

            if added:
                successful_methods.append(method)
                last_status = status
                last_final_url = response.url
            else:
                attempts.append(f"{method}: 未解析到新的候選文章")

            if max_results > 0 and len(merged) >= max_results:
                break
        except Exception as exc:
            attempts.append(f"{method}: {type(exc).__name__}: {exc}")

    if merged:
        return IndexFetchResult(
            index_url=entry.url,
            ok=True,
            candidates=merged,
            method="+".join(successful_methods) or "bing",
            status_code=last_status,
            final_url=last_final_url,
        )

    return IndexFetchResult(
        index_url=entry.url, ok=False, candidates=[], error="；".join(attempts)
    )


def fetch_index_one(
    entry: Entry,
    *,
    timeout: tuple[float, float],
    max_bytes: int,
    max_results: int,
    per_domain_delay: float,
    respect_robots: bool,
) -> IndexFetchResult:
    if entry.index_kind == "bing_news_search":
        return fetch_bing_index(
            entry, timeout=timeout, max_bytes=max_bytes, max_results=max_results,
            per_domain_delay=per_domain_delay, respect_robots=respect_robots,
        )
    return IndexFetchResult(
        index_url=entry.url, ok=False, candidates=[],
        error=f"尚未支援的搜尋索引型態：{entry.index_kind or 'unknown'}",
    )


def task_key(task: ArticleTask, dedupe_scope: str) -> tuple[str, ...]:
    canonical = canonicalize_article_url(task.url) or task.url
    if dedupe_scope == "global":
        return (canonical,)
    if dedupe_scope == "none":
        return (task.category, canonical, task.source_member, str(task.search_rank))
    return (task.category, canonical)


def unique_output_filename(
    category: str, title: str, used: dict[str, Counter[str]]
) -> str:
    base = safe_component(title)
    key = base.casefold()
    used[category][key] += 1
    number = used[category][key]
    return f"{base}.txt" if number == 1 else f"{base}__{number}.txt"

def domain_wait(domain: str, delay: float) -> None:
    if delay <= 0:
        return
    with _domain_lock_guard:
        lock = _domain_locks.setdefault(domain, threading.Lock())
    with lock:
        last = _domain_last_request.get(domain, 0.0)
        remaining = delay - (time.monotonic() - last)
        if remaining > 0:
            time.sleep(remaining)
        _domain_last_request[domain] = time.monotonic()


def robots_allowed(url: str, session: requests.Session, timeout: tuple[float, float]) -> bool:
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = urllib.parse.urljoin(base, "/robots.txt")
    with _robots_lock:
        cached = _robots_cache.get(base)
    if cached is not None:
        reachable, parser = cached
        return True if not reachable else parser.can_fetch(USER_AGENT, url)

    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    reachable = False
    try:
        response = session.get(robots_url, timeout=timeout, allow_redirects=True)
        if response.status_code < 400:
            parser.parse(response.text.splitlines())
            reachable = True
    except requests.RequestException:
        pass
    with _robots_lock:
        _robots_cache[base] = (reachable, parser)
    return True if not reachable else parser.can_fetch(USER_AGENT, url)


def response_to_text(response: requests.Response) -> str:
    if response.encoding and response.encoding.lower() not in {"iso-8859-1", "ascii"}:
        return response.text
    match = from_bytes(response.content).best()
    if match:
        return str(match)
    return response.content.decode("utf-8", errors="replace")


def normalize_body(text: str) -> str:
    text = html_lib.unescape(text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    previous = ""
    for raw in text.splitlines():
        line = re.sub(r"[\t\u00a0 ]+", " ", raw).strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if len(line) <= 100 and SHORT_NOISE_RE.search(line):
            continue
        if line == previous:
            continue
        previous = line
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def node_is_noise(tag) -> bool:
    attrs = " ".join([
        str(tag.get("id", "")),
        " ".join(tag.get("class", []) if isinstance(tag.get("class"), list) else [str(tag.get("class", ""))]),
        str(tag.get("role", "")),
        str(tag.get("aria-label", "")),
    ])
    return bool(NOISE_TOKEN_RE.search(attrs))


def soup_to_paragraphs(node) -> str:
    parts: list[str] = []
    for element in node.find_all(["h2", "h3", "h4", "p", "li", "blockquote", "pre"], recursive=True):
        if element.find_parent(list(NOISE_TAGS)):
            continue
        text = " ".join(element.stripped_strings)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if len(text) <= 100 and SHORT_NOISE_RE.search(text):
            continue
        if element.name == "li":
            text = "• " + text
        parts.append(text)
    if not parts:
        parts = [re.sub(r"\s+", " ", node.get_text(" ", strip=True))]
    return normalize_body("\n\n".join(parts))


def candidate_score(node) -> float:
    text = node.get_text(" ", strip=True)
    if not text:
        return 0.0
    total = len(text)
    link_text = sum(len(a.get_text(" ", strip=True)) for a in node.find_all("a"))
    link_density = min(1.0, link_text / max(total, 1))
    paragraphs = len(node.find_all("p"))
    headings = len(node.find_all(["h2", "h3"]))
    return total * (1.0 - 0.85 * link_density) + paragraphs * 80 + headings * 30


def extract_with_bs4(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for tag in list(soup.find_all(True)):
        try:
            if node_is_noise(tag):
                tag.decompose()
        except Exception:
            continue

    selectors = [
        "article", "main", "[role='main']", "#article-body", ".article-body",
        ".article-content", ".story-body", ".story-content", ".entry-content",
        ".post-content", ".content-body", ".field--name-body", ".node__content",
        ".td-post-content", ".caas-body",
    ]
    candidates = []
    for selector in selectors:
        candidates.extend(soup.select(selector))
    if not candidates:
        candidates = soup.find_all(["section", "div"], limit=1000)
    if not candidates:
        candidates = [soup.body or soup]
    best = max(candidates, key=candidate_score)
    return soup_to_paragraphs(best)


def extract_html(html: str, url: str) -> tuple[str, str]:
    candidates: list[tuple[str, str]] = []
    if trafilatura is not None:
        try:
            text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=False,
                include_images=False,
                include_links=False,
                favor_precision=True,
                no_fallback=False,
                output_format="txt",
            )
            if text:
                candidates.append((normalize_body(text), "trafilatura"))
        except Exception:
            pass

    if Document is not None:
        try:
            summary_html = Document(html).summary(html_partial=True)
            text = extract_with_bs4(summary_html)
            if text:
                candidates.append((text, "readability"))
        except Exception:
            pass

    try:
        text = extract_with_bs4(html)
        if text:
            candidates.append((text, "beautifulsoup"))
    except Exception:
        pass

    if not candidates:
        return "", ""
    # 優先精確抽取；若結果過短，改採較長且仍合理的候選。
    candidates.sort(key=lambda item: len(item[0]), reverse=True)
    longest = candidates[0]
    preferred = next((x for x in candidates if x[1] == "trafilatura" and len(x[0]) >= 500), None)
    return preferred or longest


def extract_pdf(data: bytes) -> tuple[str, str]:
    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text(extraction_mode="layout") or page.extract_text() or ""
        except TypeError:
            text = page.extract_text() or ""
        if text.strip():
            pages.append(text)
    return normalize_body("\n\n".join(pages)), "pypdf"


def looks_blocked(text: str) -> bool:
    sample = text[:5000]
    return bool(BLOCK_PAGE_RE.search(sample)) and len(text) < 3000


def fetch_one(
    url: str,
    *,
    timeout: tuple[float, float],
    max_bytes: int,
    min_chars: int,
    per_domain_delay: float,
    respect_robots: bool,
) -> FetchResult:
    session = get_session()
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    try:
        if respect_robots and not robots_allowed(url, session, timeout):
            return FetchResult(url=url, ok=False, error="robots.txt 不允許抓取")
        domain_wait(domain, per_domain_delay)
        response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
        status = response.status_code
        content_type = (response.headers.get("Content-Type") or "").lower()
        response.raise_for_status()

        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"內容超過限制 {max_bytes // (1024*1024)} MB")
            chunks.append(chunk)
        data = b"".join(chunks)

        if "application/pdf" in content_type or data.startswith(b"%PDF-") or response.url.lower().split("?")[0].endswith(".pdf"):
            body, method = extract_pdf(data)
        elif "text/html" in content_type or "application/xhtml" in content_type or b"<html" in data[:1000].lower():
            response._content = data
            html = response_to_text(response)
            body, method = extract_html(html, response.url)
        elif content_type.startswith("text/plain"):
            body, method = normalize_body(decode_text(data)), "plain-text"
        else:
            return FetchResult(
                url=url, ok=False, status_code=status, content_type=content_type,
                final_url=response.url, error=f"不支援的內容型態：{content_type or 'unknown'}",
            )

        body = normalize_body(body)
        if looks_blocked(body):
            return FetchResult(
                url=url, ok=False, status_code=status, content_type=content_type,
                final_url=response.url, method=method, error="頁面疑似存取限制、CAPTCHA 或付費牆",
            )
        if len(body) < min_chars:
            return FetchResult(
                url=url, ok=False, status_code=status, content_type=content_type,
                final_url=response.url, method=method,
                error=f"正文過短（{len(body)} 字元，小於 {min_chars}）",
            )
        return FetchResult(
            url=url, ok=True, body=body, method=method, status_code=status,
            content_type=content_type, final_url=response.url,
        )
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return FetchResult(url=url, ok=False, status_code=status, error=f"{type(exc).__name__}: {exc}")


def write_utf8(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def zip_output(output_dir: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as zf:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(output_dir))


def write_source_manifest(entries: list[Entry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "序號", "類別", "原文標題", "網域", "語言", "來源型態", "發布時間",
            "原文／索引連結", "索引型態", "來源元素據檔",
        ])
        for i, e in enumerate(entries, 1):
            writer.writerow([
                i, e.category, e.title, e.domain, e.language, e.source_type,
                e.published, e.url, e.index_kind or "單篇來源", e.source_member,
            ])


def write_dict_rows(
    rows: list[dict[str, object]], path: Path, fields: list[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


RESULT_FIELDS = [
    "序號", "狀態", "來源方式", "類別", "原文標題", "網域", "原文連結",
    "索引標題", "索引連結", "搜尋順位", "來源元素據檔", "最終網址",
    "HTTP狀態", "內容型態", "擷取方法", "正文字元數", "輸出檔", "錯誤",
]


def write_results(rows: list[dict[str, object]], path: Path) -> None:
    write_dict_rows(rows, path, RESULT_FIELDS)


def write_index_results(rows: list[dict[str, object]], path: Path) -> None:
    fields = [
        "原始序號", "狀態", "類別", "索引型態", "索引標題", "索引連結",
        "展開方法", "HTTP狀態", "候選順位", "候選標題", "候選來源",
        "候選發布時間", "候選網址", "來源元素據檔", "錯誤",
    ]
    write_dict_rows(rows, path, fields)


def find_default_input(base: Path) -> Path:
    candidates = sorted((base / "01_輸入元素據").glob("*.zip"))
    if not candidates:
        candidates = sorted(base.glob("*.zip"))
    if not candidates:
        raise FileNotFoundError("找不到輸入 ZIP，請用 --input-zip 指定。")
    return candidates[0]


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="批次展開來源索引並抓取單篇網頁正文"
    )
    parser.add_argument("--input-zip", type=Path, help="來源元素據 ZIP")
    parser.add_argument("--output-dir", type=Path, default=script_dir / "02_正文輸出")
    parser.add_argument("--output-zip", type=Path, help="輸出正文 ZIP；未指定時依輸入檔名產生")
    parser.add_argument("--log-dir", type=Path, default=script_dir / "04_執行紀錄")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--read-timeout", type=float, default=45.0)
    parser.add_argument("--per-domain-delay", type=float, default=1.2)
    parser.add_argument("--min-chars", type=int, default=500)
    parser.add_argument("--max-mb", type=int, default=30)
    parser.add_argument("--index-max-mb", type=int, default=5)
    parser.add_argument(
        "--max-results-per-index", type=int, default=0,
        help="每個搜尋結果集合最多展開幾篇候選文章；0 表示不限（正式模式預設）",
    )
    parser.add_argument(
        "--max-articles-per-category", type=int, default=0,
        help="每類最多保留幾篇；0 表示不限（正式模式預設）",
    )
    parser.add_argument(
        "--test-mode", action="store_true",
        help="測試模式：每個搜尋集合最多 10 篇、每類最多 20 篇",
    )
    parser.add_argument(
        "--dedupe-scope", choices=("category", "global", "none"), default="category",
        help="網址去重範圍：category=同類別、global=所有類別、none=不去重",
    )
    parser.add_argument(
        "--skip-search-index", action="store_true",
        help="不展開搜尋結果集合，只處理單篇來源",
    )
    parser.add_argument("--ignore-robots", action="store_true", help="僅在已取得授權時使用")
    parser.add_argument("--dry-run", action="store_true", help="只檢查資料格式，不連線")
    parser.add_argument("--clean-output", action="store_true", help="先清空既有正文輸出")
    args = parser.parse_args()

    if args.max_results_per_index < 0:
        parser.error("--max-results-per-index 不可小於 0；0 表示不限")
    if args.max_articles_per_category < 0:
        parser.error("--max-articles-per-category 不可小於 0；0 表示不限")

    if args.test_mode:
        effective_max_results_per_index = 10
        effective_max_articles_per_category = 20
        run_mode = "測試模式"
    else:
        effective_max_results_per_index = args.max_results_per_index
        effective_max_articles_per_category = args.max_articles_per_category
        run_mode = "正式模式"

    input_zip = (args.input_zip or find_default_input(script_dir)).resolve()
    output_dir = args.output_dir.resolve()
    output_zip = (
        args.output_zip
        or script_dir / "03_輸出壓縮包" / f"{input_zip.stem}_正文包.zip"
    ).resolve()
    log_dir = args.log_dir.resolve()

    if args.clean_output and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    entries = read_entries(input_zip)
    write_source_manifest(entries, log_dir / "來源清單.csv")

    categories = Counter(e.category for e in entries)
    direct_entries = [e for e in entries if not e.index_kind]
    index_entries = [e for e in entries if e.index_kind]
    supported_index_entries = [e for e in index_entries if e.index_kind == "bing_news_search"]
    unsupported_index_entries = [e for e in index_entries if e.index_kind != "bing_news_search"]

    index_limit_text = (
        "不限（展開端點回傳的全部候選）"
        if effective_max_results_per_index == 0
        else str(effective_max_results_per_index)
    )
    category_limit_text = (
        "不限"
        if effective_max_articles_per_category == 0
        else str(effective_max_articles_per_category)
    )
    print(
        f"讀取完成：{len(entries)} 筆、{len(categories)} 類；"
        f"單篇來源 {len(direct_entries)} 筆、搜尋結果集合 {len(index_entries)} 筆"
    )
    print(
        f"執行模式：{run_mode}；每個搜尋集合上限：{index_limit_text}；"
        f"每類文章上限：{category_limit_text}"
    )
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")
    if unsupported_index_entries:
        print(f"警告：有 {len(unsupported_index_entries)} 筆搜尋索引型態尚未支援。")

    if args.dry_run:
        direct_names = build_output_names(direct_entries)
        preview_rows: list[dict[str, object]] = []
        for i, e in enumerate(entries, 1):
            if e.index_kind:
                status = "INDEX_PENDING" if e.index_kind == "bing_news_search" else "UNSUPPORTED_INDEX"
                output_file = ""
            else:
                status = "DIRECT_PENDING"
                output_file = str(
                    Path(f"#T#[{safe_component(e.category, 100)}]") / direct_names[e]
                )
            preview_rows.append({
                "序號": i,
                "狀態": status,
                "來源方式": e.index_kind or "direct",
                "類別": e.category,
                "原文標題": e.title,
                "網域": e.domain,
                "原文連結": e.url,
                "來源元素據檔": e.source_member,
                "輸出檔": output_file,
            })
        write_results(preview_rows, log_dir / "乾跑檢查結果.csv")
        print("乾跑完成；未展開搜尋結果、未下載正文。")
        return 0

    timeout = (args.connect_timeout, args.read_timeout)
    respect_robots = not args.ignore_robots

    # 第一階段：展開搜尋結果集合；同一個索引 URL 只抓一次。
    index_fetch_results: dict[str, IndexFetchResult] = {}
    if supported_index_entries and not args.skip_search_index:
        representative: dict[str, Entry] = {}
        for entry in supported_index_entries:
            representative.setdefault(entry.url, entry)
        print(f"開始展開 {len(representative)} 個不重複搜尋索引……")
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {
                pool.submit(
                    fetch_index_one,
                    entry,
                    timeout=timeout,
                    max_bytes=args.index_max_mb * 1024 * 1024,
                    max_results=effective_max_results_per_index,
                    per_domain_delay=args.per_domain_delay,
                    respect_robots=respect_robots,
                ): url
                for url, entry in representative.items()
            }
            completed = 0
            for future in as_completed(futures):
                url = futures[future]
                result = future.result()
                index_fetch_results[url] = result
                completed += 1
                mark = "OK" if result.ok else "FAIL"
                extra = f"{len(result.candidates)} results" if result.ok else result.error
                print(f"[INDEX {completed:03d}/{len(futures):03d}] {mark} {url} — {extra}")

    article_tasks: list[ArticleTask] = []
    index_rows: list[dict[str, object]] = []

    # 單篇來源直接加入正文抓取工作。
    for entry in direct_entries:
        article_url = canonicalize_article_url(entry.url) or entry.url
        article_tasks.append(ArticleTask(
            source_member=entry.source_member,
            category=entry.category,
            title=entry.title,
            url=article_url,
            domain=urllib.parse.urlparse(article_url).netloc.lower().removeprefix("www."),
            language=entry.language,
            source_type=entry.source_type,
            published=entry.published,
            origin_type="direct",
        ))

    # 搜尋索引展開後，每個候選結果都變成一筆獨立正文抓取工作。
    entry_sequence = {entry: i for i, entry in enumerate(entries, 1)}
    for entry in index_entries:
        base_row = {
            "原始序號": entry_sequence[entry],
            "類別": entry.category,
            "索引型態": entry.index_kind,
            "索引標題": entry.title,
            "索引連結": entry.url,
            "來源元素據檔": entry.source_member,
        }
        if args.skip_search_index:
            index_rows.append({**base_row, "狀態": "略過", "錯誤": "使用 --skip-search-index"})
            continue
        result = index_fetch_results.get(entry.url)
        if result is None:
            reason = (
                f"尚未支援的搜尋索引型態：{entry.index_kind}"
                if entry.index_kind != "bing_news_search"
                else "搜尋索引未執行"
            )
            index_rows.append({**base_row, "狀態": "失敗", "錯誤": reason})
            continue
        if not result.ok:
            index_rows.append({
                **base_row,
                "狀態": "失敗",
                "展開方法": result.method,
                "HTTP狀態": result.status_code if result.status_code is not None else "",
                "錯誤": result.error,
            })
            continue

        for rank, candidate in enumerate(result.candidates, 1):
            article_url = canonicalize_article_url(candidate.url) or candidate.url
            article_tasks.append(ArticleTask(
                source_member=entry.source_member,
                category=entry.category,
                title=candidate.title or entry.title,
                url=article_url,
                domain=urllib.parse.urlparse(article_url).netloc.lower().removeprefix("www."),
                language=entry.language,
                source_type="search-index candidate article",
                published=candidate.published or entry.published,
                origin_type="search_result",
                index_title=entry.title,
                index_url=entry.url,
                search_rank=rank,
            ))
            index_rows.append({
                **base_row,
                "狀態": "展開成功",
                "展開方法": result.method,
                "HTTP狀態": result.status_code if result.status_code is not None else "",
                "候選順位": rank,
                "候選標題": candidate.title,
                "候選來源": candidate.source_name,
                "候選發布時間": candidate.published,
                "候選網址": article_url,
            })

    index_results_csv = log_dir / "索引展開結果.csv"
    write_index_results(index_rows, index_results_csv)

    # 依指定範圍去重。direct 工作先加入，因此相同網址同類別時優先保留明確單篇來源。
    retained_tasks: list[ArticleTask] = []
    seen_task_keys: set[tuple[str, ...]] = set()
    duplicate_count = 0
    for task in article_tasks:
        key = task_key(task, args.dedupe_scope)
        if key in seen_task_keys:
            duplicate_count += 1
            continue
        seen_task_keys.add(key)
        retained_tasks.append(task)

    capped_count = 0
    if effective_max_articles_per_category > 0:
        category_kept: Counter[str] = Counter()
        capped_tasks: list[ArticleTask] = []
        for task in retained_tasks:
            if category_kept[task.category] >= effective_max_articles_per_category:
                capped_count += 1
                continue
            category_kept[task.category] += 1
            capped_tasks.append(task)
        retained_tasks = capped_tasks

    unique_article_urls = sorted({task.url for task in retained_tasks})
    print(
        f"索引展開後共 {len(article_tasks)} 筆文章工作；"
        f"去重移除 {duplicate_count} 筆、類別上限移除 {capped_count} 筆；"
        f"準備抓取 {len(unique_article_urls)} 個不重複文章網址。"
    )

    # 第二階段：抓取每篇文章主文。每個網址完成後立即寫入對應 TXT，
    # 並同步追加、flush 抓取結果.csv；中途停止時，已完成成果仍會保留。
    tasks_by_url: dict[str, list[ArticleTask]] = defaultdict(list)
    for task in retained_tasks:
        tasks_by_url[task.url].append(task)

    # 預先決定序號與輸出檔名，避免平行完成順序影響檔名。
    used_names: dict[str, Counter[str]] = defaultdict(Counter)
    task_sequence: dict[ArticleTask, int] = {}
    task_rel_paths: dict[ArticleTask, Path] = {}
    for i, task in enumerate(retained_tasks, 1):
        task_sequence[task] = i
        filename = unique_output_filename(task.category, task.title, used_names)
        task_rel_paths[task] = (
            Path(f"#T#[{safe_component(task.category, 100)}]") / filename
        )

    result_rows: list[dict[str, object]] = []
    success = 0
    failed = 0
    results_csv = log_dir / "抓取結果.csv"
    output_results_csv = output_dir / "抓取結果.csv"
    results_csv.parent.mkdir(parents=True, exist_ok=True)
    output_results_csv.parent.mkdir(parents=True, exist_ok=True)

    with (
        results_csv.open("w", encoding="utf-8-sig", newline="") as result_file,
        output_results_csv.open("w", encoding="utf-8-sig", newline="") as output_result_file,
    ):
        result_writer = csv.DictWriter(
            result_file, fieldnames=RESULT_FIELDS, extrasaction="ignore"
        )
        output_result_writer = csv.DictWriter(
            output_result_file, fieldnames=RESULT_FIELDS, extrasaction="ignore"
        )
        result_writer.writeheader()
        output_result_writer.writeheader()
        result_file.flush()
        output_result_file.flush()

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {
                pool.submit(
                    fetch_one,
                    url,
                    timeout=timeout,
                    max_bytes=args.max_mb * 1024 * 1024,
                    min_chars=args.min_chars,
                    per_domain_delay=args.per_domain_delay,
                    respect_robots=respect_robots,
                ): url
                for url in unique_article_urls
            }
            completed = 0
            for future in as_completed(futures):
                url = futures[future]
                result = future.result()
                completed += 1
                saved_for_url = 0

                for task in tasks_by_url[url]:
                    rel_path = task_rel_paths[task]
                    out_path = output_dir / rel_path
                    if result.ok:
                        # TXT 只保留清理後正文；類別由外層 #T#[類別] 目錄表示。
                        write_utf8(out_path, result.body.strip() + "\n")
                        status = "成功"
                        success += 1
                        saved_for_url += 1
                    else:
                        status = "失敗"
                        failed += 1

                    row = {
                        "序號": task_sequence[task],
                        "狀態": status,
                        "來源方式": task.origin_type,
                        "類別": task.category,
                        "原文標題": task.title,
                        "網域": task.domain,
                        "原文連結": task.url,
                        "索引標題": task.index_title,
                        "索引連結": task.index_url,
                        "搜尋順位": task.search_rank if task.search_rank else "",
                        "來源元素據檔": task.source_member,
                        "最終網址": result.final_url,
                        "HTTP狀態": result.status_code if result.status_code is not None else "",
                        "內容型態": result.content_type,
                        "擷取方法": result.method,
                        "正文字元數": len(result.body) if result.ok else 0,
                        "輸出檔": str(rel_path) if result.ok else "",
                        "錯誤": result.error,
                    }
                    result_rows.append(row)
                    result_writer.writerow(row)
                    output_result_writer.writerow(row)
                    # 每篇都立刻刷新到紀錄目錄與正文輸出目錄，不等整批完成。
                    result_file.flush()
                    output_result_file.flush()

                mark = "OK" if result.ok else "FAIL"
                extra = f"{len(result.body)} chars; saved {saved_for_url} file(s)" if result.ok else result.error
                print(f"[ARTICLE {completed:04d}/{len(futures):04d}] {mark} {url} — {extra}")

    shutil.copy2(index_results_csv, output_dir / "索引展開結果.csv")

    successful_by_category = Counter(
        row["類別"] for row in result_rows if row["狀態"] == "成功"
    )
    task_by_category = Counter(task.category for task in retained_tasks)
    index_success_count = sum(1 for result in index_fetch_results.values() if result.ok)
    index_failed_count = len(index_entries) - sum(
        1 for entry in index_entries
        if index_fetch_results.get(entry.url) and index_fetch_results[entry.url].ok
    )

    summary = [
        "分類訓練正文抓取摘要",
        "=" * 32,
        f"完成時間：{now_iso()}",
        f"來源元素據：{input_zip.name}",
        f"執行模式：{run_mode}",
        f"每個搜尋集合上限：{index_limit_text}",
        f"每類文章上限：{category_limit_text}",
        f"原始記錄：{len(entries)}",
        f"單篇來源記錄：{len(direct_entries)}",
        f"搜尋結果集合記錄：{len(index_entries)}",
        f"成功展開的不重複搜尋索引：{index_success_count}",
        f"未成功展開的搜尋索引記錄：{index_failed_count}",
        f"展開前文章工作：{len(article_tasks)}",
        f"網址去重移除：{duplicate_count}",
        f"類別數量上限移除：{capped_count}",
        f"實際文章工作：{len(retained_tasks)}",
        f"不重複文章網址：{len(unique_article_urls)}",
        f"成功輸出：{success}",
        f"失敗／受限：{failed}",
        "",
        "類別結果：",
    ]
    for category in sorted(categories):
        summary.append(
            f"- {category}: 成功 {successful_by_category[category]} / "
            f"文章工作 {task_by_category[category]} / 原始記錄 {categories[category]}"
        )
    summary += [
        "",
        "處理規則：",
        (
            "- 每個搜尋索引不設程式端篇數上限，合併 RSS 與 HTML 可取得的候選文章。"
            if effective_max_results_per_index == 0
            else f"- 每個搜尋索引最多展開 {effective_max_results_per_index} 篇候選文章。"
        ),
        (
            "- 每類文章不設篇數上限。"
            if effective_max_articles_per_category == 0
            else f"- 每類最多保留 {effective_max_articles_per_category} 篇文章。"
        ),
        f"- 網址去重範圍：{args.dedupe_scope}。",
        "- Bing News 索引優先以 RSS 展開，失敗時再解析搜尋頁 HTML。",
        "- 搜尋結果頁本身不會被存成訓練正文。",
        "- 每份成功 TXT 僅含清理後主文；類別由所在的 #T#[類別] 目錄表示。",
        "- 未繞過登入、付費牆、CAPTCHA、robots.txt 或網站封鎖。",
        "- 詳細原因請查看抓取結果.csv與索引展開結果.csv。",
    ]
    write_utf8(output_dir / "抓取摘要.txt", "\n".join(summary) + "\n")
    shutil.copy2(output_dir / "抓取摘要.txt", log_dir / "抓取摘要.txt")

    zip_output(output_dir, output_zip)
    print("\n完成")
    print(f"正文目錄：{output_dir}")
    print(f"正文壓縮包：{output_zip}")
    print(f"文章抓取紀錄：{results_csv}")
    print(f"索引展開紀錄：{index_results_csv}")
    return 0 if success else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已中止。已完成的檔案仍保留，可重新執行。", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n錯誤：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
