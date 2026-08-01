# archagent spot-check worksheet

Reviewer: (fill in)    Date: 2026-08-01

For each item below, read the evidence and record a verdict. **The tool's own severity,
confidence and recommendation are deliberately not shown** — they are held back so that this
measures agreement with the code rather than with the tool's prior. They are revealed when the
sheet is ingested.

Verdicts: `confirm` (a real problem worth acting on) · `dismiss` (not a problem here, say why) ·
`unsure`. A one-line reason matters more than the verdict; it is what makes a disagreement
diagnosable later, and `unsure` is a real answer — it is excluded from the precision denominator
rather than counted as a dismissal.

The evidence below is a pointer, not a substitute for the code. For a **change-prone file** in
particular the question is whether that file is genuinely absorbing special cases, which only
reading it can answer.


## Getting the code

Each finding is judged against the repository **at the revision it was found at**. These
commands put each one in `/tmp`, reusing the cached clones:

```bash
git -C ~/.cache/archagent/corpus/datasette.git worktree add --detach /tmp/review-datasette 1.0a37
git -C ~/.cache/archagent/corpus/django.git worktree add --detach /tmp/review-django 5.2.16
git -C ~/.cache/archagent/corpus/litellm.git worktree add --detach /tmp/review-litellm v1.95.0-dev.2
```

When you are done: `git -C ~/.cache/archagent/corpus/<name>.git worktree remove --force /tmp/review-<name>`

---

## item 1 — `scattered-source-of-truth:datasette/views/database.py:8181537b`

**Repository:** datasette @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `datasette/views/database.py`
- also: `datasette/views/row.py`, `datasette/views/stored_queries.py`, `datasette/views/table.py`
- values: csv, html, json

```
verdict:
why:
```

---

## item 2 — `scattered-source-of-truth:django/db/backends/oracle/operations.py:47c524d0`

**Repository:** django @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `django/db/backends/oracle/operations.py`
- also: `django/db/backends/base/schema.py`, `django/db/backends/mysql/operations.py`, `django/db/backends/oracle/schema.py`, `django/db/backends/postgresql/operations.py`, `django/db/backends/sqlite3/_functions.py`, `django/db/backends/sqlite3/operations.py` (+2 more)
- values: BooleanField, DateField, DateTimeField, JSONField, TimeField, UUIDField, +12 more

```
verdict:
why:
```

---

## item 3 — `enum-value-escape:litellm/types/llms/openai.py:352293eb`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/types/llms/openai.py`
- also: `litellm/completion_extras/litellm_responses_transformation/transformation.py`, `litellm/litellm_core_utils/llm_cost_calc/tool_call_cost_tracking.py`, `litellm/llms/anthropic/chat/transformation.py`, `litellm/llms/bedrock/image_generation/amazon_titan_transformation.py`, `litellm/llms/ollama/chat/transformation.py`, `litellm/llms/ollama/completion/transformation.py` (+2 more)
- values: hd, high, low, medium, standard

```
verdict:
why:
```

---

## item 4 — `enum-value-escape:litellm/types/guardrails.py:64a3cd9d`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/types/guardrails.py`
- also: `litellm/integrations/custom_guardrail.py`, `litellm/proxy/utils.py`
- values: during_call, logging_only, post_call, pre_call

```
verdict:
why:
```

---

## item 5 — `scattered-source-of-truth:litellm/litellm_core_utils/prompt_templates/factory.py:408ce3f3`

**Repository:** litellm @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `litellm/litellm_core_utils/prompt_templates/factory.py`
- also: `litellm/litellm_core_utils/prompt_templates/common_utils.py`, `litellm/litellm_core_utils/realtime_streaming.py`, `litellm/litellm_core_utils/token_counter.py`
- values: function_call, image_url, system, text, user

```
verdict:
why:
```

---

## item 6 — `enum-value-escape:litellm/types/guardrails.py:f9422129`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/types/guardrails.py`
- also: `litellm/proxy/guardrails/guardrail_endpoints.py`, `litellm/proxy/guardrails/guardrail_registry.py`
- values: config, db

```
verdict:
why:
```

---

## item 7 — `scattered-source-of-truth:litellm/proxy/hooks/parallel_request_limiter_v3.py:7785fe81`

**Repository:** litellm @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `litellm/proxy/hooks/parallel_request_limiter_v3.py`
- also: `litellm/proxy/guardrails/guardrail_hooks/cisco_ai_defense/cisco_ai_defense.py`, `litellm/proxy/guardrails/guardrail_initializers.py`, `litellm/proxy/hooks/batch_rate_limiter.py`, `litellm/proxy/hooks/dynamic_rate_limiter_v3.py`
- values: OVER_LIMIT, input, output, requests

```
verdict:
why:
```

---

## item 8 — `enum-value-escape:litellm/integrations/otel/model/config.py:381c1a31`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/integrations/otel/model/config.py`
- also: `litellm/litellm_core_utils/litellm_logging.py`
- values: agentops, arize, langfuse_otel, levo, weave_otel

```
verdict:
why:
```

---

## item 9 — `scattered-source-of-truth:litellm/integrations/code_interpreter_interception/handler.py:25459028`

**Repository:** litellm @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `litellm/integrations/code_interpreter_interception/handler.py`
- also: `litellm/integrations/custom_guardrail.py`, `litellm/integrations/logfire_logger.py`, `litellm/integrations/mlflow.py`, `litellm/integrations/websearch_interception/handler.py`
- values: acompletion, completion, litellm_metadata, metadata, tool_choice, tools

```
verdict:
why:
```

---

## item 10 — `enum-value-escape:litellm/types/utils.py:7e133d31`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/types/utils.py`
- also: `litellm/utils.py`
- values: eu, us

```
verdict:
why:
```

---

## item 11 — `scattered-source-of-truth:litellm/responses/streaming_iterator.py:e5f94b0e`

**Repository:** litellm @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `litellm/responses/streaming_iterator.py`
- also: `litellm/responses/file_search/emulated_handler.py`, `litellm/responses/litellm_completion_transformation/transformation.py`, `litellm/responses/mcp/litellm_proxy_mcp_handler.py`, `litellm/responses/utils.py`
- values: function_call, mcp, message, output_text

```
verdict:
why:
```

---

## item 12 — `enum-value-escape:litellm/types/utils.py:d5861323`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/types/utils.py`
- also: `litellm/cost_calculator.py`, `litellm/integrations/logfire_logger.py`, `litellm/litellm_core_utils/llm_response_utils/convert_dict_to_response.py`, `litellm/litellm_core_utils/llm_response_utils/get_formatted_prompt.py`, `litellm/llms/custom_httpx/llm_http_handler.py`, `litellm/proxy/common_request_processing.py` (+7 more)
- values: acompletion, acreate_file, aembedding, afile_content, afile_delete, agenerate_content, +25 more

```
verdict:
why:
```

---

## item 13 — `scattered-source-of-truth:litellm/litellm_core_utils/get_supported_openai_params.py:0007a635`

**Repository:** litellm @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `litellm/litellm_core_utils/get_supported_openai_params.py`
- also: `litellm/litellm_core_utils/exception_mapping_utils.py`, `litellm/litellm_core_utils/get_llm_provider_logic.py`, `litellm/litellm_core_utils/llm_response_utils/get_api_base.py`, `litellm/litellm_core_utils/prompt_templates/factory.py`, `litellm/litellm_core_utils/streaming_handler.py`
- values: ai21, aleph_alpha, anthropic, azure, azure_text, baseten, +15 more

```
verdict:
why:
```

---

## item 14 — `enum-value-escape:litellm/types/utils.py:57f438c0`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/types/utils.py`
- also: `litellm/__init__.py`, `litellm/cost_calculator.py`, `litellm/images/main.py`, `litellm/litellm_core_utils/exception_mapping_utils.py`, `litellm/litellm_core_utils/get_llm_provider_logic.py`, `litellm/litellm_core_utils/get_supported_openai_params.py` (+5 more)
- values: ai21_chat, aiml, aiohttp_openai, amazon_nova, anthropic_text, assemblyai, +104 more

```
verdict:
why:
```

---

## item 15 — `scattered-source-of-truth:litellm/main.py:9f62d232`

**Repository:** litellm @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `litellm/main.py`
- also: `litellm/__init__.py`, `litellm/cost_calculator.py`, `litellm/router.py`, `litellm/utils.py`
- values: aleph_alpha, anthropic, anyscale, azure, azure_ai, bedrock, +37 more

```
verdict:
why:
```

---

## item 16 — `enum-value-escape:litellm/types/utils.py:8e7fc614`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/types/utils.py`
- also: `litellm/llms/bedrock/chat/converse_transformation.py`
- values: flex, priority

```
verdict:
why:
```

---

## item 17 — `scattered-source-of-truth:litellm/proxy/_experimental/mcp_server/gateway_dcr_flow.py:6e5d7a48`

**Repository:** litellm @ (pinned)
**Kind:** scattered-source-of-truth

**Evidence**

- owner: `litellm/proxy/_experimental/mcp_server/gateway_dcr_flow.py`
- also: `litellm/proxy/_experimental/mcp_server/byok_oauth_endpoints.py`, `litellm/proxy/_experimental/mcp_server/discoverable_endpoints.py`
- values: S256, authorization_code, code

```
verdict:
why:
```

---

## item 18 — `enum-value-escape:litellm/proxy/guardrails/guardrail_hooks/noma/noma_v2.py:e2dc995f`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/proxy/guardrails/guardrail_hooks/noma/noma_v2.py`
- also: `litellm/proxy/guardrails/guardrail_hooks/bedrock_guardrails.py`, `litellm/proxy/guardrails/guardrail_hooks/straiker/straiker.py`
- values: BLOCKED, GUARDRAIL_INTERVENED

```
verdict:
why:
```

---

## item 19 — `enum-value-escape:litellm/types/router.py:7b6e86ef`

**Repository:** litellm @ (pinned)
**Kind:** enum-value-escape

**Evidence**

- owner: `litellm/types/router.py`
- also: `litellm/router.py`
- values: cost-based-routing, latency-based-routing, least-busy, usage-based-routing, usage-based-routing-v2

```
verdict:
why:
```

---
