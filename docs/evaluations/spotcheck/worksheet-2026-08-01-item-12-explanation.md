# enum-value-escape — `CallTypes`, `litellm/types/utils.py`

**Rating: critical.** The scattered vocabulary is itself a moderate maintainability problem, but it
has already caused a silent security failure: prompt injection detection does not run at all for
embedding and transcription requests, and it reports success rather than erroring. The rating
reflects that live consequence, not the enum hygiene on its own

## Background

LiteLLM is a proxy that sits in front of many LLM providers and exposes a single OpenAI-compatible
API. Every request that flows through it is tagged with a "call type": a short string naming the
operation, such as `completion` for a chat completion, `embedding` for an embedding, or
`transcription` for audio transcription. Asynchronous variants get an `a` prefix, so the async form
of `embedding` is `aembedding`. Because the proxy is async, most requests arrive as the `a` variant.

The call type is load-bearing. It decides which cost calculation runs, what gets written to logs, and
which optional hooks apply to a request. Hooks are pluggable callbacks that inspect or modify a
request before it reaches the provider, and several of them look at the call type to decide whether
they should act at all.

## The finding

The call type vocabulary is declared four separate times, by hand, in four different places.

`CallTypes` (`types/utils.py:314`) is a Python `Enum` with 145 members. `CallTypesLiteral`
(`types/utils.py:492`) is a `typing.Literal` covering the same concept with 61 members, sitting in
the same file about 180 lines below the enum. A `Literal` is not a class with members; it is just a
fixed set of allowed strings that the type checker enforces at call boundaries. Nothing in the code
derives the `Literal` from the enum, so keeping the two aligned is entirely manual.

`proxy/common_request_processing.py:1057` declares a third list, under the name `route_type`, which
is what the proxy's HTTP layer calls the same concept when it routes an incoming request. Two more
ad-hoc lists appear inline at `get_formatted_prompt.py:6` and `prompt_injection_detection.py:147`.

The four have drifted. 85 of the enum's values are absent from `CallTypesLiteral`, mostly the batch,
file, thread, video, container and fine-tuning types. Three values go the other way:
`arealtime_calls`, `acreate_realtime_client_secret` and `acreate_realtime_transcription_session`
exist in the `Literal` and are passed as bare strings at `router.py:1226-1231`, but have no enum
member at all.

## The resulting bug

`prompt_injection_detection.py` implements an optional hook that inspects a user's prompt for
injection attacks before the request is forwarded to the provider. It only knows how to handle a few
kinds of request, so it first checks the call type against a hand-written list and bails out for
anything it does not recognize. That check is at `:147-155`:

```python
try:
    assert call_type in ["acompletion", "completion", "text_completion", "embeddings",
                         "image_generation", "moderation", "audio_transcription"]
except Exception:
    self.print_verbose(f"Call Type - {call_type}, not in accepted list - [...]")
    return data
```

`"embeddings"` and `"audio_transcription"` appear in none of the four vocabularies. The real values
are `"embedding"` and `"aembedding"` for embeddings, and `"transcription"` and `"atranscription"` for
audio. The proxy passes its `route_type` value into this hook (`common_request_processing.py:1262`
and `:1642`), so an embedding request arrives carrying `"aembedding"`. That value is not in the list,
the `assert` therefore raises, and the `except Exception` immediately below catches it, logs a debug
line, and returns the request data unchanged.

The practical effect is that prompt injection detection silently does nothing for embedding and
transcription requests. It does not error, and it does not warn at a level an operator would notice.
It reports success while having scanned nothing. The same two typos also make the
`elif call_type == "audio_transcription"` branch at `get_formatted_prompt.py:47` permanently
unreachable, since no caller can ever produce that string.

## Why it was not caught

The hook's `call_type` parameter is declared as `CallTypesLiteral` (see the `pre_call_hook` signature
at `proxy/utils.py:1326`). A type checker comparing the hand-written list against that declared type
would have flagged both `"embeddings"` and `"audio_transcription"` as impossible values immediately.

It did not, because every hop in the chain carries a `# type: ignore` comment
(`prompt_injection_detection.py:161` and `:223`, `common_request_processing.py:1262` and `:1642`).
In most Python projects that comment tells the type checker to skip errors on that line. In this
repository it does not even do that: `pyrightconfig.json` sets `enableTypeIgnoreComments` to false,
so the comments silence nothing and the underlying type error is simply never reported. The
suppressions are inert, and the mismatch went unnoticed on both counts.

## The ordinary escapes

Beyond the bug, the routine pattern is present throughout. `cost_calculator.py:484-574` runs roughly
ten bare string comparisons of the form `call_type == "speech" or call_type == "aspeech"` and
`call_type == "arerank" or call_type == "rerank"`, all against a parameter it declares as
`CallTypesLiteral`, and never references `CallTypes` itself.

## Why this is more than a style issue

An enum escape is usually cosmetic, and it is fair to ask whether replacing string literals with
enum members buys anything. This case shows what it buys. With a single declared domain, the
`prompt_injection_detection` list would have been a type error caught at check time. Instead, two
plausible-looking strings turned a security hook into a no-op for two whole request categories, and
the failure mode was silence
