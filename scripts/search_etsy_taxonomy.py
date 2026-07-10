"""Search Etsy seller taxonomy nodes for a draft listing taxonomy id."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402

API_BASE_URL = "https://openapi.etsy.com/v3/application"
SELLER_TAXONOMY_PATH = "/seller-taxonomy/nodes"


@dataclass(frozen=True, slots=True)
class TaxonomyMatch:
    """Ranked Etsy taxonomy search result."""

    taxonomy_name: str
    full_taxonomy_path: str
    taxonomy_id: int
    score: int


def load_config_from_environment() -> EtsyConfig:
    """Load Etsy API credentials without saving or printing secrets."""
    client_id = os.getenv("ETSY_CLIENT_ID")
    shared_secret = os.getenv("ETSY_SHARED_SECRET")
    access_token = os.getenv("ETSY_ACCESS_TOKEN")
    missing: list[str] = []
    if not client_id:
        missing.append("ETSY_CLIENT_ID")
    if not shared_secret:
        missing.append("ETSY_SHARED_SECRET")
    if not access_token:
        missing.append("ETSY_ACCESS_TOKEN")
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return EtsyConfig(
        mode="live",
        client_id=str(client_id),
        shared_secret=str(shared_secret),
        access_token=str(access_token),
        api_base_url=API_BASE_URL,
    )


def fetch_taxonomy_nodes(client: EtsyClient) -> list[dict[str, Any]]:
    """Fetch Etsy seller taxonomy nodes."""
    payload = client.get_json(SELLER_TAXONOMY_PATH)
    results = payload.get("results", [])
    if isinstance(results, list):
        return [node for node in results if isinstance(node, dict)]
    if isinstance(results, dict):
        return [results]
    raise RuntimeError("Etsy taxonomy response did not include results.")


def search_taxonomy(
    search_phrase: str,
    taxonomy_nodes: list[dict[str, Any]],
) -> list[TaxonomyMatch]:
    """Return taxonomy matches ranked by relevance."""
    phrase = search_phrase.strip().casefold()
    if not phrase:
        raise RuntimeError("Search phrase is required.")

    matches: list[TaxonomyMatch] = []
    for node, path in _iter_nodes(taxonomy_nodes, parent_path=()):
        name = _node_name(node)
        taxonomy_id = _node_id(node)
        if not name or taxonomy_id is None:
            continue
        full_path = _full_path(node, path + (name,))
        score = _score_match(phrase, name, full_path)
        if score > 0:
            matches.append(
                TaxonomyMatch(
                    taxonomy_name=name,
                    full_taxonomy_path=full_path,
                    taxonomy_id=taxonomy_id,
                    score=score,
                )
            )

    return sorted(
        matches,
        key=lambda match: (
            -match.score,
            len(match.full_taxonomy_path),
            match.full_taxonomy_path.casefold(),
        ),
    )


def _iter_nodes(
    nodes: list[dict[str, Any]],
    parent_path: tuple[str, ...],
) -> list[tuple[dict[str, Any], tuple[str, ...]]]:
    flattened: list[tuple[dict[str, Any], tuple[str, ...]]] = []
    for node in nodes:
        name = _node_name(node)
        flattened.append((node, parent_path))
        child_path = parent_path + ((name,) if name else ())
        children = node.get("children", [])
        if isinstance(children, list):
            child_nodes = [
                child for child in children if isinstance(child, dict)
            ]
            flattened.extend(_iter_nodes(child_nodes, child_path))
    return flattened


def _node_name(node: dict[str, Any]) -> str:
    return str(node.get("name") or node.get("taxonomy_name") or "").strip()


def _node_id(node: dict[str, Any]) -> int | None:
    raw_id = (
        node.get("id")
        or node.get("taxonomy_id")
        or node.get("seller_taxonomy_id")
    )
    if raw_id is None:
        return None
    return int(raw_id)


def _full_path(node: dict[str, Any], fallback_path: tuple[str, ...]) -> str:
    raw_path = (
        node.get("full_path")
        or node.get("path")
        or node.get("taxonomy_path")
        or node.get("full_taxonomy_path")
    )
    if isinstance(raw_path, list):
        parts = [str(part).strip() for part in raw_path if str(part).strip()]
        if parts:
            return " > ".join(parts)
    if isinstance(raw_path, str) and raw_path.strip():
        return raw_path.strip()
    return " > ".join(fallback_path)


def _score_match(phrase: str, name: str, full_path: str) -> int:
    name_text = name.casefold()
    path_text = full_path.casefold()
    tokens = [token for token in phrase.split() if token]
    score = 0
    if phrase == name_text:
        score += 100
    if phrase in name_text:
        score += 75
    if phrase in path_text:
        score += 50
    score += sum(10 for token in tokens if token in name_text)
    score += sum(4 for token in tokens if token in path_text)
    return score


def find_best_match(search_phrase: str, client: EtsyClient) -> TaxonomyMatch:
    """Fetch taxonomy nodes and return the highest ranked match."""
    matches = search_taxonomy(search_phrase, fetch_taxonomy_nodes(client))
    if not matches:
        raise RuntimeError(f"No Etsy taxonomy matches found for: {search_phrase}")
    return matches[0]


def main(argv: list[str] | None = None) -> None:
    """Run Etsy seller taxonomy lookup from the command line."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or not " ".join(args).strip():
        print("Error")
        print('Usage: python3.14 scripts/search_etsy_taxonomy.py "party printable"')
        raise SystemExit(1)

    try:
        config = load_config_from_environment()
        client = EtsyClient(config=config)
        match = find_best_match(" ".join(args), client)
    except RuntimeError as error:
        print("Error")
        print(error)
        raise SystemExit(1) from error

    print("Taxonomy Name")
    print(match.taxonomy_name)
    print("Full Taxonomy Path")
    print(match.full_taxonomy_path)
    print("Taxonomy ID")
    print(match.taxonomy_id)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Cancelled.")
        sys.exit(130)
