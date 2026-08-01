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
verdict: confirm
why: this is a real problem - the values are not defined anywhere and are implicit (based on some regular expression in datasette/app.py:2527-2773). These should be centrally defined as constants with documentation. I would rate this as a moderate issue, not critical, as the values are implicitly coming http content times.
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
verdict: confirm
why: like item 1, this is a case where centrally-defined constants should have been used in place of string literals. Again, it is a moderate issue.
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
verdict: partial confirm
why: these string literals are used in different places for different purposes. For example "high" in openai.py and transformation.py has different meanings. There are a few valid cases and there are cases where the constants are defined but string literals used in the same file instead of the constants. So, overally, I would give it a weak moderate, but several independent meanings are present here.
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
verdict: confirm
why: the central contstants are defined in guardrails.py but inconsistently used (some cases have string literals). A moderate severity.
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
verdict: confirm
why:
system and text (as the chat-completions concepts) are used consistently; user, image_url, and function_call are each defined independently in multiple places, and in two cases the duplicates have actually diverged in behavior.

convert_to_ollama_image and extract_images_from_message are the same feature for the same provider on two different code paths — llms/ollama/completion/transformation.py:389 uses the first, llms/ollama/chat/transformation.py:278 uses the second — and they disagree.

I would rate that as a critical issue.
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
verdict: confirm
why: GUARDRAIL_DEFINITION_LOCATION is defined in types/guardrails.py:1042 but guardrail_endpoints.py:228 and :267 pass bare "db"/"config" into the same field the same file populates with the enum at :1235/:1246; guardrail_registry.py never imports it and re-declares the domain as Literal["db","config"] across ~9 sites. Moderate, not critical: the enum subclasses str so everything still compares correctly, and the registry's Literal is still type-checked; the weak spot is the unchecked == "db" / == "config" comparisons at guardrail_endpoints.py:241 and :1244, which gate a 404.
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
verdict: confirm
why: the strongest instance is a real divergence: _get_total_tokens_from_usage (parallel_request_limiter_v3.py:2626-2672) and the inline block at dynamic_rate_limiter_v3.py:718-728 both answer "how many tokens count toward the limit", and disagree; the owner excludes cached_tokens for input/total and handles dict usage, the dynamic limiter does neither, even though line 718 calls into the owner for the config value. Separately, RateLimitResponse.overall_code / RateLimitStatus.code are typed bare str while "OVER_LIMIT" is compared in 4+ modules including compact.py:432 outside proxy/hooks, and a typo there fails open. Caveat: the value list conflates three concepts; the "input"/"output" hits in guardrail_initializers.py and cisco_ai_defense.py are guardrail scan direction, unrelated to the limiter, and "requests" is already governed by a Literal. Serious on concept B, moderate on the rest.
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
verdict: confirm
why: ExporterOwner (integrations/otel/model/config.py:28) is used only inside the presets package; litellm_logging.py never imports it and dispatches on bare "arize"/"agentops"/"levo"/"langfuse_otel"/"weave_otel" (:3521, :3694, :3749, :3967, :3981), then threads those strings into callback_name=. The join at plumbing/routing.py:103 compares spec.owner (enum) to that bare string and works only because the enum subclasses str, which the class docstring admits is intentional. Moderate: the literals in litellm_logging are still checked against _custom_logger_compatible_callbacks_literal (__init__.py:112), and a mismatch fails closed (no headers stamped) rather than leaking creds to another backend. But the same vocabulary is declared four times (master Literal, ExporterOwner, PRESET_BY_CALLBACK keys, DYNAMIC_HEADERS_BY_CALLBACK keys) and has already drifted: langtrace is a preset with no ExporterOwner member, so its exporters get owner=None.
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
verdict: confirm
why: the metadata/litellm_metadata container is a real scattered source of truth. get_metadata_variable_name_from_kwargs exists in core_helpers.py:181, is duplicated verbatim (docstring included) in proxy/common_utils/callback_utils.py:409, wrapped a third time at router.py:7095, and then bypassed by ~30 hand-rolled ("metadata", "litellm_metadata") loops across integrations/, proxy/, main.py and router hooks. Those loops are first-hit-wins and have diverged on order: main.py:1102, common_request_processing.py:1425 and litellm_logging.py:524 read litellm_metadata first (matching the helper), while custom_guardrail.py:492+, code_interpreter handler.py:113, websearch handler.py:1350 and parallel_request_limiter_v3.py:2594+ read metadata first, so a request carrying both keys is resolved differently depending on which module looks. Scope is much wider than the reported 5 files. Separately, custom_guardrail.py:665 collapses CallTypes into bare "completion"/"acompletion" compared at logfire_logger.py:42 and mlflow.py:221 (an enum escape, overlaps item 12). The "tools"/"tool_choice" hits are just OpenAI request-body keys and are not a finding.
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
verdict: dismiss
why: concept collision, not an escape. The "eu"/"us" in litellm/utils.py belong to AllowedModelRegion = Literal["eu","us"] (proxy/_types.py:1649), key/team region allow-listing for routing, which _infer_model_region declares as its return type at utils.py:4568; a Literal has no members, so bare literals there are the correct and type-checked spelling. DataResidency (types/utils.py:3765) is OpenAI regional-processing cost uplift, a separate concept that merely shares the two strings, and its only consumer uses it properly via _VALID_DATA_RESIDENCIES derived from the enum (llm_cost_calc/utils.py:35, :664). A genuine but minor escape does exist in a file the evidence doesn't list: llms/openai/data_residency.py:17-20 hardcodes "eu"/"us" in _OPENAI_REGIONAL_HOSTS and returns Optional[str], and cost_calculator.py carries it as bare str through ~8 signatures; it fails closed to a 1.0 multiplier, so low severity.
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
verdict: confirm
why: real, and the canonical implementation already exists in a file the evidence doesn't name: ResponsesAPIResponse.output_text (types/llms/openai.py:1329) walks output items and joins every output_text block, handling dict and object forms. file_search/emulated_handler.py:316 takes a ResponsesAPIResponse and re-implements it, but returns only the first output_text block, so multi-block or multi-message responses are silently truncated there; streaming_iterator.py:1888 is a third variant that concatenates but also accepts "text" blocks, and transformation.py:974 and :1233 use two more block-type sets. The same message/output_text/function_call walk is hand-rolled in 15+ further files outside responses/ (opentelemetry.py:2624, langfuse_otel.py:188, arize/_utils.py:211, redact_messages.py:134, azure/responses/transformation.py:101, four guardrail hooks), each re-deriving the dict-vs-object dual access. Secondary: the type == "mcp" tool predicate is duplicated at utils.py:963, transformation.py:1266 and twice in the same class at litellm_proxy_mcp_handler.py:87 and :110.
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
verdict: confirm
why: one concept, four hand-maintained vocabularies: CallTypes enum (types/utils.py:314, 145 members), CallTypesLiteral (types/utils.py:492, 61 members, same file), the route_type Literal (proxy/common_request_processing.py:1057), and ad-hoc lists in get_formatted_prompt.py:6 and prompt_injection_detection.py:147. Already drifted: 85 enum values are missing from CallTypesLiteral, and 3 Literal values (arealtime_calls, acreate_realtime_client_secret, acreate_realtime_transcription_session) have no enum member and are passed as bare strings at router.py:1226-1231. This causes a live bug: prompt_injection_detection.py:147-155 asserts call_type against "embeddings" and "audio_transcription", neither of which exists in any vocabulary (the real values are "embedding"/"aembedding" and "transcription"/"atranscription"), so the assert throws, the except swallows it, and prompt injection detection silently no-ops on embedding and transcription calls; the same typo makes get_formatted_prompt.py:47 unreachable. The `# type: ignore` at prompt_injection_detection.py:161/:223 and common_request_processing.py:1262/:1642 is what hid it, and those are already inert since pyrightconfig sets enableTypeIgnoreComments false. Separately cost_calculator.py:484-574 does ~10 bare-literal comparisons on a CallTypesLiteral param. Critical.
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
verdict: confirm
why: the source of truth exists — ProviderConfigManager.get_provider_chat_config (utils.py:7830) with _PROVIDER_CONFIG_MAP keyed by LlmProviders — and get_supported_openai_params.py:38-58 uses it correctly, then duplicates it with a ~200-line if/elif chain (lines 60-260) hand-mapping 67 bare provider strings to the same XConfig().get_supported_openai_params calls. 63 of the 67 are LlmProviders members, so for request_type == "chat_completion" the generic path already returned and those branches are dead in the common case; 4 (aleph_alpha, anyscale, bedrock_converse, palm) aren't enum members at all. Azure model-type detection is duplicated verbatim between utils.py:7754 _get_azure_config and get_supported_openai_params.py:129-137, so a new Azure model family must be added in both. The other listed files each carry an independent provider dispatch: 180 bare-literal provider comparisons vs 8 LlmProviders references across the six, with get_llm_provider_logic.py (66) and prompt_templates/factory.py (10) referencing the enum zero times. Serious, though the remedy is largely deletion.
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
verdict: confirm
why: distinct from item 13 (duplicated dispatch); the point here is that LlmProviders is not the domain of the field it nominally types, so the escape cannot be closed by mechanical substitution. 647 bare custom_llm_provider == "..." sites vs 490 LlmProviders references, 129 distinct literals, of which 10 are not enum members across 23 sites. Three groups: (a) non-provider sentinels assigned into the field — "cached_response" set at caching_handler.py:937, proxy_server.py:8993/9024, responses/streaming_iterator.py:919, bedrock/chat/invoke_handler.py:550/646 and compared at streaming_handler.py:1297/1711/1905, and "anthropic_xml" (a prompt format, not a provider) passed as custom_llm_provider= at bedrock/chat/invoke_handler.py:837 behind a # type: ignore; (b) dead branches for removed providers aleph_alpha/palm/anyscale across main.py, utils.py, streaming_handler.py, exception_mapping_utils.py and get_supported_openai_params.py, where "palm" is never assigned at all but "anyscale" still is (get_llm_provider_logic.py:239), proving the field holds non-members at runtime; (c) newer surfaces with no member (litellm_responses, pydantic_ai_agents, watsonx_orchestrate). A second hand-maintained registry keyed by provider name lives in __init__.py:1103/1121/1126 with a duplicate litellm_provider chain at __init__.py:782+ and utils.py:2807. provider_list = list(LlmProviders) at __init__.py:2228 is correctly derived.
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
verdict: confirm
why: real but heavily overlapping items 13 and 14; the distinct evidence is copy-paste rather than divergence. The 6-line provider_config resolution block is verbatim identical in three files (main.py:5222, utils.py:3813, llms/anthropic/experimental_pass_through/messages/handler.py:525), and all three write the membership test as [provider.value for provider in LlmProviders], rebuilding a 149-element list per completion() and per get_optional_params() call, even though LlmProvidersSet exists at types/utils.py:3520 and is used correctly elsewhere in the same files (utils.py:5197, 5260; cost_calculator.py:808) — three spellings of one question. cost_calculator.py:584-645 is a fourth independent per-provider chain with zero enum references. main.py's 148 comparisons are mostly handler dispatch, which ProviderConfigManager does not cover, so that part is a monster if/elif rather than a duplicated source of truth, and router.py contributes only 2. Moderate on its own. Caveat for scoring: 13, 14 and 15 are three facets of one root issue and should not be counted as three independent problems.
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
verdict: partial confirm
why: the escape is real but not from the enum named. ServiceTier (types/utils.py:3757) is scoped to cost calc and all three of its consumers use it properly, including a derived _SERVICE_TIER_SUFFIXES (llm_cost_calc/utils.py:40) and ServiceTier.FLEX/PRIORITY comparisons (:189, cost_calculator.py:868). What converse_transformation.py:995 hardcodes as ("default","flex","priority") duplicates ServiceTierBlock.type: Literal["priority","default","flex"] (types/llms/bedrock.py:229), which that same file already imports at :138, and it builds the TypedDict as a raw dict so the Literal isn't enforced. The underlying issue is that OpenAI's four-value service_tier domain has no canonical home: ServiceTier covers 3 and omits "default", bedrock.py declares a different 3, groq/chat/transformation.py:287 declares a third 3 (auto/default/flex, no priority), and converse_transformation.py restates a fourth inline. Latent hazard rather than a live bug: _map_groq_service_tier normalizes anything outside its subset to "auto", so a future Groq priority tier would silently be costed as standard. Minor.
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
verdict: dismiss
why: these are RFC-frozen wire constants, not a litellm concept with a source of truth — "code" (RFC 6749 4.1.1), "authorization_code" (4.1.3), "S256" (RFC 7636 4.2) — and most occurrences sit inside OAuth metadata documents where the literal is the response payload itself (discoverable_endpoints.py:2267-2270/2389-2392, byok_oauth_endpoints.py:608-610, gateway_dcr_flow.py:287-288). They cannot drift and a typo fails loudly against any client; writing them inline is the industry standard, and a local enum would be the invented convention. I checked the security angle specifically and there is no divergence: all three files mandate S256 PKCE (gateway_dcr_flow.py:340, discoverable_endpoints.py:695-711 _require_s256_pkce, and byok_oauth_endpoints.py:660/:704/:726 — the `or "S256"` at :690 only fills a hidden HTML form field that the POST re-validates). One minor real duplicate worth noting: _require_s256_pkce and the inline check at gateway_dcr_flow.py:340 are the same rule twice with different error contracts (HTTPException detail string vs an RFC 6749 _oauth_error object), so clients see two shapes for one violation.
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
verdict: partial confirm
why: not an escape from the named enum. These are three independent vendor API vocabularies that share AWS Bedrock's native NONE/BLOCKED/GUARDRAIL_INTERVENED strings. Noma's _Action (noma_v2.py:40) is private to that module and used correctly at :232/:235; Straiker declares StraikerWebhookAction = Literal[...] (types/proxy/guardrails/guardrail_hooks/straiker.py:14), types its pydantic field with it at :86, and the bare comparisons at straiker.py:526/:532 are the correct, type-checked spelling for a Literal. The real gap is Bedrock, which declares the type but not the domain: eight TypedDicts use action: Optional[str] (types/.../bedrock_guardrails.py:40,51,60,66,77,84,96,125) and bedrock_guardrails.py runs ~20 unchecked comparisons against them. One is fail-open — _should_raise_guardrail_blocked_exception at :1494 returns False (don't block) when response.get("action") != "GUARDRAIL_INTERVENED", so drift in that string silently disables the guardrail with no type error. Low-moderate, and the fix is confined to tightening those fields to a Literal as the other two integrations already do.
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
verdict: confirm
why: RoutingStrategy (types/router.py:758) is used correctly in one dispatch — _build_strategy_selector at router.py:861-884 matches on RoutingStrategy.LEAST_BUSY.value etc. — while three sibling dispatches over the same vocabulary in the same file use bare literals: _DEFAULT_SELECTOR_ATTR_BY_STRATEGY (:816-822, five string keys), _select_deployment_async (:1116-1149) and _select_deployment_sync (:1172-1190), with two more declarations of the list at :335-343 and types/router.py:86-88. All three dispatches must agree and all three fall through to `case _: return None`, so a mismatch silently yields no deployment rather than erroring; the sync/async pair already legitimately differ (cost-based-routing omitted from sync per the comment at :1169-1171), which means a genuine typo would be indistinguishable from the intentional omission. The enum also isn't the domain in either direction: PROVIDER_BUDGET_LIMITING has no implementation anywhere and router.py:1019 groups it with unknown strings, while "simple-shuffle" and "lar1" are valid with no members. _validate_routing_strategy:836 correctly derives from the enum. Moderate; contained to one file.
```

---
