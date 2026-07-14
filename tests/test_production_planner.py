"""Tests for Sprint 19 production planning."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.product_planner import ProductPlanner  # noqa: E402
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    COMPLETED,
    FAILED,
    IN_PROGRESS,
    READY,
    ProductionQueueManager,
)
from project_aurora.style_intelligence.style_library_builder import (  # noqa: E402
    StyleLibraryBuilder,
)


def make_research() -> dict[str, object]:
    return {
        "recommendations": (
            {
                "name": "Woodland Baby Animals",
                "category": "Digital Clipart",
                "theme": "Woodland Baby Animals",
                "season": "Evergreen",
                "demand_score": 9,
                "competition_level": "low",
                "revenue_potential": "high",
                "score": 112,
            },
            {
                "name": "Strawberry Birthday Party",
                "category": "Party Printable",
                "theme": "Strawberry Birthday",
                "season": "Summer",
                "demand_score": 9,
                "competition_level": "medium",
                "revenue_potential": "high",
                "score": 107,
            },
            {
                "name": "Fairy Garden Clipart",
                "category": "Digital Clipart",
                "theme": "Fairy Garden",
                "season": "Spring",
                "demand_score": 8,
                "competition_level": "low",
                "revenue_potential": "high",
                "score": 104,
            },
            {
                "name": "Cottagecore Digital Paper",
                "category": "Digital Paper Pack",
                "theme": "Cottagecore Florals",
                "season": "Spring",
                "demand_score": 7,
                "competition_level": "low",
                "revenue_potential": "medium",
                "score": 90,
            },
        )
    }


class ProductionPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.queue_path = Path(self.temp_dir.name) / "queue.json"
        self.ids = iter(
            (
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "00000000-0000-0000-0000-000000000003",
                "00000000-0000-0000-0000-000000000004",
                "00000000-0000-0000-0000-000000000005",
            )
        )
        self.queue = ProductionQueueManager(
            queue_path=self.queue_path,
            id_factory=lambda: next(self.ids),
        )
        self.styles = StyleLibraryBuilder().build_seed_library()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_planner_creates_ranked_persistent_jobs(self) -> None:
        jobs = ProductPlanner(self.queue).plan(
            research_output=make_research(),
            style_output=self.styles,
            top_n=3,
        )

        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0].product_name, "Woodland Baby Animals")
        self.assertEqual(jobs[0].status, READY)
        self.assertEqual(jobs[0].estimated_demand, "High")
        self.assertEqual(jobs[0].estimated_competition, "Low")
        self.assertGreaterEqual(jobs[0].confidence_score, jobs[1].confidence_score)
        self.assertTrue(self.queue_path.exists())
        payload = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["job_count"], 3)
        self.assertEqual(payload["jobs"][0]["product_name"], "Woodland Baby Animals")

    def test_duplicate_prevention_skips_existing_product(self) -> None:
        ProductPlanner(self.queue).plan(
            research_output=make_research(),
            style_output=self.styles,
            top_n=1,
        )

        second_run = ProductPlanner(self.queue).plan(
            research_output=make_research(),
            style_output=self.styles,
            top_n=2,
        )

        self.assertNotIn(
            "Woodland Baby Animals",
            [job.product_name for job in second_run],
        )
        self.assertEqual(len(self.queue.list_jobs()), 3)
        with self.assertRaises(ValueError):
            self.queue.add_job(
                priority="High",
                product_name="woodland baby animals",
                category="Digital Clipart",
                style="Woodland Friends",
                seasonal_theme="Evergreen",
                keywords=("woodland",),
                confidence_score=0.9,
                estimated_competition="Low",
                estimated_demand="High",
                estimated_revenue=150.0,
            )

    def test_status_transitions_persist(self) -> None:
        job = ProductPlanner(self.queue).plan(
            research_output=make_research(),
            style_output=self.styles,
            top_n=1,
        )[0]

        in_progress = self.queue.mark_in_progress(job.id)
        completed = self.queue.mark_completed(job.id)

        self.assertEqual(in_progress.status, IN_PROGRESS)
        self.assertEqual(completed.status, COMPLETED)
        reloaded = ProductionQueueManager(queue_path=self.queue_path)
        self.assertEqual(reloaded.list_jobs()[0].status, COMPLETED)

    def test_mark_failed_and_remove_job(self) -> None:
        job = ProductPlanner(self.queue).plan(
            research_output=make_research(),
            style_output=self.styles,
            top_n=1,
        )[0]

        failed = self.queue.mark_failed(job.id)
        self.assertEqual(failed.status, FAILED)
        self.queue.remove_job(job.id)
        self.assertEqual(self.queue.list_jobs(), ())

    def test_next_ready_job_uses_deterministic_sorting(self) -> None:
        jobs = ProductPlanner(self.queue).plan(
            research_output=make_research(),
            style_output=self.styles,
            top_n=3,
        )
        self.queue.mark_in_progress(jobs[0].id)

        next_job = self.queue.next_ready_job()

        self.assertIsNotNone(next_job)
        self.assertEqual(next_job.product_name, jobs[1].product_name)

    def test_deterministic_sorting_tiebreaks_by_product_name(self) -> None:
        research = {
            "recommendations": (
                {
                    "name": "Beta Clipart",
                    "category": "Digital Clipart",
                    "theme": "Woodland",
                    "season": "Evergreen",
                    "demand_score": 8,
                    "competition_level": "low",
                    "revenue_potential": "high",
                    "score": 100,
                },
                {
                    "name": "Alpha Clipart",
                    "category": "Digital Clipart",
                    "theme": "Woodland",
                    "season": "Evergreen",
                    "demand_score": 8,
                    "competition_level": "low",
                    "revenue_potential": "high",
                    "score": 100,
                },
            )
        }

        jobs = ProductPlanner(self.queue).plan(
            research_output=research,
            style_output=self.styles,
            top_n=2,
        )

        self.assertEqual(
            [job.product_name for job in jobs],
            ["Alpha Clipart", "Beta Clipart"],
        )

    def test_empty_research_input_creates_no_jobs(self) -> None:
        jobs = ProductPlanner(self.queue).plan(
            research_output={"recommendations": ()},
            style_output=self.styles,
            top_n=5,
        )

        self.assertEqual(jobs, ())
        self.assertEqual(self.queue.list_jobs(), ())

    def test_malformed_queue_recovers_as_empty(self) -> None:
        self.queue_path.write_text("{not-json", encoding="utf-8")
        recovered = ProductionQueueManager(
            queue_path=self.queue_path,
            id_factory=lambda: "00000000-0000-0000-0000-000000000099",
        )

        self.assertEqual(recovered.list_jobs(), ())
        recovered.add_job(
            priority="High",
            product_name="Recovered Product",
            category="Digital Clipart",
            style="Storybook Watercolor",
            seasonal_theme="Evergreen",
            keywords=("recovered",),
            confidence_score=0.9,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=100.0,
        )

        payload = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["job_count"], 1)
        self.assertEqual(payload["jobs"][0]["product_name"], "Recovered Product")


if __name__ == "__main__":
    unittest.main()
