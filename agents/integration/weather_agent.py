from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import requests

from memory.vector_memory import store_memory


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

CAPABILITY_MODE = "real"
TRUST_LEVEL = "safe"
AGENT_NAME = "weather"
ACTION_NAME = "get_weather"
REQUEST_TIMEOUT = 10


@dataclass
class WeatherLocation:
    city: str
    region: str
    country: str
    latitude: float
    longitude: float

    @property
    def label(self) -> str:
        if self.region and self.country:
            return f"{self.city}, {self.region}, {self.country}"
        if self.country:
            return f"{self.city}, {self.country}"
        return self.city


@dataclass
class CurrentWeather:
    temperature_c: Optional[float]
    feels_like_c: Optional[float]
    humidity_percent: Optional[float]
    wind_speed_kmh: Optional[float]
    weather_code: Optional[int]
    condition: str


@dataclass
class ForecastDay:
    label: str
    max_c: Optional[float]
    min_c: Optional[float]
    weather_code: Optional[int]
    condition: str
    precipitation_mm: Optional[float]


@dataclass
class WeatherPayload:
    location: WeatherLocation
    current: CurrentWeather
    forecast_days: List[ForecastDay] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": asdict(self.location) | {"label": self.location.label},
            "current": asdict(self.current),
            "forecast_days": [asdict(day) for day in self.forecast_days],
        }


@dataclass
class AgentResult:
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None
    mode: str = CAPABILITY_MODE
    agent: str = AGENT_NAME
    action: str = ACTION_NAME
    trust_level: str = TRUST_LEVEL

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WeatherAgentError(Exception):
    error_code = "WEATHER_AGENT_ERROR"

    def __init__(self, message: str, *, user_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class MissingCityError(WeatherAgentError):
    error_code = "MISSING_CITY"


class CityNotFoundError(WeatherAgentError):
    error_code = "CITY_NOT_FOUND"


class InvalidLocationDataError(WeatherAgentError):
    error_code = "INVALID_LOCATION_DATA"


class InvalidWeatherDataError(WeatherAgentError):
    error_code = "INVALID_WEATHER_DATA"


class WeatherClient:
    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        geocode_url: str = GEOCODE_URL,
        weather_url: str = WEATHER_URL,
        timeout: int = REQUEST_TIMEOUT,
    ) -> None:
        self.session = session or requests.Session()
        self.geocode_url = geocode_url
        self.weather_url = weather_url
        self.timeout = timeout

    def get_coordinates(self, city: str) -> WeatherLocation:
        response = self.session.get(
            self.geocode_url,
            params={"name": city, "count": 1},
            timeout=self.timeout,
        )
        response.raise_for_status()

        payload = response.json()
        results = payload.get("results") or []
        if not results:
            raise CityNotFoundError(
                f"City not found in geocoding lookup: {city}",
                user_message=f"Sorry, I could not find weather data for {city}. Please check the city name.",
            )

        raw = results[0]

        name = raw.get("name")
        latitude = raw.get("latitude")
        longitude = raw.get("longitude")
        country = raw.get("country", "") or ""
        region = raw.get("admin1", "") or ""

        if not name or latitude is None or longitude is None:
            raise InvalidLocationDataError(
                "Geocoding response missing required fields.",
                user_message="Location data was incomplete. Please try again.",
            )

        return WeatherLocation(
            city=str(name),
            region=str(region),
            country=str(country),
            latitude=float(latitude),
            longitude=float(longitude),
        )

    def get_weather(self, location: WeatherLocation) -> Dict[str, Any]:
        response = self.session.get(
            self.weather_url,
            params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current": (
                    "temperature_2m,relative_humidity_2m,"
                    "wind_speed_10m,weather_code,apparent_temperature"
                ),
                "daily": (
                    "weather_code,temperature_2m_max,"
                    "temperature_2m_min,precipitation_sum"
                ),
                "timezone": "auto",
                "forecast_days": 3,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        payload = response.json()
        if "current" not in payload or "daily" not in payload:
            raise InvalidWeatherDataError(
                "Weather response missing current or daily block.",
                user_message="Weather data was incomplete. Please try again.",
            )

        return payload


class WeatherFormatter:
    WEATHER_CODES = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Light rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Light snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Light rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Light snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with light hail",
        99: "Thunderstorm with heavy hail",
    }

    @classmethod
    def weather_code_to_text(cls, code: Optional[int]) -> str:
        return cls.WEATHER_CODES.get(code, "Unknown")

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def build_current_weather(self, current: Dict[str, Any]) -> CurrentWeather:
        code = self._to_int(current.get("weather_code"))
        return CurrentWeather(
            temperature_c=self._to_float(current.get("temperature_2m")),
            feels_like_c=self._to_float(current.get("apparent_temperature")),
            humidity_percent=self._to_float(current.get("relative_humidity_2m")),
            wind_speed_kmh=self._to_float(current.get("wind_speed_10m")),
            weather_code=code,
            condition=self.weather_code_to_text(code),
        )

    def build_forecast_days(self, daily: Dict[str, Any]) -> List[ForecastDay]:
        max_temps = daily.get("temperature_2m_max") or []
        min_temps = daily.get("temperature_2m_min") or []
        codes = daily.get("weather_code") or []
        rain = daily.get("precipitation_sum") or []

        labels = ["Today", "Tomorrow", "Day 3"]
        count = min(3, len(max_temps), len(min_temps))

        forecast_days: List[ForecastDay] = []
        for i in range(count):
            code = self._to_int(codes[i]) if i < len(codes) else None
            forecast_days.append(
                ForecastDay(
                    label=labels[i] if i < len(labels) else f"Day {i + 1}",
                    max_c=self._to_float(max_temps[i]),
                    min_c=self._to_float(min_temps[i]),
                    weather_code=code,
                    condition=self.weather_code_to_text(code),
                    precipitation_mm=self._to_float(rain[i]) if i < len(rain) else 0.0,
                )
            )

        return forecast_days

    def build_message(self, payload: WeatherPayload) -> str:
        current = payload.current
        lines = [
            f"Current weather in {payload.location.label}:",
            f"- Temperature: {self._display(current.temperature_c, '°C')}",
            f"- Feels like: {self._display(current.feels_like_c, '°C')}",
            f"- Condition: {current.condition}",
            f"- Humidity: {self._display(current.humidity_percent, '%')}",
            f"- Wind speed: {self._display(current.wind_speed_kmh, ' km/h')}",
            "",
            "3-day forecast:",
        ]

        for day in payload.forecast_days:
            lines.append(
                f"- {day.label}: "
                f"High {self._display(day.max_c, '°C')} / "
                f"Low {self._display(day.min_c, '°C')} | "
                f"{day.condition} | "
                f"Rain: {self._display(day.precipitation_mm, ' mm')}"
            )

        return "\n".join(lines).strip()

    @staticmethod
    def _display(value: Optional[float], suffix: str = "") -> str:
        if value is None:
            return "N/A"
        if value.is_integer():
            return f"{int(value)}{suffix}"
        return f"{value:.1f}{suffix}"


class WeatherAgent:
    def __init__(
        self,
        *,
        client: Optional[WeatherClient] = None,
        formatter: Optional[WeatherFormatter] = None,
        store_weather_memory: bool = False,
    ) -> None:
        self.client = client or WeatherClient()
        self.formatter = formatter or WeatherFormatter()
        self.store_weather_memory = store_weather_memory

    @staticmethod
    def clean_city_name(city: str) -> str:
        text = str(city or "").strip()

        patterns = [
            r"^(can you\s+)?(please\s+)?(tell me\s+)?(what('?s| is)\s+the\s+)?"
            r"(weather|forecast|temperature)\s+(in|for)\s+",
            r"^(weather|forecast|temperature)\s*[:\-]?\s*",
        ]

        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        text = re.sub(r"\b(today|right now|currently|now)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text)
        return text.strip(" ,.?")

    @staticmethod
    def build_result(
        *,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        return AgentResult(
            success=success,
            message=message,
            data=data or {},
            error=error,
            error_code=error_code,
        ).to_dict()

    def _store_memory_safe(self, location: WeatherLocation) -> None:
        try:
            store_memory(
                f"Weather checked for {location.label}",
                {
                    "type": "weather",
                    "city": location.city,
                    "country": location.country,
                },
            )
        except Exception:
            pass

    def get_weather(self, city: str) -> Dict[str, Any]:
        try:
            cleaned_city = self.clean_city_name(city)
            if not cleaned_city:
                raise MissingCityError(
                    "Missing city name.",
                    user_message="Please provide a city name.",
                )

            location = self.client.get_coordinates(cleaned_city)
            raw_weather = self.client.get_weather(location)

            current_block = raw_weather.get("current", {})
            daily_block = raw_weather.get("daily", {})

            current = self.formatter.build_current_weather(current_block)
            forecast_days = self.formatter.build_forecast_days(daily_block)

            payload = WeatherPayload(
                location=location,
                current=current,
                forecast_days=forecast_days,
            )

            if self.store_weather_memory:
                self._store_memory_safe(location)

            return self.build_result(
                success=True,
                message=self.formatter.build_message(payload),
                data=payload.to_dict(),
            )

        except MissingCityError as e:
            return self.build_result(
                success=False,
                message=e.user_message,
                error=str(e),
                error_code=e.error_code,
            )

        except CityNotFoundError as e:
            return self.build_result(
                success=False,
                message=e.user_message,
                error=str(e),
                error_code=e.error_code,
            )

        except (InvalidLocationDataError, InvalidWeatherDataError) as e:
            return self.build_result(
                success=False,
                message=e.user_message,
                error=str(e),
                error_code=e.error_code,
            )

        except requests.exceptions.Timeout as e:
            return self.build_result(
                success=False,
                message="Weather service timed out. Please try again.",
                error=str(e),
                error_code="TIMEOUT",
            )

        except requests.exceptions.RequestException as e:
            return self.build_result(
                success=False,
                message="Could not fetch weather data because of a network issue. Please try again.",
                error=str(e),
                error_code="NETWORK_ERROR",
            )

        except Exception as e:
            return self.build_result(
                success=False,
                message="Could not fetch weather data right now.",
                error=str(e),
                error_code="UNEXPECTED_ERROR",
            )


weather_agent = WeatherAgent(store_weather_memory=False)


def get_weather(city: str) -> Dict[str, Any]:
    return weather_agent.get_weather(city)