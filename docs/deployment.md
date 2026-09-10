# Deployment platforms

The code calls the Anthropic API by default. Each runtime path has one place where a
deployment points it at DeepSeek, GCP Vertex AI, AWS Bedrock, Microsoft Foundry, or an
in-house gateway instead. Everything here applies to both roles; the examples use the
shopping names, and `MerchantAgent`, `merchant_agent_sdk`, and
`merchant-agent/managed-agents/` substitute one for one.

## Support matrix

| Path | Anthropic API | DeepSeek | GCP Vertex AI | AWS Bedrock | Microsoft Foundry | In-house gateway |
|---|---|---|---|---|---|---|
| Messages API runtimes | Yes | Yes | Yes | Yes | Yes | Yes |
| Agent SDK runtimes | Yes | Yes | Yes | Yes | Yes | Yes |
| Managed Agents | Yes | No | No | No¹ | No | Yes² |
| Merchant analysis, hosted code execution | Yes | No | No | No | Yes³ | No |
| Merchant analysis, `execute_analysis_query` | Yes | Yes | Yes | Yes | Yes | Yes |

How each path selects the platform:

| Path | Where set | Anthropic API | DeepSeek | GCP Vertex AI | AWS Bedrock | Microsoft Foundry | In-house gateway |
|---|---|---|---|---|---|---|---|
| Messages API runtimes | `client=` on the agent | default | `AsyncAnthropic(base_url="https://api.deepseek.com/anthropic", api_key=...)`; the demo APIs build this from `DEEPSEEK_API_KEY` | `AsyncAnthropicVertex` | `AsyncAnthropicBedrockMantle` or `AsyncAnthropicBedrock` | `AsyncAnthropicFoundry` | `AsyncAnthropic(base_url=..., auth_token=...)` |
| Agent SDK runtimes | `options.env` | default | `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` | `CLAUDE_CODE_USE_VERTEX=1` | `CLAUDE_CODE_USE_BEDROCK=1` or `CLAUDE_CODE_USE_MANTLE=1` | `CLAUDE_CODE_USE_FOUNDRY=1` | `ANTHROPIC_BASE_URL` |
| Managed Agents | `ANTHROPIC_API_URL` for the deploy script | default | — | — | — | — | `ANTHROPIC_API_URL` |

¹ See the AWS note below. ² Through a pass-through proxy for the deploy script and session endpoints; see
"Managed Agents: the endpoint". ³ Foundry deployments hosted on Anthropic
only.

The two analysis rows apply to merchant deployments with `enable_analysis` on. Hosted code
execution (`analysis_use_code_execution`) mounts the `code_execution_20260120` server tool,
which the Anthropic API serves; a Foundry deployment hosted on Anthropic also serves it.
`MerchantBackend.execute_analysis_query` runs in your infrastructure and returns an
ordinary tool result, so it works everywhere. The retail example uses the query method and
mounts the sandbox only when `MERCHANT_ANALYSIS_CODE_EXECUTION=1` is set.

AWS note: Managed Agents runs on Anthropic-operated infrastructure, so it has no Vertex,
Bedrock, or Foundry variant. On AWS it is available through
[Claude Platform on AWS](https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws),
which serves the same `/v1` endpoints with AWS authentication, an `anthropic-workspace-id`
header, and first-party model ids. The deploy script sends neither; follow the platform
guide for that route.

## Model ids

The model is a string in the config. Each role config has `model` and `memory_model`; the
merchant config adds `analysis_model`. The SDK runtimes copy the model into their options,
and the manifests set it in `agent.yaml`. Nothing else reads the string, so a platform move
is a config change. Id grammar differs by platform; confirm against your
platform's catalog.

| Field | Repo default | DeepSeek | Anthropic API, gateways | GCP Vertex AI | AWS Bedrock (Mantle) | AWS Bedrock (Invoke API) | Microsoft Foundry |
|---|---|---|---|---|---|---|---|
| Shopping `model` | `deepseek-v4-flash` | `deepseek-v4-flash` | `claude-sonnet-5` | `claude-sonnet-5` | `anthropic.<SERVED_MODEL>` | `<INFERENCE_PROFILE_ID>` | `claude-sonnet-5` |
| Merchant `model` | `deepseek-v4-pro` | `deepseek-v4-pro` | `claude-opus-5` | `claude-opus-5` | `anthropic.<SERVED_MODEL>` | `<INFERENCE_PROFILE_ID>` | `claude-opus-5` |
| `memory_model` | `deepseek-v4-flash` | `deepseek-v4-flash` | `claude-haiku-4-5-20251001` | `claude-haiku-4-5@20251001` | `anthropic.<SERVED_MODEL>` | `<INFERENCE_PROFILE_ID>` | `claude-haiku-4-5` |

- DeepSeek serves an unrecognized id with `deepseek-v4-flash` instead of rejecting it, so
  a typo downgrades the model quietly; confirm the id when a reply looks weaker than
  expected.
- Vertex writes dated snapshots with `@`.
- Bedrock has two endpoints. Mantle speaks the Messages API and takes dateless
  `anthropic.` ids from its own lineup; the Invoke API takes inference-profile ids from your account's catalog
  (region-prefixed, dated, `-v1:0` suffixed).
- Foundry takes the name of a deployment in your resource; the values above are the
  defaults, which match the dateless first-party ids.
- Managed Agents takes first-party ids.
- All three model fields go through the same client, so all three must exist on the
  platform it targets.

## Messages API runtimes: the `client` argument

`ShoppingAgent` and `MerchantAgent` take an optional `client`. Without one they construct
`AsyncAnthropic`, which reads `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and
`ANTHROPIC_BASE_URL` from the environment; exporting the last two points the example APIs
at a gateway. With one, every call uses it: the turn loop (`messages.stream`), memory
extraction, and the analysis delegate (`messages.create`). Any async client in the
`anthropic` package fits. The parameter is annotated `AsyncAnthropic`, so a type checker
needs a `cast` for the platform classes.

```python
from pathlib import Path

from anthropic import (
    AsyncAnthropic,
    AsyncAnthropicBedrockMantle,
    AsyncAnthropicFoundry,
    AsyncAnthropicVertex,
)
from shopping_agent import ShoppingAgentConfig
from shopping_agent_runtime import ShoppingAgent

common = dict(backend=your_backend, skills_dir=Path("shopping-agent/skills"))

# GCP Vertex AI: pip install "anthropic[vertex]"; Application Default Credentials.
agent = ShoppingAgent(
    **common,
    config=ShoppingAgentConfig(memory_model="claude-haiku-4-5@20251001"),
    client=AsyncAnthropicVertex(project_id="your-project", region="global"),
)

# AWS Bedrock, Mantle endpoint: the standard AWS credential chain.
agent = ShoppingAgent(
    **common,
    config=ShoppingAgentConfig(
        model="anthropic.your-served-model", memory_model="anthropic.claude-haiku-4-5"
    ),
    client=AsyncAnthropicBedrockMantle(aws_region="us-east-1"),
)

# Microsoft Foundry: an Azure API key, or azure_ad_token_provider= for Entra ID.
agent = ShoppingAgent(
    **common,
    config=ShoppingAgentConfig(memory_model="claude-haiku-4-5"),
    client=AsyncAnthropicFoundry(resource="your-resource", api_key="your-azure-key"),
)

# DeepSeek: its endpoint serves the Messages API. The demo APIs construct exactly this
# from DEEPSEEK_API_KEY; a standalone deployment passes it explicitly.
agent = ShoppingAgent(
    **common,
    client=AsyncAnthropic(
        base_url="https://api.deepseek.com/anthropic", api_key="your-deepseek-key"
    ),
)

# In-house gateway: it must serve /v1/messages with SSE streaming.
agent = ShoppingAgent(
    **common,
    client=AsyncAnthropic(base_url="https://llm-gateway.internal.example", auth_token="your-token"),
)
```

DeepSeek speaks the same request vocabulary — tools, `tool_choice`, streaming, system
blocks, multi-turn tool results, `thinking` with `output_config.effort` — with four
differences. `cache_control` markers are ignored: DeepSeek caches repeated prefixes on
disk on its own and bills a cache read far below a miss, so `rolling_conversation_cache`
pays off without them. Thinking is always on there; `thinking_effort` pins the effort on
a low/high/max scale, and temperature is ignored while thinking runs. The hosted
code-execution tool is not served, so `analysis_use_code_execution` stays off while
`execute_analysis_query` carries the analysis delegate; the web-search server tool is
served. Rate limits meter account-level concurrency, not requests per minute.

The packages declare `anthropic>=0.91`, the release that adds `AsyncAnthropicBedrockMantle`,
the newest of the client classes above.

## Agent SDK runtimes: the CLI environment

The SDK runtimes construct no HTTP client. `claude-agent-sdk` starts the Claude Code CLI,
and the CLI selects the platform from its environment. `make_options()` returns
`(options, toolset)`; add the platform variables to `options.env` before opening the client.
The SDK overlays `env` on the inherited environment, so only the platform variables need
listing.

```python
from claude_agent_sdk import ClaudeSDKClient
from shopping_agent_sdk import make_options

options, toolset = make_options()
options.env.update({"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"})
options.model = "us.anthropic.claude-sonnet-5"
async with ClaudeSDKClient(options=options) as client:
    ...
```

| Target | Required | Credentials | Model ids | Optional |
|---|---|---|---|---|
| AWS Bedrock, Invoke API | `CLAUDE_CODE_USE_BEDROCK=1` | AWS standard chain | inference-profile ids | `ANTHROPIC_BEDROCK_BASE_URL` |
| AWS Bedrock, Mantle | `CLAUDE_CODE_USE_MANTLE=1` | AWS standard chain | `anthropic.` ids | `ANTHROPIC_BEDROCK_MANTLE_BASE_URL`, `CLAUDE_CODE_SKIP_MANTLE_AUTH`⁴ |
| GCP Vertex AI | `CLAUDE_CODE_USE_VERTEX=1`, `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION` | Application Default Credentials | `@`-dated ids | `ANTHROPIC_VERTEX_BASE_URL` |
| Microsoft Foundry | `CLAUDE_CODE_USE_FOUNDRY=1`, `ANTHROPIC_FOUNDRY_RESOURCE` or `ANTHROPIC_FOUNDRY_BASE_URL` | `ANTHROPIC_FOUNDRY_API_KEY`, or Entra ID via the Azure default chain | deployment names | `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`⁵ |
| DeepSeek | `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` | `ANTHROPIC_AUTH_TOKEN` (a DeepSeek key) | `deepseek-v4-flash`, `deepseek-v4-pro` | `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL` |
| In-house gateway | `ANTHROPIC_BASE_URL` | `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` | first-party ids | `ANTHROPIC_CUSTOM_HEADERS` |

⁴ Set to `1` when a gateway signs the requests. ⁵ Pin the deployment names the CLI uses
for its Sonnet and Opus calls.

Set `ANTHROPIC_DEFAULT_HAIKU_MODEL` when the platform needs its own id for the CLI's
small-model calls. These variables belong to Claude Code; its documentation is the
reference.

## Managed Agents: the endpoint

`scripts/deploy_managed_agent.sh` reads `ANTHROPIC_API_KEY` and posts to `ANTHROPIC_API_URL`
(default `https://api.anthropic.com`; the other two paths read `ANTHROPIC_BASE_URL`). A gateway at that address must proxy `/v1/skills` (multipart),
`/v1/agents`, and, for your host application, `/v1/environments`, `/v1/sessions`, and the
session event stream, with the `anthropic-beta` headers intact. A gateway that fronts only
`/v1/messages` does not serve this path.

```bash
# Dry run against a gateway (the default); add --live to deploy.
ANTHROPIC_API_URL=https://llm-gateway.internal.example \
  scripts/deploy_managed_agent.sh shopping-agent/managed-agents/shopping-agent
```

## What the tests cover

`tests/test_platform_seams.py` constructs each platform client with placeholder credentials
and checks that both Messages API runtimes bind it, and that each environment above reaches
`ClaudeAgentOptions` in both SDK runtimes. `scripts/verify_all.py` runs both deploy dry
runs. No test holds cloud credentials, so no live platform conversation runs here; run one
on your platform before relying on it. To drive either agent with no credentials at all,
script the model with `commerce_common.testing.FakeClient`.
