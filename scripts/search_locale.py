"""Config-first search locale resolution with query-aware language inference.

Port of the plugin/hermes v2.9 search-locale module, adapted to this skill's
CLI + config.json + env-var surface.

Providers with country/language request parameters used to receive hardcoded
us/en defaults. Resolution is now centralized here:

- Country precedence: explicit ``--country`` CLI value > explicit location
  hint in the query (curated city/country table) > config/env
  (``locale.country`` in config.json or ``WSP_LOCALE_COUNTRY``) > "us".
- Language precedence: explicit ``--language`` CLI value > config/env
  (``locale.language`` / ``WSP_LOCALE_LANGUAGE``; the value "auto" enables
  conservative query language inference) > "en".

Query language never implies a country: a German query may come from Austria
or Switzerland just as well as Germany, so only explicit location hints, CLI
flags, or configuration move the region.
"""

import os
import re
from typing import Any, Dict, Optional

FALLBACK_COUNTRY = "us"
FALLBACK_LANGUAGE = "en"

# locale.language value that enables query language inference.
AUTO_LANGUAGE = "auto"

LOCALE_COUNTRY_ENV = "WSP_LOCALE_COUNTRY"
LOCALE_LANGUAGE_ENV = "WSP_LOCALE_LANGUAGE"

# Providers whose request carries country and/or language parameters. SerpBase
# takes no locale parameters, so it is absent here.
LOCALE_PROVIDERS = {"serper", "brave", "querit", "firecrawl", "you", "searxng"}

# Small curated table of unambiguous location hints. Only well-known city and
# country names are listed; generic example queries such as
# "mejores restaurantes Madrid" resolve to the matching country.
# Deliberately small: unknown places simply do not hint.
LOCATION_COUNTRY_HINTS: Dict[str, str] = {
    # Austria
    "wien": "at", "vienna": "at", "graz": "at", "salzburg": "at",
    "innsbruck": "at", "österreich": "at", "austria": "at",
    # Germany
    "berlin": "de", "münchen": "de", "munich": "de", "hamburg": "de",
    "frankfurt": "de", "deutschland": "de", "germany": "de",
    # Switzerland
    "zürich": "ch", "zurich": "ch", "schweiz": "ch", "switzerland": "ch",
    # France
    "paris": "fr", "lyon": "fr", "marseille": "fr", "france": "fr",
    # Spain
    "madrid": "es", "barcelona": "es", "españa": "es", "spain": "es",
    # Italy
    "rome": "it", "roma": "it", "milano": "it", "milan": "it", "italia": "it", "italy": "it",
    # Portugal
    "lisbon": "pt", "lisboa": "pt", "portugal": "pt",
    # Netherlands
    "amsterdam": "nl", "rotterdam": "nl", "netherlands": "nl",
    # United Kingdom
    "london": "gb", "manchester": "gb", "united kingdom": "gb",
    # United States
    "new york": "us", "chicago": "us", "san francisco": "us", "usa": "us",
}

# Minimum number of distinct signals before a language inference is trusted.
LANGUAGE_INFERENCE_MIN_MATCHES = 2

# Common function/search words per supported language. Words shared between
# languages (e.g. "que" in es/fr/pt) may appear in several sets; the strict
# single-winner rule in infer_query_language keeps those from mis-firing.
LANGUAGE_INFERENCE_STOPWORDS: Dict[str, set] = {
    "en": {"the", "and", "what", "how", "where", "when", "which", "who", "best", "near", "hours", "open", "with", "from", "for", "are", "is", "was", "does", "latest", "today", "new"},
    "de": {"der", "die", "das", "und", "oder", "nicht", "ist", "sind", "ein", "eine", "einen", "mit", "für", "von", "wie", "wo", "was", "warum", "welche", "beste", "besten", "gibt", "öffnungszeiten", "heute", "morgen", "preis", "kaufen", "günstig", "nähe"},
    "es": {"el", "los", "las", "una", "unos", "que", "qué", "cómo", "dónde", "cuál", "por", "para", "con", "mejores", "mejor", "cerca", "hoy", "horario", "horarios", "abierto", "abiertos", "tiendas", "restaurantes", "precio", "precios", "donde", "como"},
    "fr": {"le", "les", "des", "une", "du", "où", "quel", "quelle", "quels", "quelles", "meilleur", "meilleure", "meilleurs", "meilleures", "horaires", "ouvert", "ouverts", "ouverture", "aujourd", "hui", "près", "proche", "avec", "pour", "prix", "cher", "que"},
    "it": {"il", "lo", "gli", "che", "come", "dove", "quale", "quali", "migliori", "migliore", "orari", "orario", "aperto", "aperti", "vicino", "con", "oggi", "prezzo", "prezzi", "negozi", "ristoranti", "della", "delle"},
    "pt": {"os", "do", "dos", "das", "um", "uma", "que", "como", "onde", "qual", "quais", "melhores", "melhor", "horários", "aberto", "perto", "hoje", "preço", "lojas", "com", "você", "para", "restaurantes"},
    "nl": {"het", "een", "waar", "hoe", "welke", "beste", "goedkoop", "goedkoopste", "vandaag", "morgen", "openingstijden", "winkel", "winkels", "dichtbij", "buurt", "naar", "zijn", "niet", "voor"},
}

# Distinctive characters that count as one additional signal per language.
LANGUAGE_INFERENCE_CHAR_HINTS: Dict[str, str] = {
    "de": "äöüß",
    "es": "ñ¿¡",
    "pt": "ãõ",
    "fr": "œ",
}

_WORD_RE = re.compile(r"[^\W]+", re.UNICODE)


def provider_supports_locale(provider: str) -> bool:
    return provider in LOCALE_PROVIDERS


def detect_location_country(query: Optional[str]) -> Optional[str]:
    """Return the ISO 3166-1 alpha-2 country for an explicit location hint.

    Only returns a country when every hint in the query agrees on a single
    country; conflicting hints (e.g. a "Paris vs Madrid" comparison) resolve to
    None so configuration keeps deciding.
    """
    if not query:
        return None
    lowered = query.lower()
    countries = set()
    for place, country in LOCATION_COUNTRY_HINTS.items():
        if re.search(rf"(^|[^\w]){re.escape(place)}($|[^\w])", lowered, re.UNICODE):
            countries.add(country)
    return next(iter(countries)) if len(countries) == 1 else None


def infer_query_language(query: str) -> Optional[str]:
    """Infer the query language conservatively for locale defaults.

    Returns an ISO 639-1 code when at least LANGUAGE_INFERENCE_MIN_MATCHES
    distinct signals point to a single language that strictly beats every
    other candidate. Returns None when the evidence is missing or ambiguous so
    callers fall back to their configured default (for example
    "Wiener Kaffeehaus Öffnungszeiten" infers "de", while a terse technical
    query such as "DAC R2R NOS" infers nothing).
    """
    if not query:
        return None
    lowered = query.lower()
    words = set(_WORD_RE.findall(lowered))
    counts: Dict[str, int] = {}
    for language, stopwords in LANGUAGE_INFERENCE_STOPWORDS.items():
        count = len(words & stopwords)
        for char in LANGUAGE_INFERENCE_CHAR_HINTS.get(language, ""):
            if char in lowered:
                count += 1
        if count:
            counts[language] = count
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    best_language, best_count = ranked[0]
    if best_count < LANGUAGE_INFERENCE_MIN_MATCHES:
        return None
    if len(ranked) > 1 and ranked[1][1] == best_count:
        return None
    return best_language


def _configured_locale_value(config: Dict[str, Any], key: str, env_var: str) -> str:
    locale_config = (config or {}).get("locale", {})
    value = ""
    if isinstance(locale_config, dict):
        value = str(locale_config.get(key) or "").strip().lower()
    if not value:
        value = str(os.environ.get(env_var) or "").strip().lower()
    return value


def resolve_locale(
    provider: str,
    config: Dict[str, Any],
    query: Optional[str] = None,
    cli_country: Optional[str] = None,
    cli_language: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve (country, language, metadata) for a provider request.

    Precedence:
      country:  explicit CLI flag > location hint in query > config/env > "us"
      language: explicit CLI flag > config/env ("auto" enables conservative
                query inference) > "en"

    The metadata dict follows the freshness/search_type reporting pattern.
    Country codes are normalized to lowercase; providers that need uppercase
    upper-case them in their own request builders.
    """
    configured_country = _configured_locale_value(config, "country", LOCALE_COUNTRY_ENV)
    configured_language = _configured_locale_value(config, "language", LOCALE_LANGUAGE_ENV)

    hinted = detect_location_country(query)
    if cli_country:
        country, country_source = str(cli_country).strip().lower(), "cli"
    elif hinted:
        country, country_source = hinted, "hint"
    elif configured_country:
        country, country_source = configured_country, "config"
    else:
        country, country_source = FALLBACK_COUNTRY, "fallback"

    auto_language = configured_language == AUTO_LANGUAGE
    if cli_language:
        language, language_source = str(cli_language).strip().lower(), "cli"
    elif configured_language and not auto_language:
        language, language_source = configured_language, "config"
    else:
        inferred = infer_query_language(query or "") if auto_language else None
        if inferred:
            language, language_source = inferred, "inferred"
        else:
            language, language_source = FALLBACK_LANGUAGE, "fallback"

    return {
        "country": country,
        "language": language,
        "metadata": {
            "country": country,
            "language": language,
            "source": {"country": country_source, "language": language_source},
        },
    }
