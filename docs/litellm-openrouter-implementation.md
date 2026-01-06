# LiteLLM OpenRouter Free-First Implementation

## Overview

This document details the implementation of a "smart dynamic" OpenRouter free-first routing strategy for LiteLLM proxy, with automatic daily pool updates via GitHub Actions.

## Goals

- **Free-first**: Always try free OpenRouter models first
- **Tool-safe**: Only include models that support tool calling
- **Quality-biased**: Rank models by context length, agentic keywords, etc.
- **Stable**: Hysteresis prevents daily PR churn
- **Spill to paid**: Fall back to `openrouter/openai/gpt-5-mini` on errors/429s

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Request                          │
│                        model: "primary"                         │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LiteLLM Proxy                              │
│  routing_strategy: weighted-pick                                │
│  allowed_fails: 2 │ cooldown_time: 120s                         │
└─────────────────────────────────────────────────────────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │                                     │
              ▼                                     ▼
┌─────────────────────────────┐     ┌─────────────────────────────┐
│     "primary" Pool          │     │      "paid-tools"           │
│   (10 free tool-capable)    │     │   (fallback on error/429)   │
│                             │     │                             │
│  - openrouter/...:free (w6) │     │  openrouter/openai/gpt-5-mini│
│  - openrouter/...:free (w6) │     │                             │
│  - openrouter/...:free (w3) │     │                             │
│  - ... (10 total)           │     │                             │
└─────────────────────────────┘     └─────────────────────────────┘
```

## Components

### 1. ExternalSecret Update
**File**: `apps/selfhosted/litellm/manifests/litellm-credentials.externalsecret.yaml`

Add:
- `OPENROUTER_API_KEY` from Bitwarden key `openrouter_api_key`

### 2. LiteLLM Proxy Config Update
**File**: `apps/selfhosted/litellm/values.yaml`

Changes:
- Remove all `github_copilot/*` model entries
- Remove `GITHUB_COPILOT_TOKEN_DIR` env var
- Remove `github-copilot-tokens` persistence
- Add `primary` pool (10 free tool-capable models)
- Add `paid-tools` fallback model
- Update `litellm_settings` with routing tricks:
  - `routing_strategy: weighted-pick`
  - `allowed_fails: 2`
  - `cooldown_time: 120`
  - `fallbacks: [{"primary": ["paid-tools"]}]`
  - `request_timeout: 120` (reduced from 600)

### 3. Pool Generator Script
**File**: `scripts/litellm/generate_openrouter_pool.py`

A Python script that:
1. Fetches OpenRouter model catalog via API
2. Filters for tool-capable free models (context >= 16k)
3. Scores and ranks candidates
4. Applies hysteresis (>=70% overlap with existing pool)
5. Outputs deterministic YAML

**Supporting files**:
- `scripts/litellm/openrouter_blocklist.txt` - Models to never include
- `scripts/litellm/requirements.txt` - Python dependencies

### 4. GitHub Action
**File**: `.github/workflows/litellm-openrouter-pool.yaml`

Daily cron job that:
1. Runs the generator script
2. If changes detected, opens a PR
3. PR body includes added/removed models

## Implementation Steps

### Step 1: Add OpenRouter Secret
Update ExternalSecret to include `OPENROUTER_API_KEY`.

### Step 2: Update LiteLLM Values
Replace the entire LiteLLM config:
- Remove GitHub Copilot references
- Add OpenRouter model pool
- Configure routing/fallbacks

### Step 3: Create Generator Script
Add the Python script with:
- OpenRouter API integration
- Filtering logic (tools + free + context)
- Scoring algorithm
- Hysteresis for stability
- YAML generation

### Step 4: Add Blocklist File
Create empty blocklist for future use.

### Step 5: Add GitHub Workflow
Create daily cron workflow for automatic pool updates.

### Step 6: Lint and Verify
Run `task lint` to ensure YAML formatting.

## Model Selection Algorithm

### Hard Filters (must pass all)
1. `tools` in supported_parameters
2. Free variant available (`:free` suffix or $0 pricing)
3. Context length >= 16,384 tokens
4. Text/chat capable (not image-only)

### Scoring (higher = better)
```
score = (
    log2(context_length) * 10                    # Context bonus
    + 20 if "coder" in id                        # Agentic keyword boost
    + 20 if "devstral" in id
    + 15 if "agent" in id
    + 10 if "qwen" in id                         # Known good for tools
    + 10 if "gemini" in id
    - 5 if "exp" in id                           # Experimental penalty
    - 5 if "preview" in id
)
```

### Hysteresis Rules
- Load existing pool from `values.yaml`
- If a model is still eligible, prefer keeping it
- Only replace models that:
  - Are no longer eligible (removed/changed on OpenRouter)
  - Fall significantly below new candidates in score
- Target: >=70% overlap between runs when possible

### Weight Assignment
Based on final rank (1-10):
- Rank 1-2: weight 6
- Rank 3-5: weight 3
- Rank 6-10: weight 1

## LiteLLM Proxy Settings ("The Tricks")

```yaml
litellm_settings:
  drop_params: true              # Essential for cross-model compatibility
  num_retries: 3                 # Retry failed requests
  request_timeout: 120           # Agent-friendly timeout
  routing_strategy: weighted-pick # Use weights for load balancing
  allowed_fails: 2               # Cooldown after 2 failures
  cooldown_time: 120             # 2 minute cooldown for failing models
  fallbacks:
    - primary:
        - paid-tools            # Spill to paid on error/429
```

## File Structure After Implementation

```
home-ops/
├── .github/
│   └── workflows/
│       ├── renovate.yaml (existing)
│       └── litellm-openrouter-pool.yaml (new)
├── apps/
│   └── selfhosted/
│       └── litellm/
│           ├── config.yaml (unchanged)
│           ├── values.yaml (updated)
│           └── manifests/
│               └── litellm-credentials.externalsecret.yaml (updated)
├── scripts/
│   └── litellm/
│       ├── generate_openrouter_pool.py (new)
│       ├── openrouter_blocklist.txt (new)
│       └── requirements.txt (new)
└── docs/
    └── litellm-openrouter-implementation.md (this file)
```

## Bitwarden Secret Requirements

The following secret must exist in Bitwarden before deployment:

| Secret Key | Bitwarden Item Name | Description |
|------------|---------------------|-------------|
| `OPENROUTER_API_KEY` | `openrouter_api_key` | OpenRouter API key for model access |

## Testing

After deployment:
1. Verify LiteLLM pod starts successfully
2. Test tool calling via the proxy:
   ```bash
   curl -X POST https://litellm.edgard.org/v1/chat/completions \
     -H "Authorization: Bearer $LITELLM_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "primary",
       "messages": [{"role": "user", "content": "What is 2+2?"}],
       "tools": [{"type": "function", "function": {"name": "calculator", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}}}}]
     }'
   ```
3. Verify fallback by temporarily blocking all free models

## Maintenance

### Adding a model to blocklist
Edit `scripts/litellm/openrouter_blocklist.txt` and add the model ID (one per line):
```
some-vendor/broken-model
another/flaky-model
```

### Manual pool regeneration
```bash
cd scripts/litellm
python generate_openrouter_pool.py --apply
```

### Checking current pool
The pool is visible in `apps/selfhosted/litellm/values.yaml` under the `# BEGIN GENERATED OPENROUTER POOL` marker.

## Rollback

To rollback to manual model selection:
1. Disable the GitHub Action (delete or set `workflow_dispatch` only)
2. Manually edit `apps/selfhosted/litellm/values.yaml` with desired models
3. Remove the `# BEGIN/END GENERATED` markers if you want full manual control
