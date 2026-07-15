"""Tests for Sprint 22 daily dynamic factory."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.local_env import load_local_env  # noqa: E402
from project_aurora.config.profile_loader import ProjectProfileLoader  # noqa: E402
from project_aurora.integrations.etsy.etsy_token_manager import (  # noqa: E402
    EtsyTokenManager,
)
from project_aurora.planning.dynamic_product_planner import (  # noqa: E402
    DynamicProductPlanner,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    READY,
    ProductionQueueManager,
)
from project_aurora.research.dynamic_market_research import (  # noqa: E402
    DynamicMarketResearchEngine,
    DynamicResearchReport,
    MarketSignal,
)
from scripts import run_daily_factory  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def make_signal(index: int) -> MarketSignal:
    return MarketSignal(
        trend_phrase=f"woodland nursery animal {index}",
        product_type="clipart",
        estimated_demand=0.9 - index * 0.005,
        estimated_competition=0.25 + index * 0.005,
        seasonal_timing="90 day window",
        target_customer="parents, teachers, crafters, digital printable buyers",
        recommended_style="Storybook Watercolor",
        keywords=(f"woodland{index}", "nursery", "animal"),
        source="test",
        collected_at=datetime.now(),
        confidence_score=0.9,
    )


class Sprint22DailyFactoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.profile = ProjectProfileLoader().load(
            PROJECT_ROOT / "config" / "projects" / "rainbow_milk_studio.yaml"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_research(self) -> DynamicResearchReport:
        return DynamicResearchReport(
            signals=tuple(make_signal(index) for index in range(1, 7)),
            providers_used=("test",),
            providers_unavailable=(),
        )

    def test_dynamic_candidate_generation_at_least_30(self) -> None:
        queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        planner = DynamicProductPlanner(queue, self.profile)

        candidates = planner.generate_candidates(self.make_research())

        self.assertGreaterEqual(len(candidates), 30)
        self.assertTrue(
            all(candidate.product_type in self.profile.allowed_product_types for candidate in candidates)
        )

    def test_exactly_10_unique_jobs(self) -> None:
        queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        planner = DynamicProductPlanner(queue, self.profile)

        result = planner.plan(self.make_research(), count=10)

        jobs = queue.list_jobs()
        self.assertEqual(len(result.selected), 10)
        self.assertEqual(len(jobs), 10)
        self.assertEqual(len({job.product_name for job in jobs}), 10)
        self.assertTrue(all(job.status == READY for job in jobs))

    def test_historical_duplicate_prevention(self) -> None:
        queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        queue.add_job(
            priority="High",
            product_name="Woodland Nursery Animal 1 Clipart Bundle",
            category="clipart",
            style="Storybook Watercolor",
            seasonal_theme="Evergreen",
            keywords=("woodland",),
            confidence_score=0.9,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=100,
        )
        planner = DynamicProductPlanner(queue, self.profile)

        result = planner.plan(self.make_research(), count=10)

        self.assertIn("Woodland Nursery Animal 1 Clipart Bundle", result.duplicates_rejected)

    def test_provider_unavailable_reporting(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            report = DynamicMarketResearchEngine().run()

        unavailable = {item.provider for item in report.providers_unavailable}
        self.assertIn("Etsy API Signals", unavailable)
        self.assertIn("Google Trends", unavailable)
        self.assertIn("Pinterest Trends", unavailable)
        self.assertTrue(report.providers_used)

    def test_candidate_ranking(self) -> None:
        queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        planner = DynamicProductPlanner(queue, self.profile)
        candidates = planner.generate_candidates(self.make_research())

        ranked = planner.rank_candidates(candidates)

        self.assertGreaterEqual(ranked[0].confidence_score, ranked[-1].confidence_score)

    def test_local_credential_loading(self) -> None:
        env_path = self.base_path / "aurora.local.env"
        env_path.write_text("ETSY_CLIENT_ID=abc\nETSY_SHARED_SECRET=secret\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            loaded = load_local_env(env_path)
            self.assertEqual(os.environ["ETSY_CLIENT_ID"], "abc")
            self.assertIn("ETSY_SHARED_SECRET", loaded)

    def test_token_refresh(self) -> None:
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append(api_request)
            return FakeResponse(
                {
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                }
            )

        with patch.dict(
            os.environ,
            {
                "ETSY_CLIENT_ID": "client",
                "ETSY_REFRESH_TOKEN": "refresh",
            },
            clear=True,
        ):
            result = EtsyTokenManager(
                credential_path=self.base_path / "aurora.local.env",
                urlopen=fake_urlopen,
            ).refresh_if_needed(force=True)
            self.assertEqual(os.environ["ETSY_ACCESS_TOKEN"], "new-access")

        self.assertTrue(result.refreshed)
        self.assertEqual(len(calls), 1)

    def test_scheduler_script_generation_and_lock_behavior(self) -> None:
        runner = (PROJECT_ROOT / "scripts" / "run_daily_factory_scheduled.sh").read_text(
            encoding="utf-8"
        )
        plist = (
            PROJECT_ROOT / "config" / "com.aurora.daily-factory.plist.template"
        ).read_text(encoding="utf-8")

        self.assertIn("daily_factory.lock", runner)
        self.assertIn("--scheduled", runner)
        self.assertIn("StartCalendarInterval", plist)
        self.assertIn("<integer>8</integer>", plist)

    def test_cost_cap_enforcement(self) -> None:
        config_path = self.base_path / "daily_factory.yaml"
        config_path.write_text(
            "\n".join(
                (
                    "enabled: true",
                    "daily_product_count: 10",
                    "max_daily_products: 10",
                    "max_daily_images: 40",
                    "max_estimated_daily_cost: 0.01",
                    "continue_after_failure: true",
                    "require_live_confirmation_for_manual_runs: false",
                    "schedule_hour: 8",
                    "schedule_minute: 0",
                    "timezone: America/New_York",
                )
            ),
            encoding="utf-8",
        )
        with patch.object(run_daily_factory, "PROJECT_ROOT", self.base_path), patch.object(
            run_daily_factory,
            "load_daily_factory_config",
            return_value=run_daily_factory.load_daily_factory_config(config_path),
        ), patch.object(
            run_daily_factory.ImageProviderConfig,
            "from_file",
            return_value=SimpleNamespace(
                provider="openai",
                quality="medium",
                number_of_images=4,
            ),
        ):
            with self.assertRaises(SystemExit):
                run_daily_factory.main(["--count", "10", "--live", "--scheduled"])

    def test_daily_report_and_scheduled_mode_no_confirmation(self) -> None:
        queue_path = self.base_path / "queue.json"
        reports_dir = self.base_path / "daily_reports"
        batch = SimpleNamespace(
            completed=10,
            failed=0,
            draft_ids=("1", "2"),
            images_generated=40,
            downloads_uploaded=40,
            elapsed_time=61.5,
            failure_summary=(),
        )
        with patch.object(run_daily_factory, "QUEUE_PATH", queue_path), patch.object(
            run_daily_factory,
            "REAL_QUEUE_PATH",
            queue_path,
            create=True,
        ), patch.object(
            run_daily_factory,
            "DAILY_REPORTS_DIR",
            reports_dir,
        ), patch.object(
            run_daily_factory,
            "_run_live_batch",
            return_value=batch,
        ), patch(
            "builtins.input",
            side_effect=AssertionError("scheduled mode must not ask"),
        ):
            report = run_daily_factory.run_daily_factory(
                count=10,
                live=True,
                cost_estimate=1.6,
            )

        self.assertEqual(report["products_completed"], 10)
        self.assertEqual(report["ai_disclosure"], "MANUAL_REQUIRED")
        self.assertTrue((reports_dir / f"{report['date']}.json").exists())


if __name__ == "__main__":
    unittest.main()
