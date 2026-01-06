#!/usr/bin/env python3
"""
OpenRouter Free Tools Pool Generator for LiteLLM Proxy

This script generates a smart, stable pool of free OpenRouter models that support
tool calling, for use with LiteLLM proxy's load balancing and fallback features.

Features:
- Filters for tool-capable free models only
- Scores models by provider reputation, context length, and agentic keywords
- Applies hysteresis to prevent daily PR churn
- Generates deterministic YAML output
- Respects a blocklist for known-bad models

Scoring factors (in order of importance):
- Provider reputation: Tier 1 (+30): google, meta-llama, qwen, mistralai
                       Tier 2 (+15): nvidia, deepseek, openai, anthropic, microsoft
                       Tier 3 (+10): cohere, databricks, amazon, ai21, xiaomi
- Context length: log2(context) * 10 (e.g., 128k = ~170 points)
- Keyword boosts: coder (+20), devstral (+20), agent (+15), instruct (+5)
- Keyword penalties:
    - Stability: preview (-10), alpha (-10), beta (-5), exp (-5)
    - Size: nano (-15), mini (-15), tiny (-15), micro (-15), small (-5)
- Parameter count: models with <20B parameters get -20 penalty

Usage:
    python generate_openrouter_pool.py [--apply] [--dry-run] [--pool-size N]

Options:
    --apply      Write changes to values.yaml (default: just print diff)
    --dry-run    Only fetch and score models, don't compare or write
    --pool-size  Number of models in the primary pool (default: 10)
"""

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any

import requests

# Configuration
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
VALUES_YAML_PATH = Path(__file__).parent.parent.parent / "apps/selfhosted/litellm/values.yaml"
BLOCKLIST_PATH = Path(__file__).parent / "openrouter_blocklist.txt"

# Pool configuration
DEFAULT_POOL_SIZE = 10
MIN_CONTEXT_LENGTH = 16384  # 16k minimum

# Weight assignment by rank (1-indexed)
WEIGHT_BY_RANK = {
    1: 6,
    2: 6,
    3: 3,
    4: 3,
    5: 3,
    6: 1,
    7: 1,
    8: 1,
    9: 1,
    10: 1,
}

# Provider reputation tiers (bonus points by provider/org)
# Based on model quality, reliability, and community adoption
PROVIDER_REPUTATION = {
    # Tier 1: Top-tier providers with proven track record
    "google": 30,
    "meta-llama": 30,
    "qwen": 30,
    "mistralai": 30,
    # Tier 2: Strong providers with good models
    "nvidia": 15,
    "deepseek": 15,
    "openai": 15,
    "anthropic": 15,
    "microsoft": 15,
    # Tier 3: Emerging or specialized providers
    "cohere": 10,
    "databricks": 10,
    "amazon": 10,
    "ai21": 10,
    "xiaomi": 10,
}

# Scoring keywords (applied to model name/id)
BOOST_KEYWORDS = {
    "coder": 20,
    "devstral": 20,
    "agent": 15,
    "instruct": 5,  # Instruct-tuned models follow tool-calling better
}

PENALTY_KEYWORDS = {
    # Stability concerns
    "preview": 10,
    "alpha": 10,
    "beta": 5,
    "exp": 5,
    # Smaller/weaker model variants
    "nano": 15,
    "mini": 15,
    "tiny": 15,
    "micro": 15,
    "small": 5,
}

# Minimum parameter count threshold (in billions)
# Models below this get a penalty
MIN_PARAM_BILLIONS = 20
SMALL_PARAM_PENALTY = 20

# Hysteresis: minimum overlap percentage with existing pool
HYSTERESIS_MIN_OVERLAP = 0.7

# BEGIN/END markers in values.yaml
BEGIN_MARKER = "# BEGIN GENERATED OPENROUTER POOL"
END_MARKER = "# END GENERATED OPENROUTER POOL"


def load_blocklist() -> set[str]:
    """Load the blocklist of model IDs to exclude."""
    if not BLOCKLIST_PATH.exists():
        return set()

    blocklist = set()
    with open(BLOCKLIST_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                blocklist.add(line.lower())
    return blocklist


def fetch_openrouter_models() -> list[dict[str, Any]]:
    """Fetch all models from OpenRouter API."""
    response = requests.get(OPENROUTER_MODELS_URL, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("data", [])


def is_free_model(model: dict[str, Any]) -> bool:
    """Check if a model has a free variant available."""
    model_id = model.get("id", "")

    # Check if model ID ends with :free
    if model_id.endswith(":free"):
        return True

    # Check pricing - both input and output should be 0 or very close
    pricing = model.get("pricing", {})
    prompt_price = float(pricing.get("prompt", "1") or "1")
    completion_price = float(pricing.get("completion", "1") or "1")

    return prompt_price == 0 and completion_price == 0


def supports_tools(model: dict[str, Any]) -> bool:
    """Check if a model supports tool/function calling."""
    # Check supported_parameters
    supported_params = model.get("supported_parameters", [])
    if "tools" in supported_params or "tool_choice" in supported_params:
        return True

    # Check architecture/capabilities
    arch = model.get("architecture", {})
    if arch.get("tool_use"):
        return True

    # Check top_provider info
    top_provider = model.get("top_provider", {})
    if top_provider.get("supports_tool_parameters"):
        return True

    return False


def get_context_length(model: dict[str, Any]) -> int:
    """Get the context length of a model."""
    return model.get("context_length", 0)


def get_provider(model_id: str) -> str:
    """Extract the provider/org from a model ID (e.g., 'google' from 'google/gemini-2.0-flash:free')."""
    parts = model_id.split("/")
    if len(parts) >= 1:
        return parts[0].lower()
    return ""


def score_model(model: dict[str, Any]) -> float:
    """
    Score a model for ranking.

    Higher scores = better candidates for the pool.

    Scoring factors:
    - Provider reputation (tier-based bonus)
    - Context length (log-scaled)
    - Keyword boosts (coder, agent, instruct, etc.)
    - Keyword penalties (preview, alpha, nano, etc.)
    - Parameter count penalty (models <20B get penalized)
    """
    model_id = model.get("id", "").lower()
    score = 0.0

    # Provider reputation bonus
    provider = get_provider(model_id)
    score += PROVIDER_REPUTATION.get(provider, 0)

    # Context length bonus (log-scaled)
    context_length = get_context_length(model)
    if context_length > 0:
        score += math.log2(context_length) * 10

    # Keyword boosts
    for keyword, boost in BOOST_KEYWORDS.items():
        if keyword in model_id:
            score += boost

    # Keyword penalties
    for keyword, penalty in PENALTY_KEYWORDS.items():
        if keyword in model_id:
            score -= penalty

    # Parameter count penalty for small models
    # Matches patterns like: -7b, -4b, -9b, -12b, 70b, 120b
    param_match = re.search(r"[/-](\d+)b", model_id)
    if param_match:
        params = int(param_match.group(1))
        if params < MIN_PARAM_BILLIONS:
            score -= SMALL_PARAM_PENALTY

    return score


def normalize_model_id(model_id: str) -> str:
    """
    Normalize a model ID for consistent comparison.

    Strips :free suffix and converts to lowercase.
    """
    model_id = model_id.lower()
    if model_id.endswith(":free"):
        model_id = model_id[:-5]
    return model_id


def extract_current_pool(values_content: str) -> list[str]:
    """
    Extract current model IDs from the generated section of values.yaml.

    Returns normalized model IDs (without :free suffix, lowercase).
    """
    current_pool = []

    # Find the generated section
    begin_idx = values_content.find(BEGIN_MARKER)
    end_idx = values_content.find(END_MARKER)

    if begin_idx == -1 or end_idx == -1:
        return current_pool

    generated_section = values_content[begin_idx:end_idx]

    # Extract model IDs using regex
    # Looking for: model: openrouter/vendor/model:free
    pattern = r"model:\s*openrouter/([^\s]+)"
    matches = re.findall(pattern, generated_section)

    for match in matches:
        normalized = normalize_model_id(match)
        current_pool.append(normalized)

    return current_pool


def apply_hysteresis(
    candidates: list[dict[str, Any]],
    current_pool: list[str],
    pool_size: int,
) -> list[dict[str, Any]]:
    """
    Apply hysteresis to prefer keeping existing pool members.

    This reduces PR churn when rankings fluctuate slightly.
    """
    if not current_pool:
        # No existing pool, just return top candidates
        return candidates[:pool_size]

    # Separate candidates into "already in pool" and "new"
    in_pool = []
    not_in_pool = []

    for candidate in candidates:
        normalized_id = normalize_model_id(candidate["id"])
        if normalized_id in current_pool:
            in_pool.append(candidate)
        else:
            not_in_pool.append(candidate)

    # Calculate how many we want to keep from existing pool
    min_keep = int(pool_size * HYSTERESIS_MIN_OVERLAP)

    # Build final pool
    final_pool = []

    # First, keep existing pool members that are still eligible (up to min_keep)
    for candidate in in_pool[:min_keep]:
        final_pool.append(candidate)

    # Fill remaining slots from the top of all candidates (respecting order)
    for candidate in candidates:
        if len(final_pool) >= pool_size:
            break
        if candidate not in final_pool:
            final_pool.append(candidate)

    # Re-sort by score for consistent weight assignment
    final_pool.sort(key=lambda m: (-m["_score"], m["id"]))

    return final_pool[:pool_size]


def generate_pool_yaml(pool: list[dict[str, Any]]) -> str:
    """Generate the YAML block for the model pool."""
    lines = [
        BEGIN_MARKER,
        "# This section is auto-updated by .github/workflows/litellm-openrouter-pool.yaml",
        "# Manual edits will be overwritten. To block a model, add it to scripts/litellm/openrouter_blocklist.txt",
    ]

    for rank, model in enumerate(pool, 1):
        model_id = model["id"]
        # Ensure :free suffix
        if not model_id.endswith(":free"):
            model_id = f"{model_id}:free"

        weight = WEIGHT_BY_RANK.get(rank, 1)

        lines.append(f"- model_name: primary")
        lines.append(f"  litellm_params:")
        lines.append(f"    model: openrouter/{model_id}")
        lines.append(f"    api_key: os.environ/OPENROUTER_API_KEY")
        lines.append(f"    drop_params: true")
        lines.append(f"    weight: {weight}")

    lines.append(END_MARKER)

    return "\n".join(lines)


def update_values_yaml(values_content: str, new_pool_yaml: str) -> str:
    """Replace the generated section in values.yaml with new pool."""
    # Find the markers
    begin_idx = values_content.find(BEGIN_MARKER)
    end_idx = values_content.find(END_MARKER)

    if begin_idx == -1 or end_idx == -1:
        raise ValueError(
            f"Could not find {BEGIN_MARKER} and {END_MARKER} markers in values.yaml"
        )

    # Find the proper indentation by looking at the line with BEGIN_MARKER
    line_start = values_content.rfind("\n", 0, begin_idx) + 1
    indent = begin_idx - line_start

    # Indent the new pool YAML
    indented_lines = []
    for line in new_pool_yaml.split("\n"):
        if line.strip():
            indented_lines.append(" " * indent + line)
        else:
            indented_lines.append("")
    indented_pool_yaml = "\n".join(indented_lines)

    # Replace the section
    end_of_marker = end_idx + len(END_MARKER)
    new_content = (
        values_content[:line_start] + indented_pool_yaml + values_content[end_of_marker:]
    )

    return new_content


def main():
    parser = argparse.ArgumentParser(
        description="Generate OpenRouter free tools pool for LiteLLM"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to values.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only fetch and score models, don't compare or write",
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        default=DEFAULT_POOL_SIZE,
        help=f"Number of models in the primary pool (default: {DEFAULT_POOL_SIZE})",
    )
    args = parser.parse_args()

    print("Fetching OpenRouter models...")
    all_models = fetch_openrouter_models()
    print(f"  Found {len(all_models)} total models")

    # Load blocklist
    blocklist = load_blocklist()
    if blocklist:
        print(f"  Loaded {len(blocklist)} blocked models")

    # Filter candidates
    print("Filtering for free, tool-capable models...")
    candidates = []
    for model in all_models:
        model_id = model.get("id", "")
        normalized_id = normalize_model_id(model_id)

        # Skip blocked models
        if normalized_id in blocklist:
            continue

        # Must be free
        if not is_free_model(model):
            continue

        # Must support tools
        if not supports_tools(model):
            continue

        # Must have minimum context length
        if get_context_length(model) < MIN_CONTEXT_LENGTH:
            continue

        # Score the model
        model["_score"] = score_model(model)
        candidates.append(model)

    print(f"  Found {len(candidates)} eligible candidates")

    if not candidates:
        print("ERROR: No eligible models found!")
        sys.exit(1)

    # Sort by score (descending), then by ID (ascending) for determinism
    candidates.sort(key=lambda m: (-m["_score"], m["id"]))

    # Print top candidates
    print("\nTop candidates:")
    for i, model in enumerate(candidates[:15], 1):
        ctx = get_context_length(model)
        print(f"  {i:2}. {model['id']:<50} ctx={ctx:>8} score={model['_score']:.1f}")

    if args.dry_run:
        print("\n--dry-run specified, stopping here.")
        return

    # Load current values.yaml
    if not VALUES_YAML_PATH.exists():
        print(f"ERROR: {VALUES_YAML_PATH} not found!")
        sys.exit(1)

    values_content = VALUES_YAML_PATH.read_text()

    # Extract current pool for hysteresis
    current_pool = extract_current_pool(values_content)
    if current_pool:
        print(f"\nCurrent pool has {len(current_pool)} models")

    # Apply hysteresis and select final pool
    final_pool = apply_hysteresis(candidates, current_pool, args.pool_size)

    print(f"\nSelected pool ({len(final_pool)} models):")
    for i, model in enumerate(final_pool, 1):
        weight = WEIGHT_BY_RANK.get(i, 1)
        print(f"  {i:2}. {model['id']:<50} weight={weight}")

    # Generate new YAML
    new_pool_yaml = generate_pool_yaml(final_pool)

    # Calculate changes
    new_pool_ids = {normalize_model_id(m["id"]) for m in final_pool}
    current_pool_set = set(current_pool)

    added = new_pool_ids - current_pool_set
    removed = current_pool_set - new_pool_ids

    if added or removed:
        print("\nChanges:")
        for model_id in sorted(added):
            print(f"  + {model_id}")
        for model_id in sorted(removed):
            print(f"  - {model_id}")
    else:
        print("\nNo changes to pool composition.")

    # Update values.yaml content
    try:
        new_values_content = update_values_yaml(values_content, new_pool_yaml)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if new_values_content == values_content:
        print("No changes needed.")
        return

    if args.apply:
        VALUES_YAML_PATH.write_text(new_values_content)
        print(f"\nUpdated {VALUES_YAML_PATH}")
    else:
        print("\nRun with --apply to write changes.")


if __name__ == "__main__":
    main()
