#!/usr/bin/env python3
"""
Web Search Plus — URL extraction with automatic provider fallback.
Supports: Firecrawl, Linkup, Tavily, Exa, You.com

Usage:
    python3 scripts/extract.py --url https://example.com
    python3 scripts/extract.py --url https://example.com --provider firecrawl --format markdown
    python3 scripts/extract.py --url https://example.com --url https://example.org --include-images
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EXTRACT_PROVIDER_PRIORITY = ["firecrawl", "linkup", "tavily", "exa", "you"]


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


def request_json(url: str, init: Dict[str, Any], timeout: int = 30) -> Any:
    body = init.get("body")
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = Request(url, data=data, method=init.get("method", "GET"))
    for key, value in (init.get("headers") or {}).items():
        req.add_header(key, value)
    try:
        with urlopen(req, timeout=max(1, timeout)) as response:
            text = response.read().decode("utf-8")
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
    env_map = {
        "firecrawl": "FIRECRAWL_API_KEY",
        "linkup": "LINKUP_API_KEY",
        "tavily": "TAVILY_API_KEY",
        "exa": "EXA_API_KEY",
        "you": "YOU_API_KEY",
    }
    return os.environ.get(env_map[provider])


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


def extract_plus(urls: List[str], provider: str = "auto", output_format: str = "markdown", include_images: bool = False, include_raw_html: bool = False, render_js: bool = False) -> Dict[str, Any]:
    requested_provider = provider or "auto"
    if not urls:
        return {"provider": requested_provider, "results": [], "error": "No URLs provided", "routing": {"requested_provider": requested_provider}}
    cleaned_urls = [url.strip() for url in urls if isinstance(url, str)]
    invalid_urls = [url for url in cleaned_urls if not url.startswith(("http://", "https://"))]
    if invalid_urls:
        return {"provider": requested_provider, "results": [], "error": f"Invalid URL(s) — must start with http:// or https://: {json.dumps(invalid_urls)}", "routing": {"requested_provider": requested_provider}}
    providers = EXTRACT_PROVIDER_PRIORITY if requested_provider == "auto" else [requested_provider] + [p for p in EXTRACT_PROVIDER_PRIORITY if p != requested_provider]
    errors = []
    for current_provider in providers:
        if current_provider not in EXTRACT_PROVIDER_PRIORITY:
            errors.append({"provider": current_provider, "error": f"Provider {current_provider} does not support extraction"})
            continue
        credential = get_extract_api_key(current_provider)
        if not credential:
            errors.append({"provider": current_provider, "error": "missing_api_key"})
            continue
        try:
            if current_provider == "firecrawl":
                result = extract_firecrawl(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            elif current_provider == "linkup":
                result = extract_linkup(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            elif current_provider == "tavily":
                result = extract_tavily(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            elif current_provider == "exa":
                result = extract_exa(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            else:
                result = extract_you(cleaned_urls, credential, output_format, include_images, include_raw_html, render_js)
            result_list = result.get("results") or []
            if result_list and all(item.get("error") for item in result_list):
                errors.append({"provider": current_provider, "error": "all_urls_failed", "details": [item.get("error") for item in result_list]})
                continue
            result["routing"] = {
                "provider": current_provider,
                "requested_provider": requested_provider,
                "fallback_used": bool(errors),
                "fallback_errors": errors,
            }
            return result
        except Exception as exc:
            errors.append({"provider": current_provider, "error": str(exc)})
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
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = extract_plus(args.urls or [], args.provider, args.format, args.include_images, args.include_raw_html, args.render_js)
    if args.compact:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
