import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import search  # noqa: E402


class SerpBaseEndpointTests(unittest.TestCase):
    def test_serpbase_uses_dev_endpoint_post_body_and_api_key_header(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps({
                    "status": 0,
                    "organic": [{"title": "Result", "link": "https://example.com", "snippet": "ok"}],
                }).encode("utf-8")

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["headers"] = dict(req.header_items())
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse()

        with mock.patch.object(search, "urlopen", fake_urlopen):
            result = search.search_serpbase("openai", "serpbase-test-key", max_results=1)

        self.assertEqual(captured["url"], "https://api.serpbase.dev/google/search")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["headers"].get("X-api-key"), "serpbase-test-key")
        self.assertEqual(captured["headers"].get("Content-type"), "application/json")
        self.assertEqual(captured["body"], {"q": "openai", "page": 1})
        self.assertEqual(result["provider"], "serpbase")
        self.assertEqual(result["results"][0]["title"], "Result")


if __name__ == "__main__":
    unittest.main()
