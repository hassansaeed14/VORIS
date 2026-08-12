from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from config.settings import NEWS_API_KEY


NEWS_API_URL = "https://gnews.io/api/v4/search"

CAPABILITY_MODE = "real"
TRUST_LEVEL = "safe"
AGENT_NAME = "news"
ACTION_NAME = "get_news"
REQUEST_TIMEOUT = 10
DEFAULT_LANGUAGE = "en"
DEFAULT_MAX_ARTICLES = 10
DISPLAY_LIMIT = 5
LATEST_MAX_AGE_DAYS = 3


@dataclass
class NewsArticle:
    title: str
    description: str
    source: str
    url: str
    published_at: str
    published_at_dt: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["published_at_dt"] = self.published_at_dt.isoformat() if self.published_at_dt else None
        return data


@dataclass
class NewsPayload:
    topic: str
    articles: List[NewsArticle] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "articles": [article.to_dict() for article in self.articles],
        }


@dataclass
class AgentResult:
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None
    source: str = "live_api"
    live_data: bool = False
    mode: str = CAPABILITY_MODE
    agent: str = AGENT_NAME
    action: str = ACTION_NAME
    trust_level: str = TRUST_LEVEL

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NewsAgentError(Exception):
    error_code = "NEWS_AGENT_ERROR"

    def __init__(self, message: str, *, user_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class MissingApiKeyError(NewsAgentError):
    error_code = "MISSING_API_KEY"


class AuthenticationError(NewsAgentError):
    error_code = "AUTH_ERROR"


class RateLimitedError(NewsAgentError):
    error_code = "RATE_LIMITED"


class InvalidResponseError(NewsAgentError):
    error_code = "INVALID_RESPONSE"


class NoArticlesError(NewsAgentError):
    error_code = "NO_ARTICLES"


def safe_error_text(error: Exception) -> str:
    text = str(error).strip()
    return text if text else error.__class__.__name__


class NewsTopicNormalizer:
    PATTERNS = [
        r"^(show me|tell me|give me|find me)\s+",
        r"^(what('?s| is)\s+)?(the\s+)?",
        r"^(latest\s+)?(news|headlines)\s+(about|on|for)\s+",
        r"^(latest\s+)?(news|headlines)\s+",
    ]

    REMOVE_WORDS_PATTERN = r"\b(latest|current|today|now|please|happening)\b"

    @classmethod
    def normalize(cls, topic: str) -> str:
        text = str(topic or "").strip()
        if not text:
            return "general"

        for pattern in cls.PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        text = re.sub(cls.REMOVE_WORDS_PATTERN, "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip(" ,.?")

        return text or "general"

    @staticmethod
    def is_latest_request(topic: str) -> bool:
        text = str(topic or "").lower()
        return any(token in text for token in ["latest", "headlines", "today", "current", "breaking", "now"])


class NewsClient:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        session: Optional[requests.Session] = None,
        base_url: str = NEWS_API_URL,
        timeout: int = REQUEST_TIMEOUT,
    ) -> None:
        self.api_key = api_key or NEWS_API_KEY
        self.session = session or requests.Session()
        self.base_url = base_url
        self.timeout = timeout

    def fetch_articles(
        self,
        *,
        topic: str,
        language: str = DEFAULT_LANGUAGE,
        max_articles: int = DEFAULT_MAX_ARTICLES,
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise MissingApiKeyError(
                "Missing NEWS_API_KEY.",
                user_message="News service is not configured.",
            )

        response = self.session.get(
            self.base_url,
            params={
                "q": topic,
                "lang": language,
                "max": max_articles,
                "apikey": self.api_key,
            },
            timeout=self.timeout,
        )

        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed with HTTP {response.status_code}.",
                user_message="News service authentication failed.",
            )

        if response.status_code == 429:
            raise RateLimitedError(
                "News API rate limit reached.",
                user_message="News service rate limit reached. Please try again later.",
            )

        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise InvalidResponseError(
                "News API response is not a dictionary.",
                user_message="The news service returned invalid data.",
            )

        raw_articles = payload.get("articles")
        if not isinstance(raw_articles, list):
            raise InvalidResponseError(
                "News API articles field is invalid.",
                user_message="The news service returned invalid data.",
            )

        return raw_articles


class NewsParser:
    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None

        text = str(value).strip()
        if not text:
            return None

        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url)
            return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        except Exception:
            return False

    def normalize_article(self, article: Dict[str, Any]) -> Optional[NewsArticle]:
        source_block = article.get("source")
        if not isinstance(source_block, dict):
            source_block = {}

        title = self._clean_text(article.get("title"))
        description = self._clean_text(article.get("description"))
        source = self._clean_text(source_block.get("name")) or "Unknown"
        url = self._clean_text(article.get("url"))
        published_at = self._clean_text(article.get("publishedAt"))
        published_at_dt = self._parse_datetime(published_at)

        if not title:
            return None

        if url and not self._is_valid_url(url):
            url = ""

        return NewsArticle(
            title=title,
            description=description,
            source=source,
            url=url,
            published_at=published_at,
            published_at_dt=published_at_dt,
        )

    def parse_articles(self, raw_articles: List[Dict[str, Any]]) -> List[NewsArticle]:
        parsed: List[NewsArticle] = []

        for raw in raw_articles:
            if not isinstance(raw, dict):
                continue

            article = self.normalize_article(raw)
            if article is None:
                continue

            parsed.append(article)

        return parsed


class NewsPostProcessor:
    @staticmethod
    def deduplicate(articles: List[NewsArticle]) -> List[NewsArticle]:
        seen = set()
        unique: List[NewsArticle] = []

        for article in articles:
            key = (
                article.title.strip().lower(),
                article.source.strip().lower(),
                article.url.strip().lower(),
            )
            if key in seen:
                continue

            seen.add(key)
            unique.append(article)

        return unique

    @staticmethod
    def filter_quality(articles: List[NewsArticle]) -> List[NewsArticle]:
        filtered: List[NewsArticle] = []

        for article in articles:
            if not article.title.strip():
                continue
            if not article.source.strip():
                continue
            filtered.append(article)

        return filtered

    @staticmethod
    def filter_stale_for_latest(articles: List[NewsArticle], *, is_latest_request: bool) -> List[NewsArticle]:
        if not is_latest_request:
            return articles

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=LATEST_MAX_AGE_DAYS)

        fresh = [
            article for article in articles
            if article.published_at_dt and article.published_at_dt >= cutoff
        ]

        return fresh if fresh else articles

    @staticmethod
    def sort_by_recency(articles: List[NewsArticle]) -> List[NewsArticle]:
        fallback_dt = datetime.min.replace(tzinfo=timezone.utc)

        return sorted(
            articles,
            key=lambda article: article.published_at_dt or fallback_dt,
            reverse=True,
        )

    def process(
        self,
        articles: List[NewsArticle],
        *,
        limit: int = DISPLAY_LIMIT,
        is_latest_request: bool = False,
    ) -> List[NewsArticle]:
        cleaned = self.filter_quality(articles)
        cleaned = self.deduplicate(cleaned)
        cleaned = self.filter_stale_for_latest(cleaned, is_latest_request=is_latest_request)
        cleaned = self.sort_by_recency(cleaned)
        return cleaned[:limit]


class NewsFormatter:
    @staticmethod
    def build_message(topic: str, articles: List[NewsArticle]) -> str:
        lines = [f"Latest news on {topic}:", ""]

        for index, article in enumerate(articles, 1):
            lines.append(f"{index}. {article.title}")
            lines.append(f"   Source: {article.source}")

            if article.published_at:
                lines.append(f"   Published: {article.published_at}")

            if article.description:
                lines.append(f"   {article.description}")

            if article.url:
                lines.append(f"   Link: {article.url}")

            lines.append("")

        return "\n".join(lines).strip()


class NewsAgent:
    def __init__(
        self,
        *,
        client: Optional[NewsClient] = None,
        parser: Optional[NewsParser] = None,
        processor: Optional[NewsPostProcessor] = None,
        formatter: Optional[NewsFormatter] = None,
    ) -> None:
        self.client = client or NewsClient()
        self.parser = parser or NewsParser()
        self.processor = processor or NewsPostProcessor()
        self.formatter = formatter or NewsFormatter()

    @staticmethod
    def build_result(
        *,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
        source: str = "live_api",
        live_data: bool = False,
    ) -> Dict[str, Any]:
        return AgentResult(
            success=success,
            message=message,
            data=data or {},
            error=error,
            error_code=error_code,
            source=source,
            live_data=live_data,
        ).to_dict()

    def get_news(self, topic: str = "general") -> Dict[str, Any]:
        latest_request = NewsTopicNormalizer.is_latest_request(topic)
        normalized_topic = NewsTopicNormalizer.normalize(topic)

        try:
            raw_articles = self.client.fetch_articles(topic=normalized_topic)
            parsed_articles = self.parser.parse_articles(raw_articles)
            final_articles = self.processor.process(
                parsed_articles,
                limit=DISPLAY_LIMIT,
                is_latest_request=latest_request,
            )

            if not final_articles:
                raise NoArticlesError(
                    f"No usable articles found for topic: {normalized_topic}",
                    user_message=f"I couldn't find live news results for {normalized_topic} right now.",
                )

            payload = NewsPayload(topic=normalized_topic, articles=final_articles)

            return self.build_result(
                success=True,
                message=self.formatter.build_message(normalized_topic, final_articles),
                data=payload.to_dict(),
                source="live_api",
                live_data=True,
            )

        except NewsAgentError as e:
            source = "config" if isinstance(e, MissingApiKeyError) else "live_api"
            return self.build_result(
                success=False,
                message=e.user_message,
                data={"topic": normalized_topic, "articles": []},
                error=safe_error_text(e),
                error_code=e.error_code,
                source=source,
                live_data=False,
            )

        except requests.exceptions.Timeout as e:
            return self.build_result(
                success=False,
                message="Live news service timed out. Please try again.",
                data={"topic": normalized_topic, "articles": []},
                error=safe_error_text(e),
                error_code="TIMEOUT",
                source="live_api",
                live_data=False,
            )

        except requests.exceptions.RequestException as e:
            return self.build_result(
                success=False,
                message="I couldn't fetch live news right now because of a network or API issue.",
                data={"topic": normalized_topic, "articles": []},
                error=safe_error_text(e),
                error_code="NETWORK_ERROR",
                source="live_api",
                live_data=False,
            )

        except Exception as e:
            return self.build_result(
                success=False,
                message="I couldn't fetch live news right now.",
                data={"topic": normalized_topic, "articles": []},
                error=safe_error_text(e),
                error_code="UNEXPECTED_ERROR",
                source="live_api",
                live_data=False,
            )


news_agent = NewsAgent()


def get_news(topic: str = "general") -> Dict[str, Any]:
    return news_agent.get_news(topic)


def get_pakistan_news() -> Dict[str, Any]:
    return news_agent.get_news("Pakistan latest news")


def get_tech_news() -> Dict[str, Any]:
    return news_agent.get_news("technology AI latest news")


def get_sports_news() -> Dict[str, Any]:
    return news_agent.get_news("sports latest news")