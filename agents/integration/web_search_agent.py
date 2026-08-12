from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from groq import Groq

from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


DUCKDUCKGO_API_URL = "https://api.duckduckgo.com/"
OPENAI_STATUS_API_URL = "https://status.openai.com/api/v2/status.json"
GROQ_MODELS_URL = "https://console.groq.com/docs/models"
REQUEST_TIMEOUT = 10

CAPABILITY_MODE = "hybrid"
TRUST_LEVEL = "safe"
AGENT_NAME = "web_search"

MAX_RELATED_TOPICS = 5
MAX_EXTRACTED_CHARS = 4000
MAX_PARAGRAPHS_FALLBACK = 20
MIN_BLOCK_LENGTH = 200
MIN_PARAGRAPH_LENGTH = 40
SUMMARY_MAX_SENTENCES = 4
SUMMARY_MAX_TOKENS = 500
MAX_QUERY_LENGTH = 300

ALLOWED_SCHEMES = {"http", "https"}
INVALID_HOST_CHARS = {" ", "@", "\t", "\n", "\r"}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ERROR_EMPTY_QUERY = "MISSING_QUERY"
ERROR_EMPTY_URL = "MISSING_URL"
ERROR_INVALID_URL = "INVALID_URL"
ERROR_TIMEOUT = "TIMEOUT"
ERROR_NETWORK = "NETWORK_ERROR"
ERROR_INVALID_RESPONSE = "INVALID_RESPONSE"
ERROR_NO_RESULTS = "NO_RESULTS"
ERROR_NO_CONTENT = "NO_READABLE_CONTENT"
ERROR_EMPTY_SUMMARY = "EMPTY_SUMMARY"
ERROR_INVALID_CONTENT = "INVALID_CONTENT"
ERROR_UNEXPECTED = "UNEXPECTED_ERROR"

SEARCH_ACTION = "web_search"
SUMMARY_ACTION = "summarize_website"

SEARCH_SOURCE = "duckduckgo_instant_answer"
OPENAI_STATUS_SOURCE = "official_openai_status"
GROQ_MODELS_SOURCE = "official_groq_models"
WEBSITE_FETCH_SOURCE = "website_fetch"
LLM_SUMMARY_SOURCE = "llm_summary"
FALLBACK_SUMMARY_SOURCE = "extractive_fallback"


@dataclass
class AgentResult:
    success: bool
    action: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None
    source: str = "live_search"
    live_data: bool = False
    mode: str = CAPABILITY_MODE
    agent: str = AGENT_NAME
    trust_level: str = TRUST_LEVEL

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchPayload:
    query: str
    heading: str = ""
    abstract: str = ""
    related_topics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SummaryPayload:
    url: str
    title: str = ""
    extracted_text: str = ""
    summary: str = ""
    summary_source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResultItem:
    heading: str = ""
    abstract: str = ""
    related_topics: List[str] = field(default_factory=list)


@dataclass
class SummaryResult:
    summary: str
    source: str
    llm_error: Optional[str] = None


class WebSearchError(Exception):
    error_code = ERROR_UNEXPECTED

    def __init__(self, message: str, *, user_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class MissingQueryError(WebSearchError):
    error_code = ERROR_EMPTY_QUERY


class MissingUrlError(WebSearchError):
    error_code = ERROR_EMPTY_URL


class InvalidUrlError(WebSearchError):
    error_code = ERROR_INVALID_URL


class InvalidResponseError(WebSearchError):
    error_code = ERROR_INVALID_RESPONSE


class NoResultsError(WebSearchError):
    error_code = ERROR_NO_RESULTS


class NoReadableContentError(WebSearchError):
    error_code = ERROR_NO_CONTENT


class EmptySummaryError(WebSearchError):
    error_code = ERROR_EMPTY_SUMMARY


class InvalidContentError(WebSearchError):
    error_code = ERROR_INVALID_CONTENT


class MemoryStore(Protocol):
    def __call__(self, label: str, metadata: Dict[str, Any]) -> None: ...


def safe_error_text(error: Exception) -> str:
    text = str(error).strip()
    return text if text else error.__class__.__name__


def maybe_create_groq_client() -> Optional[Groq]:
    try:
        if not GROQ_API_KEY:
            return None
        return Groq(api_key=GROQ_API_KEY)
    except Exception:
        return None


class TextCleaner:
    @staticmethod
    def is_meaningful(value: Any) -> bool:
        if value is None:
            return False

        text = str(value).strip()
        if not text:
            return False

        cleaned = text.strip(" \n\t.,!?;:-_")
        return bool(cleaned)

    @staticmethod
    def clean_general(text: Any) -> str:
        if not TextCleaner.is_meaningful(text):
            return ""

        value = str(text)
        value = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", value)
        value = re.sub(r"#{1,6}\s*", "", value)
        value = re.sub(r"`{3}[\w-]*\n?", "", value)
        value = re.sub(r"`(.+?)`", r"\1", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    @staticmethod
    def clean_query(query: Any) -> str:
        text = TextCleaner.clean_general(query)
        if not text:
            return ""

        patterns = [
            r"^(search for|search|look up|find information about|find|google)\s+",
            r"^(can you\s+)?(please\s+)?",
            r"^(tell me about)\s+",
        ]

        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        text = re.sub(r"\s+", " ", text).strip(" ,.?")
        return text[:MAX_QUERY_LENGTH]

    @staticmethod
    def clean_extracted_text(text: Any) -> str:
        if not TextCleaner.is_meaningful(text):
            return ""

        value = str(text)
        value = re.sub(r"\r\n?", "\n", value)
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

    @staticmethod
    def dedupe_preserve_order(items: Iterable[str]) -> List[str]:
        seen = set()
        result: List[str] = []

        for item in items:
            normalized = TextCleaner.clean_general(item)
            if not normalized:
                continue

            key = normalized.casefold()
            if key in seen:
                continue

            seen.add(key)
            result.append(normalized)

        return result


class UrlNormalizer:
    @staticmethod
    def _sanitize_netloc(netloc: str) -> str:
        return netloc.strip().rstrip(".").lower()

    @classmethod
    def normalize(cls, url: str) -> str:
        raw = TextCleaner.clean_general(url)
        if not raw:
            raise MissingUrlError(
                "Missing URL.",
                user_message="Please provide a website URL.",
            )

        if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
            raw = f"https://{raw}"

        parsed = urlparse(raw)
        scheme = parsed.scheme.lower()
        netloc = cls._sanitize_netloc(parsed.netloc)

        if scheme not in ALLOWED_SCHEMES:
            raise InvalidUrlError(
                "Only HTTP and HTTPS URLs are allowed.",
                user_message="Please provide a valid website URL.",
            )

        if not netloc:
            raise InvalidUrlError(
                "Invalid URL: missing domain.",
                user_message="Please provide a valid website URL.",
            )

        if any(char in netloc for char in INVALID_HOST_CHARS):
            raise InvalidUrlError(
                "Invalid URL: malformed domain.",
                user_message="Please provide a valid website URL.",
            )

        if "." not in netloc and netloc != "localhost":
            raise InvalidUrlError(
                "Invalid URL: domain appears incomplete.",
                user_message="Please provide a valid website URL.",
            )

        normalized = parsed._replace(
            scheme=scheme,
            netloc=netloc,
            fragment="",
        )
        return urlunparse(normalized)


class SessionFactory:
    @staticmethod
    def create() -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        return session


class WebSearchClient:
    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        timeout: int = REQUEST_TIMEOUT,
    ) -> None:
        self.session = session or SessionFactory.create()
        self.timeout = timeout

    def fetch_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as error:
            raise InvalidResponseError(
                "Invalid JSON response format.",
                user_message="The search service returned invalid data.",
            ) from error

        if not isinstance(payload, dict):
            raise InvalidResponseError(
                "Invalid JSON response format.",
                user_message="The search service returned invalid data.",
            )

        return payload

    def fetch_html(self, url: str) -> requests.Response:
        response = self.session.get(
            url,
            timeout=self.timeout,
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type:
            raise InvalidContentError(
                "URL did not return an HTML page.",
                user_message="The website could not be processed.",
            )

        return response

    def close(self) -> None:
        self.session.close()


class SearchResponseParser:
    @staticmethod
    def _add_topic_if_valid(collected: List[str], text: Any) -> None:
        cleaned = TextCleaner.clean_general(text)
        if TextCleaner.is_meaningful(cleaned):
            collected.append(cleaned)

    def extract_related_topics(
        self,
        related_topics: List[Any],
        limit: int = MAX_RELATED_TOPICS,
    ) -> List[str]:
        collected: List[str] = []

        for item in related_topics:
            if len(collected) >= limit:
                break

            if not isinstance(item, dict):
                continue

            self._add_topic_if_valid(collected, item.get("Text"))

            subtopics = item.get("Topics")
            if isinstance(subtopics, list):
                for sub in subtopics:
                    if isinstance(sub, dict):
                        self._add_topic_if_valid(collected, sub.get("Text"))
                    if len(collected) >= limit:
                        break

        return TextCleaner.dedupe_preserve_order(collected)[:limit]

    def parse(self, payload: Dict[str, Any]) -> SearchResultItem:
        return SearchResultItem(
            heading=TextCleaner.clean_general(payload.get("Heading", "")),
            abstract=TextCleaner.clean_general(payload.get("Abstract", "")),
            related_topics=self.extract_related_topics(payload.get("RelatedTopics", [])),
        )


class WebsiteExtractor:
    @staticmethod
    def _text_score(text: str) -> Tuple[int, int]:
        words = text.split()
        sentence_count = len(re.findall(r"[.!?]", text))
        return (len(words), sentence_count)

    @staticmethod
    def _remove_noise_tags(soup: BeautifulSoup) -> None:
        noisy_tags = [
            "script",
            "style",
            "noscript",
            "header",
            "footer",
            "nav",
            "aside",
            "form",
            "svg",
            "iframe",
            "canvas",
        ]
        for tag in soup(noisy_tags):
            tag.decompose()

    @staticmethod
    def _extract_paragraphs(nodes: Iterable[Any]) -> List[str]:
        paragraphs: List[str] = []
        for node in nodes:
            try:
                text = TextCleaner.clean_extracted_text(node.get_text(" ", strip=True))
            except Exception:
                continue
            if len(text) >= MIN_PARAGRAPH_LENGTH:
                paragraphs.append(text)
        return paragraphs

    def get_candidate_text_blocks(self, soup: BeautifulSoup) -> List[str]:
        selectors = [
            "article",
            "main",
            "[role='main']",
            ".post-content",
            ".entry-content",
            ".article-content",
            ".content",
            ".main-content",
            ".page-content",
        ]

        blocks: List[str] = []

        for selector in selectors:
            for node in soup.select(selector):
                text = TextCleaner.clean_extracted_text(node.get_text(" ", strip=True))
                if len(text) >= MIN_BLOCK_LENGTH:
                    blocks.append(text)

        if not blocks:
            paragraphs = self._extract_paragraphs(soup.find_all("p"))
            if paragraphs:
                blocks.append("\n\n".join(paragraphs[:MAX_PARAGRAPHS_FALLBACK]))

        return TextCleaner.dedupe_preserve_order(blocks)

    def extract(self, html: bytes) -> Dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        self._remove_noise_tags(soup)

        title = ""
        if soup.title and soup.title.string:
            title = TextCleaner.clean_general(soup.title.string)

        candidate_blocks = self.get_candidate_text_blocks(soup)
        best_text = max(candidate_blocks, key=self._text_score, default="")
        best_text = TextCleaner.clean_extracted_text(best_text)[:MAX_EXTRACTED_CHARS]

        return {
            "title": title,
            "text": best_text,
        }


class SummaryEngine:
    def __init__(self, *, llm_client: Optional[Groq], model_name: str) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    @staticmethod
    def fallback_summary(text: str, max_sentences: int = SUMMARY_MAX_SENTENCES) -> str:
        cleaned = TextCleaner.clean_extracted_text(text)
        if not cleaned:
            return ""

        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        selected = [sentence.strip() for sentence in sentences if len(sentence.split()) >= 6]
        return " ".join(selected[:max_sentences]).strip()

    def summarize_with_llm(self, text: str, title: str = "") -> str:
        if self.llm_client is None:
            return ""

        content_text = TextCleaner.clean_extracted_text(text)
        if not content_text:
            return ""

        prompt_parts: List[str] = []
        if title:
            prompt_parts.append(f"Page title: {title}")
        prompt_parts.append(f"Content:\n{content_text}")

        ai_response = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS's website summarizer. "
                        "Summarize the provided website content clearly, accurately, and faithfully. "
                        "Do not invent facts. "
                        "Return only the summary. "
                        "Keep it concise, practical, and easy to understand."
                    ),
                },
                {
                    "role": "user",
                    "content": "\n\n".join(prompt_parts),
                },
            ],
            max_tokens=SUMMARY_MAX_TOKENS,
            temperature=0.2,
        )

        try:
            content = ai_response.choices[0].message.content or ""
        except (AttributeError, IndexError, KeyError, TypeError):
            content = ""

        return TextCleaner.clean_general(content)

    def summarize(self, text: str, title: str = "") -> SummaryResult:
        llm_error: Optional[str] = None
        summary = ""
        summary_source = LLM_SUMMARY_SOURCE

        try:
            summary = self.summarize_with_llm(text, title=title)
        except Exception as error:
            llm_error = safe_error_text(error)
            summary = ""

        if not TextCleaner.is_meaningful(summary):
            summary = self.fallback_summary(text)
            summary_source = FALLBACK_SUMMARY_SOURCE

        return SummaryResult(
            summary=summary,
            source=summary_source,
            llm_error=llm_error,
        )


class MemoryManager:
    def __init__(
        self,
        *,
        writer: Optional[MemoryStore] = None,
        enabled: bool = False,
    ) -> None:
        self.writer = writer or store_memory
        self.enabled = enabled

    def maybe_store(self, label: str, metadata: Dict[str, Any]) -> Optional[str]:
        if not self.enabled:
            return None

        try:
            self.writer(label, metadata)
            return None
        except Exception as error:
            return safe_error_text(error)


class ResultFactory:
    @staticmethod
    def build(
        *,
        success: bool,
        action: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
        source: str = "live_search",
        live_data: bool = False,
    ) -> Dict[str, Any]:
        return AgentResult(
            success=success,
            action=action,
            message=message,
            data=data or {},
            error=error,
            error_code=error_code,
            source=source,
            live_data=live_data,
        ).to_dict()

    @staticmethod
    def empty_search_data(query: str = "") -> Dict[str, Any]:
        return SearchPayload(query=query).to_dict()

    @staticmethod
    def empty_summary_data(
        url: str = "",
        title: str = "",
        extracted_text: str = "",
    ) -> Dict[str, Any]:
        return SummaryPayload(
            url=url,
            title=title,
            extracted_text=extracted_text,
            summary="",
            summary_source="",
        ).to_dict()


class MessageFormatter:
    @staticmethod
    def format_search_message(
        query: str,
        heading: str,
        abstract: str,
        related: Sequence[str],
    ) -> str:
        lines: List[str] = [f"Search results for: {query}"]

        if TextCleaner.is_meaningful(heading):
            lines.append(f"Topic: {heading}")

        if TextCleaner.is_meaningful(abstract):
            lines.append(f"Summary: {abstract}")

        if related:
            lines.append("Related information:")
            lines.extend(f"{index}. {item}" for index, item in enumerate(related, start=1))

        return "\n".join(lines)

    @staticmethod
    def build_summary_data(
        *,
        url: str,
        title: str,
        extracted_text: str,
        summary: str,
        summary_source: str,
        llm_error: Optional[str],
        memory_error: Optional[str],
    ) -> Dict[str, Any]:
        data = SummaryPayload(
            url=url,
            title=title,
            extracted_text=extracted_text,
            summary=summary,
            summary_source=summary_source,
        ).to_dict()

        diagnostics: Dict[str, Any] = {}
        if llm_error:
            diagnostics["llm_error"] = llm_error
        if memory_error:
            diagnostics["memory_error"] = memory_error
        if diagnostics:
            data["diagnostics"] = diagnostics

        return data

    @staticmethod
    def build_search_data(
        *,
        query: str,
        heading: str,
        abstract: str,
        related_topics: List[str],
        memory_error: Optional[str],
    ) -> Dict[str, Any]:
        data = SearchPayload(
            query=query,
            heading=heading,
            abstract=abstract,
            related_topics=related_topics,
        ).to_dict()

        if memory_error:
            data["diagnostics"] = {"memory_error": memory_error}

        return data


class WebSearchAgent:
    def __init__(
        self,
        *,
        search_client: Optional[WebSearchClient] = None,
        parser: Optional[SearchResponseParser] = None,
        memory_manager: Optional[MemoryManager] = None,
    ) -> None:
        self.search_client = search_client or WebSearchClient()
        self.parser = parser or SearchResponseParser()
        self.memory_manager = memory_manager or MemoryManager(enabled=False)

    def _build_search_success(
        self,
        *,
        query: str,
        parsed: SearchResultItem,
        source: str,
    ) -> Dict[str, Any]:
        memory_error = self.memory_manager.maybe_store(
            f"Web searched: {query}",
            {
                "type": "web_search",
                "query": query,
                "source": source,
            },
        )

        return ResultFactory.build(
            success=True,
            action=SEARCH_ACTION,
            message=MessageFormatter.format_search_message(
                query,
                parsed.heading,
                parsed.abstract,
                parsed.related_topics,
            ),
            data=MessageFormatter.build_search_data(
                query=query,
                heading=parsed.heading,
                abstract=parsed.abstract,
                related_topics=parsed.related_topics,
                memory_error=memory_error,
            ),
            source=source,
            live_data=True,
        )

    @staticmethod
    def _extract_groq_model_prices(lines: Sequence[str]) -> List[Dict[str, str]]:
        prices: List[Dict[str, str]] = []
        seen_model_ids = set()
        money_pattern = re.compile(r"^\$\d+(?:\.\d+)?$")

        for index in range(len(lines) - 5):
            display_name = TextCleaner.clean_general(lines[index])
            model_id = TextCleaner.clean_general(lines[index + 1])
            if not display_name or not model_id or model_id in seen_model_ids:
                continue
            if "/" not in model_id and "-" not in model_id:
                continue

            for cursor in range(index + 2, min(index + 10, len(lines) - 3)):
                input_price = TextCleaner.clean_general(lines[cursor])
                input_label = TextCleaner.clean_general(lines[cursor + 1]).lower()
                output_price = TextCleaner.clean_general(lines[cursor + 2])
                output_label = TextCleaner.clean_general(lines[cursor + 3]).lower()
                if (
                    money_pattern.fullmatch(input_price)
                    and input_label == "input"
                    and money_pattern.fullmatch(output_price)
                    and output_label == "output"
                ):
                    prices.append(
                        {
                            "display_name": display_name,
                            "model_id": model_id,
                            "input_price": input_price,
                            "output_price": output_price,
                        }
                    )
                    seen_model_ids.add(model_id)
                    break

        return prices

    def _official_live_search_fallback(self, query: str) -> Optional[Tuple[SearchResultItem, str]]:
        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            return None

        try:
            if "openai" in normalized_query and "status" in normalized_query:
                payload = self.search_client.fetch_json(OPENAI_STATUS_API_URL, {})
                status_info = payload.get("status") if isinstance(payload.get("status"), dict) else {}
                page_info = payload.get("page") if isinstance(payload.get("page"), dict) else {}
                description = TextCleaner.clean_general(status_info.get("description"))
                indicator = TextCleaner.clean_general(status_info.get("indicator"))
                updated_at = TextCleaner.clean_general(page_info.get("updated_at"))
                if description:
                    related_topics = []
                    if indicator:
                        related_topics.append(f"Status indicator: {indicator}.")
                    if updated_at:
                        related_topics.append(f"Updated at: {updated_at}.")
                    related_topics.append("Source: status.openai.com")
                    return (
                        SearchResultItem(
                            heading="OpenAI API status",
                            abstract=f"OpenAI's official status page currently reports: {description}.",
                            related_topics=related_topics,
                        ),
                        OPENAI_STATUS_SOURCE,
                    )
        except Exception:
            return None

        try:
            if "groq" in normalized_query and any(token in normalized_query for token in ("price", "pricing")):
                response = self.search_client.fetch_html(GROQ_MODELS_URL)
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text("\n", strip=True)
                lines = [TextCleaner.clean_general(line) for line in text.splitlines()]
                lines = [line for line in lines if line]
                price_entries = self._extract_groq_model_prices(lines)
                if price_entries:
                    preferred_order = [
                        "llama-3.3-70b-versatile",
                        "llama-3.1-8b-instant",
                    ]
                    ordered_entries = sorted(
                        price_entries,
                        key=lambda item: (
                            0
                            if item["model_id"] in preferred_order
                            else 1,
                            preferred_order.index(item["model_id"])
                            if item["model_id"] in preferred_order
                            else 999,
                        ),
                    )
                    featured = ordered_entries[:3]
                    lead = featured[0]
                    abstract = (
                        f"Groq's official models page currently lists {lead['display_name']} "
                        f"({lead['model_id']}) at {lead['input_price']} input and {lead['output_price']} "
                        "output per 1M tokens on the developer plan."
                    )
                    related_topics = [
                        (
                            f"{item['display_name']} ({item['model_id']}): "
                            f"{item['input_price']} input and {item['output_price']} output per 1M tokens."
                        )
                        for item in featured[1:]
                    ]
                    related_topics.append("Source: console.groq.com/docs/models")
                    return (
                        SearchResultItem(
                            heading="Groq API pricing",
                            abstract=abstract,
                            related_topics=related_topics,
                        ),
                        GROQ_MODELS_SOURCE,
                    )
        except Exception:
            return None

        return None

    def search(self, query: str) -> Dict[str, Any]:
        normalized_query = TextCleaner.clean_query(query)

        if not normalized_query:
            return ResultFactory.build(
                success=False,
                action=SEARCH_ACTION,
                message="Please provide something to search for.",
                data=ResultFactory.empty_search_data(""),
                error="Missing search query.",
                error_code=ERROR_EMPTY_QUERY,
                source="validation",
                live_data=False,
            )

        try:
            payload = self.search_client.fetch_json(
                DUCKDUCKGO_API_URL,
                {
                    "q": normalized_query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                },
            )

            parsed = self.parser.parse(payload)

            if not any([parsed.heading, parsed.abstract, parsed.related_topics]):
                fallback = self._official_live_search_fallback(normalized_query)
                if fallback is None:
                    raise NoResultsError(
                        "No useful search results returned.",
                        user_message=f"No useful live search results were found for '{normalized_query}'.",
                    )
                parsed, source = fallback
                return self._build_search_success(
                    query=normalized_query,
                    parsed=parsed,
                    source=source,
                )

            return self._build_search_success(
                query=normalized_query,
                parsed=parsed,
                source=SEARCH_SOURCE,
            )

        except NoResultsError as error:
            fallback = self._official_live_search_fallback(normalized_query)
            if fallback is not None:
                parsed, source = fallback
                return self._build_search_success(
                    query=normalized_query,
                    parsed=parsed,
                    source=source,
                )
            return ResultFactory.build(
                success=False,
                action=SEARCH_ACTION,
                message=error.user_message,
                data=ResultFactory.empty_search_data(normalized_query),
                error=safe_error_text(error),
                error_code=error.error_code,
                source=SEARCH_SOURCE,
                live_data=False,
            )

        except requests.exceptions.Timeout as error:
            fallback = self._official_live_search_fallback(normalized_query)
            if fallback is not None:
                parsed, source = fallback
                return self._build_search_success(
                    query=normalized_query,
                    parsed=parsed,
                    source=source,
                )
            return ResultFactory.build(
                success=False,
                action=SEARCH_ACTION,
                message="Live web search timed out.",
                data=ResultFactory.empty_search_data(normalized_query),
                error=safe_error_text(error),
                error_code=ERROR_TIMEOUT,
                source=SEARCH_SOURCE,
                live_data=False,
            )

        except requests.exceptions.RequestException as error:
            fallback = self._official_live_search_fallback(normalized_query)
            if fallback is not None:
                parsed, source = fallback
                return self._build_search_success(
                    query=normalized_query,
                    parsed=parsed,
                    source=source,
                )
            return ResultFactory.build(
                success=False,
                action=SEARCH_ACTION,
                message="I couldn't fetch live web search results because of a network issue.",
                data=ResultFactory.empty_search_data(normalized_query),
                error=safe_error_text(error),
                error_code=ERROR_NETWORK,
                source=SEARCH_SOURCE,
                live_data=False,
            )

        except InvalidResponseError as error:
            return ResultFactory.build(
                success=False,
                action=SEARCH_ACTION,
                message=error.user_message,
                data=ResultFactory.empty_search_data(normalized_query),
                error=safe_error_text(error),
                error_code=error.error_code,
                source=SEARCH_SOURCE,
                live_data=False,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=SEARCH_ACTION,
                message="I couldn't fetch live web search results right now.",
                data=ResultFactory.empty_search_data(normalized_query),
                error=safe_error_text(error),
                error_code=ERROR_UNEXPECTED,
                source=SEARCH_SOURCE,
                live_data=False,
            )

    def close(self) -> None:
        self.search_client.close()


class WebsiteSummaryAgent:
    def __init__(
        self,
        *,
        web_client: Optional[WebSearchClient] = None,
        extractor: Optional[WebsiteExtractor] = None,
        summary_engine: Optional[SummaryEngine] = None,
        memory_manager: Optional[MemoryManager] = None,
    ) -> None:
        self.web_client = web_client or WebSearchClient()
        self.extractor = extractor or WebsiteExtractor()
        self.summary_engine = summary_engine or SummaryEngine(
            llm_client=maybe_create_groq_client(),
            model_name=MODEL_NAME,
        )
        self.memory_manager = memory_manager or MemoryManager(enabled=False)

    def summarize(self, url: str) -> Dict[str, Any]:
        raw_url = TextCleaner.clean_general(url)

        if not raw_url:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message="Please provide a website URL.",
                data=ResultFactory.empty_summary_data(),
                error="Missing URL.",
                error_code=ERROR_EMPTY_URL,
                source="validation",
                live_data=False,
            )

        try:
            normalized_url = UrlNormalizer.normalize(raw_url)
        except WebSearchError as error:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message=error.user_message,
                data=ResultFactory.empty_summary_data(),
                error=safe_error_text(error),
                error_code=error.error_code,
                source="validation",
                live_data=False,
            )

        try:
            response = self.web_client.fetch_html(normalized_url)
            extracted = self.extractor.extract(response.content)

            title = extracted.get("title", "")
            extracted_text = extracted.get("text", "")

            if not TextCleaner.is_meaningful(extracted_text):
                raise NoReadableContentError(
                    "No readable website text extracted.",
                    user_message="I could not extract readable content from that website.",
                )

            summary_result = self.summary_engine.summarize(
                extracted_text,
                title=title,
            )

            if not TextCleaner.is_meaningful(summary_result.summary):
                raise EmptySummaryError(
                    "Summarizer returned empty content.",
                    user_message="I couldn't summarize that website right now.",
                )

            memory_error = self.memory_manager.maybe_store(
                f"Website summarized: {normalized_url}",
                {
                    "type": "website_summary",
                    "url": normalized_url,
                    "title": title,
                    "source": summary_result.source,
                },
            )

            return ResultFactory.build(
                success=True,
                action=SUMMARY_ACTION,
                message=summary_result.summary,
                data=MessageFormatter.build_summary_data(
                    url=normalized_url,
                    title=title,
                    extracted_text=extracted_text,
                    summary=summary_result.summary,
                    summary_source=summary_result.source,
                    llm_error=summary_result.llm_error,
                    memory_error=memory_error,
                ),
                source=summary_result.source,
                live_data=True,
            )

        except NoReadableContentError as error:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message=error.user_message,
                data=ResultFactory.empty_summary_data(normalized_url),
                error=safe_error_text(error),
                error_code=error.error_code,
                source=WEBSITE_FETCH_SOURCE,
                live_data=True,
            )

        except EmptySummaryError as error:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message=error.user_message,
                data=ResultFactory.empty_summary_data(normalized_url),
                error=safe_error_text(error),
                error_code=error.error_code,
                source=LLM_SUMMARY_SOURCE,
                live_data=True,
            )

        except requests.exceptions.Timeout as error:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message="Website access timed out.",
                data=ResultFactory.empty_summary_data(normalized_url),
                error=safe_error_text(error),
                error_code=ERROR_TIMEOUT,
                source=WEBSITE_FETCH_SOURCE,
                live_data=False,
            )

        except requests.exceptions.RequestException as error:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message="I couldn't access that website right now.",
                data=ResultFactory.empty_summary_data(normalized_url),
                error=safe_error_text(error),
                error_code=ERROR_NETWORK,
                source=WEBSITE_FETCH_SOURCE,
                live_data=False,
            )

        except InvalidContentError as error:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message=error.user_message,
                data=ResultFactory.empty_summary_data(normalized_url),
                error=safe_error_text(error),
                error_code=error.error_code,
                source=WEBSITE_FETCH_SOURCE,
                live_data=False,
            )

        except ValueError as error:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message="The website could not be processed.",
                data=ResultFactory.empty_summary_data(normalized_url),
                error=safe_error_text(error),
                error_code=ERROR_INVALID_CONTENT,
                source=WEBSITE_FETCH_SOURCE,
                live_data=False,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=SUMMARY_ACTION,
                message="I couldn't summarize that website right now.",
                data=ResultFactory.empty_summary_data(normalized_url),
                error=safe_error_text(error),
                error_code=ERROR_UNEXPECTED,
                source="website_fetch_llm_summary",
                live_data=False,
            )

    def close(self) -> None:
        self.web_client.close()


_web_search_agent = WebSearchAgent()
_website_summary_agent = WebsiteSummaryAgent()


def web_search(query: str) -> Dict[str, Any]:
    return _web_search_agent.search(query)


def summarize_website(url: str) -> Dict[str, Any]:
    return _website_summary_agent.summarize(url)
