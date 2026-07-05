#!/usr/bin/env python3
"""
Web Search Plus — URL extraction with automatic provider fallback.
Supports: Tavily, Exa, Linkup, Firecrawl, You.com, Keenable, Serper

Usage:
    python3 scripts/extract.py --url https://example.com
    python3 scripts/extract.py --url https://example.com --provider firecrawl --format markdown
    python3 scripts/extract.py --url https://example.com --url https://example.org --include-images
"""

import argparse
import gzip
import json
import os
import sys
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .url_security import validate_outbound_url
    from .provider_registry import redact_secrets
except ImportError:
    from url_security import validate_outbound_url
    from provider_registry import redact_secrets

import re

# Tavily-first for reliability (plugin v2.6+/v3 parity); keenable and serper
# join in last position so they never displace a configured keyed provider.
EXTRACT_PROVIDER_PRIORITY = ["tavily", "exa", "linkup", "firecrawl", "you", "keenable", "serper"]

# Opt-in for the keyless Keenable public tier (shared, ~1000 req/hour, no SLA).
KEENABLE_ALLOW_PUBLIC_ENV = "WSP_KEENABLE_ALLOW_PUBLIC"

# Inline extract budget: long pages return a head/tail window plus footer.
DEFAULT_EXTRACT_CHAR_LIMIT = 15000
EXTRACT_CHAR_LIMIT_ENV = "WSP_EXTRACT_CHAR_LIMIT"


def _load_env_file() -> None:
    env_paths = [Path(__file__).parent.parent / ".env", Path(__file__).parent / ".env"]
    for env_path in env_paths:
        if not env_path.exists():
            continue
        with open(env_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    if line.startswith("export "):
                        line = line[7:]
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value


_load_env_file()


def _response_header(response, name: str, default: str = "") -> str:
    """Get response header safely (works with HTTPError too)."""
    try:
        val = response.getheader(name) if hasattr(response, "getheader") else response.headers.get(name)
        return val or default
    except Exception:
        return default


def _read_response_body(response) -> bytes:
    """Read response body with gzip/deflate decompression support."""
    raw = response.read()
    encoding = _response_header(response, "Content-Encoding", "").lower().strip()

    if encoding in ("gzip", "x-gzip"):
        try:
            return gzip.decompress(raw)
        except Exception:
            if raw.startswith(b"\x1f\x8b"):
                return gzip.decompress(raw)
            return raw
    elif encoding == "deflate":
        try:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
        except zlib.error:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return raw
    elif encoding == "br":
        try:
            import brotli
            return brotli.decompress(raw)
        except ImportError:
            raise RuntimeError(
                "Brotli-encoded response received but brotli library not installed. Install with: pip install brotli"
            )
        except Exception:
            raise RuntimeError("Failed to decompress brotli-encoded response")

    return raw


def request_json(url: str, init: Dict[str, Any], timeout: int = 30) -> Any:
    body = init.get("body")
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = Request(url, data=data, method=init.get("method", "GET"))
    for key, value in (init.get("headers") or {}).items():
        req.add_header(key, value)
    try:
        with urlopen(req, timeout=max(1, timeout)) as response:
            text = _read_response_body(response).decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        try:
            data = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            data = {}
        message = data.get("error") or data.get("message") or data.get("detail") or data.get("warning") or f"HTTP {exc.code}"
        raise RuntimeError(str(message)) from exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def title_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        last_segment = [part for part in parsed.path.split("/") if part]
        return (last_segment[-1] if last_segment else parsed.hostname) or url
    except Exception:
        return url


def normalize_images(images: Any) -> Optional[List[Dict[str, str]]]:
    if not isinstance(images, list):
        return None
    normalized = []
    for image in images:
        if not image:
            continue
        if isinstance(image, str):
            normalized.append({"url": image})
        elif isinstance(image, dict) and isinstance(image.get("url"), str) and image.get("url"):
            item = {"url": image["url"]}
            if isinstance(image.get("alt"), str) and image.get("alt"):
                item["alt"] = image["alt"]
            normalized.append(item)
    return normalized or None


def normalize_result(provider: str, url: str, title: str = "", content: str = "", raw_content: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    result = {
        "url": url,
        "title": title or title_from_url(url),
        "content": content or "",
        "raw_content": raw_content if raw_content is not None else content or "",
        "provider": provider,
    }
    for key, value in extra.items():
        if value is not None:
            result[key] = value
    return result


def get_extract_api_key(provider: str) -> Optional[str]:
    try:
        from .provider_registry import PROVIDER_SPECS
    except ImportError:
        from provider_registry import PROVIDER_SPECS
    return os.environ.get(PROVIDER_SPECS[provider].env_var)


def keenable_public_allowed() -> bool:
    """True when the operator opted in to Keenable's keyless public tier."""
    return os.environ.get(KEENABLE_ALLOW_PUBLIC_ENV, "").strip() == "1"


def extract_char_limit() -> int:
    """Inline extract budget (chars); WSP_EXTRACT_CHAR_LIMIT overrides."""
    raw = os.environ.get(EXTRACT_CHAR_LIMIT_ENV, "").strip()
    try:
        value = int(raw) if raw else DEFAULT_EXTRACT_CHAR_LIMIT
    except ValueError:
        return DEFAULT_EXTRACT_CHAR_LIMIT
    return value if value > 0 else DEFAULT_EXTRACT_CHAR_LIMIT


# --- Truncate-and-sanitize output handling (plugin/hermes v2.8 parity) -------
# Long pages return a head/tail window plus an explanatory footer instead of
# unbounded inline content. Inline base64 image data is replaced with
# [IMAGE: alt] placeholders before measuring content, preventing data-URI
# token bombs while preserving normal http(s) image links.

_BASE64_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*data:image/[^)]+\)", re.IGNORECASE)
_BASE64_HTML_IMAGE_RE = re.compile(r"<img\b(?=[^>]*\bsrc=[\"']data:image/)[^>]*>", re.IGNORECASE)
_HTML_ALT_RE = re.compile(r"\balt=[\"']([^\"']*)[\"']", re.IGNORECASE)


def sanitize_extract_content(content: str) -> str:
    def _md_repl(match):
        alt = (match.group(1) or "image").strip() or "image"
        return f"[IMAGE: {alt}]"

    def _html_repl(match):
        alt_match = _HTML_ALT_RE.search(match.group(0))
        alt = ((alt_match.group(1) if alt_match else "") or "image").strip() or "image"
        return f"[IMAGE: {alt}]"

    out = _BASE64_MARKDOWN_IMAGE_RE.sub(_md_repl, content)
    return _BASE64_HTML_IMAGE_RE.sub(_html_repl, out)


def _split_extract_content(content: str, limit: int):
    head_chars = min(max(1, (limit * 2) // 3), max(1, limit - 1))
    tail_chars = min(max(1, limit // 5), max(1, limit - head_chars))
    if head_chars + tail_chars >= len(content):
        return content, "", 0
    head = content[:head_chars].rstrip()
    tail = content[-tail_chars:].lstrip()
    return head, tail, max(0, len(content) - len(head) - len(tail))


def format_truncated_extract_content(content: str, limit: int) -> Dict[str, Any]:
    """Return inline-safe extract content: sanitized, and truncated to a
    head/tail window when it exceeds the limit."""
    cleaned = sanitize_extract_content(content)
    if len(cleaned) <= limit:
        return {"content": cleaned, "truncated": False, "original_chars": len(cleaned)}
    head, tail, omitted = _split_extract_content(cleaned, limit)
    footer = "\n".join([
        "",
        "---",
        f"[Content truncated: original {len(cleaned)} chars; omitted middle {omitted} chars; showing head and tail.]",
        f"Raise {EXTRACT_CHAR_LIMIT_ENV} (or --extract-char-limit) for a larger inline budget, or extract a more specific URL for the omitted section.",
    ])
    return {
        "content": f"{head}\n\n[... omitted middle ...]\n\n{tail}\n{footer}",
        "truncated": True,
        "original_chars": len(cleaned),
    }


def _keenable_endpoint(api_url: str, api_key: Optional[str], public_allowed: bool):
    """A present key always uses the authenticated route; with no key, the
    keyless /public route is used when the public tier is enabled."""
    headers = {"X-Keenable-Title": "web-search-plus"}
    if api_key:
        headers["X-API-Key"] = api_key
        return api_url, headers
    if public_allowed:
        return f"{api_url}/public", headers
    raise ValueError("Keenable requires an API key or an enabled public endpoint")


def extract_keenable(urls: List[str], api_key: Optional[str], output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False, public_allowed: bool = False, api_url: str = "https://api.keenable.ai/v1/fetch", timeout: int = 30) -> Dict[str, Any]:
    del output_format, include_images, include_raw_html, render_js
    from urllib.parse import quote
    endpoint, headers = _keenable_endpoint(api_url, api_key, public_allowed)
    results = []
    for url in urls:
        try:
            data = request_json(f"{endpoint}?url={quote(url, safe='')}", {"method": "GET", "headers": headers}, timeout)
            content = str((data or {}).get("content") or "")
            metadata = {}
            if (data or {}).get("author") is not None:
                metadata["author"] = data["author"]
            if (data or {}).get("description") is not None:
                metadata["description"] = data["description"]
            results.append(normalize_result("keenable", str((data or {}).get("url") or url), str((data or {}).get("title") or ""), content, content, metadata=metadata or None))
        except Exception as exc:
            results.append(normalize_result("keenable", url, "", "", None, error=str(exc)))
    return {"provider": "keenable", "results": results}


def extract_serper(urls: List[str], api_key: str, output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False, api_url: str = "https://scrape.serper.dev", timeout: int = 30) -> Dict[str, Any]:
    """Extract page content via Serper's webpage scraper.

    POST {"url": ..., "includeMarkdown": true} with the X-API-KEY header; the
    answer carries "text" plus optional "markdown", "metadata", "jsonld" and
    "credits". The endpoint accepts one URL per call, so multi-URL requests
    loop with per-URL error items. The scraper returns no raw HTML;
    html/raw-html/render-js options are accepted for CLI compatibility but
    have no upstream effect.
    """
    del output_format, include_images, include_raw_html, render_js
    results = []
    for url in urls:
        try:
            data = request_json(api_url, {
                "method": "POST",
                "headers": {"X-API-KEY": api_key, "Content-Type": "application/json"},
                "body": json.dumps({"url": url, "includeMarkdown": True}),
            }, timeout)
            if isinstance(data, dict) and data.get("error"):
                results.append(normalize_result("serper", url, "", "", None, error=str(data["error"])))
                continue
            data = data if isinstance(data, dict) else {}
            # Field names are parsed tolerantly in case Serper renames them.
            markdown = str(data.get("markdown") or "")
            text = str(data.get("text") or data.get("content") or "")
            content = markdown or text
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            title = str(metadata.get("title") or data.get("title") or "")
            extra = {"metadata": metadata or None}
            if data.get("jsonld") is not None:
                extra["jsonld"] = data["jsonld"]
            if data.get("credits") is not None:
                extra["credits"] = data["credits"]
            results.append(normalize_result("serper", url, title, content, content, **extra))
        except Exception as exc:
            results.append(normalize_result("serper", url, "", "", None, error=str(exc)))
    return {"provider": "serper", "results": results}


def extract_firecrawl(urls: List[str], api_key: str, output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False, api_url: str = "https://api.firecrawl.dev/v2/scrape", timeout: int = 60) -> Dict[str, Any]:
    formats = ["html"] if output_format == "html" else ["markdown"]
    if include_raw_html and "html" not in formats:
        formats.append("html")
    results = []
    for url in urls:
        try:
            body: Dict[str, Any] = {"url": url, "formats": formats}
            if render_js:
                body["waitFor"] = 1000
            data = request_json(api_url, {
                "method": "POST",
                "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                "body": json.dumps(body),
            }, timeout)
            if data.get("success") is False:
                results.append(normalize_result("firecrawl", url, error=str(data.get("error") or data.get("warning") or "Firecrawl scrape failed")))
                continue
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            final_url = metadata.get("sourceURL") or metadata.get("url") or url
            title = metadata.get("title") or ""
            markdown = str(payload.get("markdown") or "")
            html = str(payload.get("html") or payload.get("rawHtml") or "")
            content = html if output_format == "html" else (markdown or html)
            images = None
            if include_images:
                seen = set()
                parsed = []
                og_image = metadata.get("ogImage") or metadata.get("og:image")
                if isinstance(og_image, str) and og_image and og_image not in seen:
                    parsed.append({"alt": "og:image", "url": og_image})
                    seen.add(og_image)
                import re
                for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', markdown):
                    image_url = match.group(2)
                    if image_url and image_url not in seen:
                        item = {"url": image_url}
                        if match.group(1):
                            item["alt"] = match.group(1)
                        parsed.append(item)
                        seen.add(image_url)
                images = parsed or None
            results.append(normalize_result("firecrawl", final_url, title, content, content, raw_html=html or None, images=images, metadata=metadata or None))
        except Exception as exc:
            results.append(normalize_result("firecrawl", url, error=str(exc)))
    return {"provider": "firecrawl", "results": results}


def extract_linkup(urls: List[str], api_key: str, output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False, api_url: str = "https://api.linkup.so/v1/fetch", timeout: int = 30) -> Dict[str, Any]:
    results = []
    for url in urls:
        try:
            data = request_json(api_url, {
                "method": "POST",
                "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                "body": json.dumps({
                    "url": url,
                    "extractImages": include_images,
                    "includeRawHtml": include_raw_html or output_format == "html",
                    "renderJs": render_js,
                }),
            }, timeout)
            if data.get("error"):
                results.append(normalize_result("linkup", url, error=str(data["error"])))
                continue
            markdown = str(data.get("markdown") or "")
            raw_html = str(data.get("rawHtml") or data.get("raw_html") or "")
            content = raw_html if output_format == "html" else (markdown or raw_html)
            results.append(normalize_result("linkup", url, content=content, raw_content=content, raw_html=raw_html or None, images=normalize_images(data.get("images")) if include_images else None, metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None))
        except Exception as exc:
            results.append(normalize_result("linkup", url, error=str(exc)))
    return {"provider": "linkup", "results": results}


def extract_tavily(urls: List[str], api_key: str, output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False, api_url: str = "https://api.tavily.com/extract", timeout: int = 30) -> Dict[str, Any]:
    del output_format, include_raw_html, render_js
    data = request_json(api_url, {
        "method": "POST",
        "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        "body": json.dumps({"urls": urls, "include_images": include_images}),
    }, timeout)
    results = []
    for item in data.get("results") or []:
        content = str(item.get("raw_content") or item.get("content") or "")
        results.append(normalize_result("tavily", str(item.get("url") or ""), str(item.get("title") or ""), content, content, images=normalize_images(item.get("images")) if include_images else None, metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None))
    for failed in data.get("failed_results") or []:
        results.append(normalize_result("tavily", str(failed.get("url") or ""), error=str(failed.get("error") or "Tavily extract failed")))
    return {"provider": "tavily", "results": results}


def extract_exa(urls: List[str], api_key: str, output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False, api_url: str = "https://api.exa.ai/contents", timeout: int = 30) -> Dict[str, Any]:
    del output_format, include_raw_html, render_js
    data = request_json(api_url, {
        "method": "POST",
        "headers": {"x-api-key": api_key, "Content-Type": "application/json"},
        "body": json.dumps({"urls": urls, "text": True}),
    }, timeout)
    results = []
    for item in data.get("results") or []:
        url = str(item.get("url") or item.get("id") or "")
        content = str(item.get("text") or item.get("summary") or "")
        metadata = {}
        for src, dest in [("summary", "summary"), ("highlights", "highlights"), ("publishedDate", "published_date"), ("author", "author"), ("favicon", "favicon")]:
            if item.get(src) is not None:
                metadata[dest] = item.get(src)
        images = [{"alt": "image", "url": str(item.get("image"))}] if include_images and item.get("image") else None
        results.append(normalize_result("exa", url, str(item.get("title") or ""), content, content, images=images, metadata=metadata or None))
    return {"provider": "exa", "results": results}


def extract_you(urls: List[str], api_key: str, output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False, api_url: str = "https://ydc-index.io/v1/contents", timeout: int = 30) -> Dict[str, Any]:
    del include_images, render_js
    formats = ["html"] if output_format == "html" else ["markdown"]
    if include_raw_html and "html" not in formats:
        formats.append("html")
    if "metadata" not in formats:
        formats.append("metadata")
    data = request_json(api_url, {
        "method": "POST",
        "headers": {"X-API-Key": api_key, "Content-Type": "application/json"},
        "body": json.dumps({"urls": urls, "formats": formats, "crawl_timeout": max(1, min(timeout, 60))}),
    }, timeout)
    raw_items = data if isinstance(data, list) else data.get("results") or data.get("data") or []
    results = []
    for item in raw_items:
        url = str(item.get("url") or "")
        markdown = str(item.get("markdown") or "")
        html = str(item.get("html") or "")
        content = html if output_format == "html" else (markdown or html)
        results.append(normalize_result("you", url, str(item.get("title") or ""), content, content, raw_html=html or None, metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None))
    return {"provider": "you", "results": results}


def extract_plus(urls: List[str], provider: str = "auto", output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False, allow_private: bool = False, char_limit: Optional[int] = None) -> Dict[str, Any]:
    requested_provider = provider or "auto"
    if not urls:
        return {"provider": requested_provider, "results": [], "error": "No URLs provided", "routing": {"requested_provider": requested_provider}}
    cleaned_urls = [url.strip() for url in urls if isinstance(url, str)]
    invalid_urls = [url for url in cleaned_urls if not url.startswith(("http://", "https://"))]
    if invalid_urls:
        return {"provider": requested_provider, "results": [], "error": f"Invalid URL(s) — must start with http:// or https://: {json.dumps(invalid_urls)}", "routing": {"requested_provider": requested_provider}}
    # SSRF guard: block private/loopback/link-local targets and cloud metadata
    # endpoints before any URL is fetched or forwarded to an extraction provider.
    # Opt out for trusted private networks via --allow-private-urls or
    # WSP_ALLOW_PRIVATE_URLS=1 (metadata endpoints stay blocked).
    blocked_urls = []
    for url in cleaned_urls:
        try:
            validate_outbound_url(url, allow_private=allow_private, label="Extraction URL")
        except ValueError as exc:
            blocked_urls.append(str(exc))
    if blocked_urls:
        return {"provider": requested_provider, "results": [], "error": "; ".join(blocked_urls), "routing": {"requested_provider": requested_provider}}
    providers = EXTRACT_PROVIDER_PRIORITY if requested_provider == "auto" else [requested_provider] + [p for p in EXTRACT_PROVIDER_PRIORITY if p != requested_provider]
    errors = []
    for current_provider in providers:
        if current_provider not in EXTRACT_PROVIDER_PRIORITY:
            errors.append({"provider": current_provider, "error": f"Provider {current_provider} does not support extraction"})
            continue
        credential = get_extract_api_key(current_provider)
        keyless_allowed = current_provider == "keenable" and keenable_public_allowed()
        if not credential and not keyless_allowed:
            errors.append({"provider": current_provider, "error": "missing_api_key"})
            continue
        try:
            if current_provider == "tavily":
                result = extract_tavily(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            elif current_provider == "exa":
                result = extract_exa(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            elif current_provider == "linkup":
                result = extract_linkup(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            elif current_provider == "firecrawl":
                result = extract_firecrawl(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            elif current_provider == "keenable":
                result = extract_keenable(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js, public_allowed=keyless_allowed)
            elif current_provider == "serper":
                result = extract_serper(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            else:
                result = extract_you(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            result_list = result.get("results") or []
            # Never surface credentials, even if a provider echoes one back in an error.
            for item in result_list:
                if item.get("error"):
                    item["error"] = redact_secrets(str(item["error"]))
            if result_list and all(item.get("error") for item in result_list):
                errors.append({"provider": current_provider, "error": "all_urls_failed", "details": [item.get("error") for item in result_list]})
                continue
            # Inline budget: sanitize base64 image data and truncate oversized
            # pages to a head/tail window (plugin/hermes v2.8 parity).
            limit = char_limit if char_limit and char_limit > 0 else extract_char_limit()
            for item in result_list:
                if item.get("error"):
                    continue
                original_content = item.get("content")
                if item.get("content"):
                    formatted = format_truncated_extract_content(item["content"], limit)
                    item["content"] = formatted["content"]
                    if formatted["truncated"]:
                        item["truncated"] = True
                        item["original_chars"] = formatted["original_chars"]
                if item.get("raw_content"):
                    item["raw_content"] = item["content"] if item["raw_content"] == original_content else format_truncated_extract_content(item["raw_content"], limit)["content"]
            result["routing"] = {
                "provider": current_provider,
                "requested_provider": requested_provider,
                "fallback_used": bool(errors),
                "fallback_errors": errors,
            }
            return result
        except Exception as exc:
            errors.append({"provider": current_provider, "error": redact_secrets(str(exc))})
    return {
        "provider": requested_provider,
        "results": [],
        "error": "All extraction providers failed",
        "fallback_errors": errors,
        "routing": {"requested_provider": requested_provider, "fallback_used": bool(errors), "fallback_errors": errors},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract URL content with automatic provider fallback")
    parser.add_argument("--url", dest="urls", action="append", help="URL to extract (repeatable)")
    parser.add_argument("--provider", default="auto", choices=["auto"] + EXTRACT_PROVIDER_PRIORITY)
    parser.add_argument("--format", default="markdown", choices=["markdown", "html"])
    parser.add_argument("--include-images", action="store_true")
    parser.add_argument("--include-raw-html", action="store_true")
    parser.add_argument("--render-js", action="store_true")
    parser.add_argument("--allow-private-urls", action="store_true", help="Allow URLs that resolve to private/internal networks (off by default; see WSP_ALLOW_PRIVATE_URLS)")
    parser.add_argument("--extract-char-limit", type=int, help=f"Inline content budget per URL in characters (default {DEFAULT_EXTRACT_CHAR_LIMIT}; oversized pages return a head/tail window). Set {EXTRACT_CHAR_LIMIT_ENV} to change the default.")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = extract_plus(args.urls or [], args.provider, args.format, args.include_images, args.include_raw_html, args.render_js, allow_private=args.allow_private_urls, char_limit=args.extract_char_limit)
    if args.compact:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
