"""Seasonal production timing intelligence for Aurora."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any


PRODUCE_NOW = "PRODUCE_NOW"
PRODUCE_FOR_UPCOMING_SEASON = "PRODUCE_FOR_UPCOMING_SEASON"
EVERGREEN = "EVERGREEN"
HOLD = "HOLD"
REJECT_OUT_OF_SEASON = "REJECT_OUT_OF_SEASON"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SEASONAL_CONFIG_PATH = PROJECT_ROOT / "config" / "seasonal_calendar.yaml"


@dataclass(frozen=True, slots=True)
class SeasonalReview:
    """Seasonal production decision for one product."""

    product_name: str
    current_date: date
    season: str
    seasonal_category: str
    seasonal_score: int
    lead_time_score: int
    evergreen_score: int
    production_decision: str
    reason: str
    next_recommended_window: str
    is_out_of_season: bool
    is_evergreen: bool
    is_inventory_build: bool
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "current_date": self.current_date.isoformat(),
            "season": self.season,
            "seasonal_category": self.seasonal_category,
            "seasonal_score": self.seasonal_score,
            "lead_time_score": self.lead_time_score,
            "evergreen_score": self.evergreen_score,
            "production_decision": self.production_decision,
            "reason": self.reason,
            "next_recommended_window": self.next_recommended_window,
            "is_out_of_season": self.is_out_of_season,
            "is_evergreen": self.is_evergreen,
            "is_inventory_build": self.is_inventory_build,
            "created_at": self.created_at.isoformat(),
        }


class SeasonalIntelligence:
    """Evaluate whether a product should be produced now."""

    def __init__(
        self,
        config_path: Path | None = None,
        today: date | None = None,
        allow_inventory_build: bool = False,
    ) -> None:
        self._config_path = config_path or DEFAULT_SEASONAL_CONFIG_PATH
        self._today = today or date.today()
        self._allow_inventory_build = allow_inventory_build
        self._config = _load_calendar(self._config_path)

    def evaluate(
        self,
        product_name: str,
        season: str = "",
        product_type: str = "",
        *,
        inventory_build: bool = False,
    ) -> SeasonalReview:
        """Return a production-timing review."""
        category, record = self._match_category(product_name, season, product_type)
        is_evergreen = category in {"evergreen", "weddings", "baby_showers", "birthdays"}
        in_selling = _date_in_window(self._today, record["selling_start"], record["selling_end"])
        in_production = _date_in_window(self._today, record["production_start"], record["production_end"])
        is_inventory_build = inventory_build or self._allow_inventory_build
        evergreen_score = 95 if is_evergreen else 20
        lead_time_score = 100 if in_production else 35
        seasonal_score = 95 if in_selling else 85 if in_production else evergreen_score

        if is_evergreen:
            decision = EVERGREEN
            reason = "Evergreen category remains eligible year-round."
            out_of_season = False
        elif category == "graduation" and self._today.month == 7 and self._today.day >= 1 and not is_inventory_build:
            decision = REJECT_OUT_OF_SEASON
            reason = "Graduation demand has passed its primary buying season; hold until the next production window."
            out_of_season = True
            seasonal_score = 25
            lead_time_score = 20
        elif in_selling:
            decision = PRODUCE_NOW
            reason = "Product is inside the active selling window."
            out_of_season = False
        elif in_production or is_inventory_build:
            decision = PRODUCE_FOR_UPCOMING_SEASON
            reason = "Product is inside the configured production lead-time window."
            out_of_season = False
        else:
            decision = HOLD
            reason = "Product is outside the configured selling and production windows."
            out_of_season = True
            seasonal_score = min(seasonal_score, 45)

        return SeasonalReview(
            product_name=product_name,
            current_date=self._today,
            season=season or category.replace("_", " ").title(),
            seasonal_category=category,
            seasonal_score=int(seasonal_score),
            lead_time_score=int(lead_time_score),
            evergreen_score=int(evergreen_score),
            production_decision=decision,
            reason=reason,
            next_recommended_window=(
                f"{record['production_start']} to {record['production_end']}"
            ),
            is_out_of_season=out_of_season,
            is_evergreen=is_evergreen,
            is_inventory_build=is_inventory_build,
        )

    def _match_category(
        self,
        product_name: str,
        season: str,
        product_type: str,
    ) -> tuple[str, dict[str, Any]]:
        haystack = f"{product_name} {season} {product_type}".casefold()
        seasons = self._config.get("seasons", {})
        for key, record in seasons.items():
            if key == "evergreen":
                continue
            if any(str(keyword).casefold() in haystack for keyword in record.get("keywords", ())):
                return key, record
        return "evergreen", seasons["evergreen"]


def _load_calendar(path: Path) -> dict[str, Any]:
    """Load Aurora's simple YAML calendar without external dependencies."""
    if not path.exists():
        raise FileNotFoundError(path)
    config: dict[str, Any] = {"lead_time_days": {}, "seasons": {}}
    section = ""
    current_season = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", maxsplit=1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            section = line.removesuffix(":").strip()
            continue
        if section == "lead_time_days" and line.startswith("  "):
            key, value = line.strip().split(":", maxsplit=1)
            config["lead_time_days"][key.strip()] = int(value.strip())
        elif section == "seasons" and line.startswith("  ") and not line.startswith("    "):
            current_season = line.strip().removesuffix(":")
            config["seasons"][current_season] = {}
        elif section == "seasons" and current_season and line.startswith("    "):
            key, value = line.strip().split(":", maxsplit=1)
            raw_value = value.strip().strip('"')
            if raw_value.startswith("[") and raw_value.endswith("]"):
                values = [
                    item.strip().strip('"').strip("'")
                    for item in raw_value.removeprefix("[").removesuffix("]").split(",")
                    if item.strip()
                ]
                config["seasons"][current_season][key.strip()] = values
            else:
                config["seasons"][current_season][key.strip()] = raw_value
    return config


def _date_in_window(today: date, start: str, end: str) -> bool:
    start_month, start_day = _parse_month_day(start)
    end_month, end_day = _parse_month_day(end)
    current = (today.month, today.day)
    start_tuple = (start_month, start_day)
    end_tuple = (end_month, end_day)
    if start_tuple <= end_tuple:
        return start_tuple <= current <= end_tuple
    return current >= start_tuple or current <= end_tuple


def _parse_month_day(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{2})-(\d{2})", value.strip())
    if match is None:
        raise ValueError(f"Invalid seasonal window date: {value}")
    return int(match.group(1)), int(match.group(2))
