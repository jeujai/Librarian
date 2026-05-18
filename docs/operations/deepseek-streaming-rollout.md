# DeepSeek Chat Streaming — Rollout Guide

This document collects the operational procedures for enabling and rolling out
true token-level streaming in the DeepSeek chat path (feature spec:
`.kiro/specs/deepseek-chat-streaming`). The streaming client lives in
[`src/multimodal_librarian/services/deepseek_ai_service.py`](../../src/multimodal_librarian/services/deepseek_ai_service.py)
and shares resilience primitives (circuit breaker, error-rate tracker) with the
Gemini path via
[`src/multimodal_librarian/services/provider_resilience.py`](../../src/multimodal_librarian/services/provider_resilience.py).

The guide is organized into three sections, each added by a separate task:

- Deployment checklist — pre-deploy gating items.
- Phased rollout plan — phases 0 through 4 (added by task 13.2).
- Feature-flag runbook — live tuning, soft-rollback, manual rollback (added by
  task 13.3).

## Deployment checklist

Complete every item below before promoting a build that enables DeepSeek chat
streaming to the next environment. This list is intentionally short and
gating — a ticked box means an operator has confirmed the item for the
environment being deployed to.

### Configuration and secrets

- [ ] `DEEPSEEK_API_KEY` is set in the target environment's secret store
      (AWS Secrets Manager in production, `.env` in local/dev) and is reachable
      by the application process at startup. A missing or empty key causes the
      app to fall back to the Gemini path per Requirement 11.1, which silently
      disables DeepSeek streaming and invalidates this rollout.
- [ ] `DEEPSEEK_STREAMING_ENABLED` is **explicitly set** (do not rely on the
      default) to one of:
      - `"true"` — enable streaming in this environment.
      - `"false"` — deploy the streaming code but keep it dormant (used in
        phase 0 of the phased rollout).
      The value is read once at `DeepSeekAIService.__init__` and exposed as
      `streaming_enabled_config`; a restart is required to change it.
- [ ] `DEEPSEEK_STREAM_TIMEOUT` (time-to-first-chunk timeout, seconds) has been
      reviewed for this environment. Default is `60.0`. Raise for slow links,
      lower for tighter SLOs. Applied as the `read` timeout on the initial
      `POST /chat/completions` call.
- [ ] `DEEPSEEK_STREAM_TOTAL_TIMEOUT` (maximum total stream duration, seconds)
      has been reviewed for this environment. Default is `180.0`. This caps
      the longest possible streamed response before the server yields a
      terminal timeout chunk with partial content preserved.
- [ ] `DEEPSEEK_STREAM_INCLUDE_USAGE` is set to `"true"` (default) unless a
      specific reason exists to disable usage reporting. When true the client
      sends `stream_options.include_usage=true` so `prompt_tokens` /
      `completion_tokens` land on the terminal chunk and in the
      `deepseek_stream_complete` log event.

### Observability and alerts

- [ ] An alert is configured on the rate of `event="deepseek_stream_error"` log
      entries emitted by the streaming client. Recommended threshold: warn at
      > 1% of `deepseek_stream_start` events over a 5-minute window, page at
      > 5% over a 5-minute window. These events are logged at `ERROR` and
      carry `call_id`, `duration_ms`, `chunks_received_before_error`,
      `error_type`, and a truncated `error_message`.
- [ ] An alert is configured on the circuit-breaker state reported by
      `DeepSeekAIService.get_provider_status()`. The `circuit_breaker_state`
      field is one of `"closed"`, `"half_open"`, or `"open"`. Page when
      `circuit_breaker_state="open"` persists for more than 60 seconds — this
      indicates DeepSeek is failing consecutively and the app has stopped
      issuing streaming requests entirely.
- [ ] Dashboard panels exist for the streaming metrics exposed by
      `get_provider_status()`: `streaming_total_calls`,
      `streaming_successful_calls`, `streaming_failed_calls`,
      `streaming_avg_duration_ms`, `streaming_avg_time_to_first_token_ms`,
      `streaming_avg_chunks_per_response`, and `streaming_enabled`. The
      `streaming_enabled` field flips to `false` automatically when the
      `ErrorRateTracker` soft-rollback engages — this is a leading indicator
      worth graphing even if no alert fires on it.

### Rollback readiness

- [ ] Rolling back to non-streaming by flipping `DEEPSEEK_STREAMING_ENABLED`
      from `"true"` to `"false"` has been exercised on staging and verified to
      restore full chat functionality after an application restart. The flag
      is read once at service construction, so a restart (or task
      re-deployment on ECS) is required for the change to take effect.
- [ ] The operator who will perform the rollout knows how to apply the
      rollback env-var flip in the target environment (Secrets Manager +
      forced ECS deployment for production; `.env` + `make dev` restart for
      local) and has the credentials to do so without escalation.

### Sign-off

- [ ] All items above are checked for the environment being deployed to.
- [ ] The deploying operator's name and timestamp are recorded in the rollout
      tracking ticket.

## Phased rollout plan

The streaming feature promotes through five phases. Each phase names a goal,
an exit criterion, the environment and flag state it applies to, the
observability signals that gate promotion, the rollback trigger, and the
human owner of the go/no-go decision. Phases run sequentially — do not skip
ahead even if a prior phase looks clean. The phase names and thresholds
below match design §"Migration and rollout plan".

### Phase 0: Code merge with flag off

- **Goal.** Ship the streaming code to every environment with the feature
  dormant. This decouples code deployment from feature enablement so a later
  flag flip is the only variable under test.
- **Duration / exit criteria.** Completes on the first deployment after
  merge to `main`. Exit when the deployed build includes
  `services/deepseek_ai_service.py` with the SSE streaming client and
  `services/provider_resilience.py`, and the service has restarted cleanly
  in dev, staging, and production. No user-visible change is expected.
- **Environment and flag state.** All environments.
  `DEEPSEEK_STREAMING_ENABLED=false` (the deployed default post-code-merge).
  All other DeepSeek env vars (`DEEPSEEK_API_KEY`,
  `DEEPSEEK_STREAM_TIMEOUT`, `DEEPSEEK_STREAM_TOTAL_TIMEOUT`,
  `DEEPSEEK_STREAM_INCLUDE_USAGE`) are set to their phase-appropriate
  values per the deployment checklist, but streaming stays inactive because
  the enable flag is `false`.
- **Monitoring signals.** Confirm service health endpoints and startup logs
  are clean in every environment. Because the flag is off, no
  `deepseek_stream_start`, `deepseek_stream_first_token`,
  `deepseek_stream_complete`, or `deepseek_stream_error` events should
  appear — their absence is the correctness signal for this phase.
- **Rollback trigger.** Build fails to start, import errors in
  `provider_resilience`, or the Gemini path regresses after the shared
  resilience primitives were extracted. Rollback is a code revert of the
  merge commit, since the flag-based rollback is not meaningful while the
  flag is already off.
- **Gate owner.** Release engineer responsible for the merge.

### Phase 1: Internal smoke on dev with flag on

- **Goal.** Verify the streaming client produces token-by-token output and
  honors the WebSocket protocol in a controlled environment before any
  external traffic sees it.
- **Duration / exit criteria.** Day 0 to day 1 after code merge. Exit when
  at least 20 internal chat sessions have completed end-to-end with visible
  incremental rendering, no `deepseek_stream_error` events in the window,
  and `circuit_breaker_state="closed"` throughout.
- **Environment and flag state.** Dev only. Set
  `DEEPSEEK_STREAMING_ENABLED=true` in the dev environment and restart.
  Staging and production remain at `DEEPSEEK_STREAMING_ENABLED=false`.
- **Monitoring signals.** Tail application logs for
  `event="deepseek_stream_start"` followed by
  `event="deepseek_stream_first_token"` and
  `event="deepseek_stream_complete"` on every test chat. Confirm
  `streaming_avg_time_to_first_token_ms` from
  `DeepSeekAIService.get_provider_status()` is within expected bounds
  (typically < 2000 ms on dev). Any `deepseek_stream_error` entry is
  investigated before promotion.
- **Rollback trigger.** Any occurrence of `deepseek_stream_error`,
  `circuit_breaker_state` transitioning to `"open"` or `"half_open"`, or
  `streaming_enabled` flipping to `false` inside `get_provider_status()`
  (indicating the `ErrorRateTracker` soft-rollback engaged). Rollback is
  setting `DEEPSEEK_STREAMING_ENABLED=false` in dev and restarting.
- **Gate owner.** Feature author plus one additional engineer performing
  manual smoke tests.

### Phase 2: Staging canary

- **Goal.** Exercise the streaming client under realistic traffic shape and
  latency profile, and confirm the error rate stays within the production
  tolerance across a full day-night cycle.
- **Duration / exit criteria.** At least 24 hours of continuous traffic on
  staging with `DEEPSEEK_STREAMING_ENABLED=true`. Exit criterion:
  `deepseek_stream_error` rate is strictly less than 5% of
  `deepseek_stream_start` events over the 24-hour window, AND
  `circuit_breaker_state` stayed `"closed"` for the duration (any transient
  `"half_open"` is acceptable; any sustained `"open"` is not).
- **Environment and flag state.** Staging at
  `DEEPSEEK_STREAMING_ENABLED=true`. Dev continues with the flag on.
  Production remains at `DEEPSEEK_STREAMING_ENABLED=false`.
- **Monitoring signals.** The `deepseek_stream_error` alert (warn at > 1%,
  page at > 5% over 5-minute windows) from the deployment checklist must be
  active. Watch the dashboard panels for
  `streaming_successful_calls` vs `streaming_failed_calls`,
  `streaming_avg_duration_ms`, `streaming_avg_time_to_first_token_ms`, and
  `circuit_breaker_state`. Any page-level alert firing halts promotion.
- **Rollback trigger.** Error-rate threshold breached over any 1-hour
  sub-window, circuit breaker stuck `"open"` for more than 60 seconds, or
  `streaming_enabled` flipping to `false` in `get_provider_status()` (the
  automatic soft-rollback has engaged). Rollback is
  `DEEPSEEK_STREAMING_ENABLED=false` on staging + service restart.
- **Gate owner.** On-call SRE for staging, co-signed by the feature author.

### Phase 3: Production canary at 10%

- **Goal.** Observe the streaming client on a bounded slice of production
  traffic to catch issues that only surface at scale without exposing the
  full user base.
- **Duration / exit criteria.** Day 3 to day 5 after staging exit. Target
  approximately 10% of production traffic on the streaming path, achieved
  by deploying the flag-on build to one of N ECS tasks (weighted so the
  task handles ~10% of chat requests) while the remaining tasks stay on
  `DEEPSEEK_STREAMING_ENABLED=false`. Exit when the 10% cohort's
  `deepseek_stream_error` rate stays < 5% over 24 hours and 48 hours of
  total runtime have elapsed without a page-level alert.
- **Environment and flag state.** Production, partial. One ECS task group
  (the canary) has `DEEPSEEK_STREAMING_ENABLED=true`; the majority task
  group has `DEEPSEEK_STREAMING_ENABLED=false`. Staging and dev stay at
  flag-on. Distribution is enforced at the ECS service level so the split
  is observable in the task environment variables.
- **Monitoring signals.** Same signals as phase 2, filtered to the canary
  task group. Additionally, compare end-to-end chat latency (from the
  chat router's request logs) between canary and non-canary tasks — a
  significant regression in total response time on the streaming cohort is
  a rollback signal even if the error rate is clean. Watch the
  `deepseek_stream_aborted` event rate (logged on client disconnect) to
  confirm partial-response persistence is behaving.
- **Rollback trigger.** Any page-level alert on the canary, canary error
  rate exceeding the non-canary baseline by more than 2 percentage points,
  circuit breaker stuck `"open"` for more than 60 seconds on the canary, or
  user reports of degraded chat experience tied to streaming. Rollback is
  scaling the canary task group to zero (the non-canary tasks absorb the
  traffic with the flag off).
- **Gate owner.** Production on-call SRE, co-signed by engineering manager
  owning the feature.

### Phase 4: Full production

- **Goal.** Enable streaming for 100% of production traffic as the default
  chat response mode.
- **Duration / exit criteria.** Day 5 onward. This is the steady-state end
  of the rollout. The phase "exits" only into standard feature
  maintenance — there is no further promotion step.
- **Environment and flag state.** All environments, all task groups at
  `DEEPSEEK_STREAMING_ENABLED=true`. The canary task-group split from
  phase 3 is removed and the flag is made uniform.
- **Monitoring signals.** Standing production alerts on
  `deepseek_stream_error` rate and `circuit_breaker_state=open` (from the
  deployment checklist) remain the primary signals. Keep the dashboard
  panels for `streaming_total_calls`, `streaming_successful_calls`,
  `streaming_failed_calls`, `streaming_avg_duration_ms`,
  `streaming_avg_time_to_first_token_ms`,
  `streaming_avg_chunks_per_response`, and `streaming_enabled` in the
  production overview. Review weekly for the first month.
- **Rollback trigger.** Any page-level alert on the production error rate,
  circuit breaker stuck `"open"` for more than 60 seconds across multiple
  tasks, or `streaming_enabled` flipping to `false` in
  `get_provider_status()` across a majority of tasks (global soft-rollback
  in progress). Manual rollback is
  `DEEPSEEK_STREAMING_ENABLED=false` globally plus a forced ECS
  deployment, per the feature-flag runbook.
- **Gate owner.** Production on-call SRE owns ongoing monitoring; the
  feature author remains the tie-breaker for rollback versus soft-remediate
  decisions for the first two weeks after full enablement.

## Feature-flag runbook

This runbook covers what to do when DeepSeek chat streaming misbehaves in a
running environment. It is organized by rollback path — manual first
(operator-driven flag flip) and automatic second (in-process soft-rollback by
the `ErrorRateTracker`) — followed by the observability signals the operator
uses to make and verify the decision.

### Manual rollback: flip `DEEPSEEK_STREAMING_ENABLED=false`

The quickest kill switch for DeepSeek streaming is the
`DEEPSEEK_STREAMING_ENABLED` environment variable. Setting it to `"false"`
and restarting the service makes every subsequent call to
`DeepSeekAIService.generate_response_stream` take the
`_streaming_disabled_fallback` path, which delegates to the non-streaming
`generate_response` method and emits one terminal `AIResponse` with
`metadata["streaming_fallback"] = True`. User chats continue to work; they
just render as a single final message instead of token-by-token.

**When to use.** Any of the following, in the order of severity that warrants
an operator taking action instead of waiting for the in-process soft-rollback
to engage:

- Page-level alert firing on `deepseek_stream_error` rate (the > 5% over
  5-minute window threshold from the deployment checklist).
- `circuit_breaker_state` reported by `get_provider_status()` is `"open"`
  for more than 60 seconds and not recovering.
- User reports of broken or frozen chat that correlate with the rollout
  window.
- Any situation where the operator wants streaming off across every task
  immediately and deterministically, rather than relying on each task's
  `ErrorRateTracker` to reach its own threshold independently.

**How to apply the flip.** The flag is read once in
`DeepSeekAIService.__init__` and stored on `self.streaming_enabled_config`.
A running process will not pick up a change to the underlying env var — the
service must be restarted (or its task re-deployed).

- Production (AWS ECS Fargate):
  1. In AWS Secrets Manager, update the secret that holds the task's
     environment variables so that `DEEPSEEK_STREAMING_ENABLED=false`.
  2. Force a new ECS deployment on the service so tasks restart with the
     updated env. Do not wait for natural task replacement — the whole
     point of this rollback is determinism.
  3. Confirm task health transitions back to `HEALTHY` before declaring
     rollback complete.
- Staging: same as production, against the staging service.
- Local / dev: edit `.env` to set `DEEPSEEK_STREAMING_ENABLED=false` and
  restart the app (e.g. `make dev` or re-run `uvicorn`). The
  `docker-compose.yml` path uses the same `.env` file, so
  `make down && make up` is sufficient there.

**Verification.** After restart, confirm the rollback is in effect before
closing the incident:

- Trigger a chat message end-to-end and confirm the WebSocket delivers
  exactly one `response_chunk` followed by `response_complete` (the
  fallback path produces a single terminal chunk, so there is no
  per-token streaming visible in the browser).
- Tail application logs and confirm `event="deepseek_stream_start"` is
  **no longer** appearing on new chat requests. The streaming client
  returns from the fallback branch before issuing any HTTP call to
  DeepSeek, so the start event is never emitted.
- Call the provider-status endpoint (or inspect
  `DeepSeekAIService.get_provider_status()` output in logs) and confirm
  `streaming_enabled` is `false` in every task's response. With the
  config flag set to `"false"`, `streaming_enabled` evaluates to `false`
  regardless of the `ErrorRateTracker` state because
  `get_provider_status` ANDs the two gates together.
- Confirm `deepseek_stream_error` events stop in the same window — if
  they continue, the underlying issue is not a streaming-path bug and
  the flag flip will not have fixed it.

**To restore streaming** after the underlying issue is resolved: reverse
the flag flip (`DEEPSEEK_STREAMING_ENABLED=true`) and restart. The
`CircuitBreaker` and `ErrorRateTracker` state is per-process and is
cleared by the restart, so the service comes back up with a clean
resilience slate.

### Automatic soft-rollback: `ErrorRateTracker`

The streaming client runs behind an in-process `ErrorRateTracker`
(`services/provider_resilience.py`) that disables streaming on a
per-instance basis when the observed failure rate exceeds a threshold. This
complements the manual flag flip: the tracker responds in seconds without
operator intervention, but only for the task it runs in. The manual flip
remains the only way to disable streaming uniformly across a fleet.

**Thresholds and window.** The tracker uses the defaults in
`ErrorRateConfig`:

- `window_size_seconds = 300.0` — a 5-minute sliding window of recorded
  calls, where each call is `(timestamp, success: bool)` from
  `record_call`. Entries older than the window are evicted on each new
  sample.
- `disable_threshold = 0.5` — when `streaming_enabled` is currently
  `true` and the observed failure rate over the window reaches or
  exceeds 50%, the tracker flips `streaming_enabled` to `false` and
  emits a WARNING log line:
  `"Streaming disabled due to high error rate: <pct>%"`.
- `enable_threshold = 0.3` — when `streaming_enabled` is currently
  `false` and the observed failure rate drops to 30% or below, the
  tracker flips `streaming_enabled` back to `true` and emits an INFO
  log line: `"Streaming re-enabled, error rate dropped to: <pct>%"`.
- `min_samples = 10` — the tracker will not flip in either direction
  until it has at least 10 samples in the window. On a cold task or one
  that has been idle for more than 5 minutes this delays the first
  possible disable decision until enough traffic has flowed through.

The two thresholds intentionally differ (50% disable, 30% re-enable) so
that a stream hovering around the line does not oscillate. Both are
compared against the same sliding-window failure rate, not against raw
counts.

**How to detect it has engaged.** The tracker does not emit a distinct
structured event on state flip — it logs a plain-text WARNING message
and updates its in-memory state. The authoritative runtime signals are:

- `get_provider_status()` returns `streaming_enabled=false` even though
  the operator has not flipped `DEEPSEEK_STREAMING_ENABLED`. This is
  because the endpoint ANDs the config flag and the tracker's runtime
  gate; when the tracker disables streaming, that AND becomes `false`.
- `get_performance_stats()` returns `error_rate.streaming_enabled=false`
  and `error_rate.error_rate >= 0.5`. This is the cleanest programmatic
  check — `error_rate` is the tracker's own field, independent of the
  config flag.
- A WARNING log entry matching `"Streaming disabled due to high error
  rate"` appears in the task's logs. Alert on this substring if the
  dashboard signal is not enough.
- User-visible chat responses switch from per-token streaming to
  single-message delivery (the fallback path yields one terminal
  `AIResponse` with `metadata["streaming_fallback"] = True`) without
  any deployment having happened.

In a multi-task deployment, the tracker's state is per-task, so different
tasks can have `streaming_enabled=true` and `streaming_enabled=false`
simultaneously depending on which ones hit DeepSeek failures. Compare
the `streaming_enabled` panel across tasks — a single task flipping is
noise; a majority flipping is a global incident.

**Force-reset options.** There is no public method to clear the
`ErrorRateTracker` sliding window without restarting the process; the
tracker intentionally has no escape hatch so that a single request
cannot override the failure signal. If an operator needs to force the
tracker back into `streaming_enabled=true` faster than the 30%
re-enable threshold allows:

- Preferred: wait. Once DeepSeek recovers and the next batch of calls
  succeed, the failure rate in the 5-minute window drops as old failure
  entries age out; the tracker re-enables streaming automatically at or
  below 30% failure rate.
- If immediate recovery is required: restart the task. The
  `ErrorRateTracker` state is per-instance and is cleared on process
  start. Any pre-existing failure backlog is forgotten and the tracker
  starts fresh in `streaming_enabled=true`. This is the same mechanism
  as a normal deploy or the manual flag-flip restart.
- If the circuit breaker has also opened, calling
  `CircuitBreaker.reset()` on the instance returns it to `CLOSED` with
  zeroed counters. This is only reachable programmatically (there is
  no endpoint exposing it today) — if this is needed in production,
  prefer a task restart over adding an ad-hoc reset endpoint.

After a forced or natural reset, verify `streaming_enabled` returns to
`true` in `get_provider_status()` and that
`event="deepseek_stream_start"` resumes on new chat requests before
declaring the tracker recovered.

### Log events to watch

All streaming events are emitted by `DeepSeekAIService` under the
`multimodal_librarian.services.deepseek_ai_service` logger and carry a
`call_id` field (an 8-character UUID prefix) that correlates every event
belonging to a single streamed response. Filter by `call_id` to follow one
request end-to-end.

- **`deepseek_stream_start`** (INFO, Req 9.1). Emitted at the top of
  `generate_response_stream` before any HTTP call. Fields: `call_id`,
  `model`, `prompt_chars`, `message_count`, `temperature`, `max_tokens`.
  Use this as the denominator for error-rate calculations — the count of
  `deepseek_stream_start` events is the count of streaming attempts.
- **`deepseek_stream_first_token`** (INFO, Req 9.2). Emitted on the first
  non-empty delta. Fields: `call_id`, `time_to_first_token_ms`. The
  absence of this event for a given `call_id` despite a
  `deepseek_stream_start` means the stream never produced output (TTFT
  timeout, immediate HTTP error, or disconnect before the first token).
- **`deepseek_stream_complete`** (INFO, Req 9.3). Emitted on a clean
  `[DONE]` sentinel. Fields: `call_id`, `duration_ms`, `chunks_received`,
  `prompt_tokens`, `completion_tokens`, `total_tokens`, `finish_reason`.
  The ratio of `deepseek_stream_complete` to `deepseek_stream_start` is
  the streaming success rate from the logging side (which should match
  `streaming_successful_calls / streaming_total_calls` from
  `get_provider_status()`).
- **`deepseek_stream_error`** (ERROR, Req 9.4). Emitted on any HTTP
  error, TTFT timeout, total-duration timeout, network drop, or
  unhandled exception in the streaming loop. Fields: `call_id`,
  `duration_ms`, `chunks_received_before_error`, `error_type` (one of
  the `ErrorType` values from `provider_resilience.py`),
  `error_message` (truncated to 500 characters). This is the primary
  alerting signal; the production alert from the deployment checklist
  fires on the rate of these events relative to
  `deepseek_stream_start`.
- **`deepseek_stream_malformed_chunk`** (WARNING, Req 1.6). Emitted when
  `parse_sse_line` returns `SSEFrame(kind="malformed")` — a
  `data:` line whose payload failed `json.loads`. Fields: `call_id`,
  `raw_line` (truncated to 200 characters). A handful per day across
  the fleet is expected noise from DeepSeek occasionally emitting
  non-JSON heartbeats; a sustained rate on a single `call_id` suggests
  a protocol change or a proxy corrupting frames and warrants
  investigation even though the streaming loop tolerates it by
  continuing past malformed frames.
- **`deepseek_stream_aborted`** (INFO, Req 7.1, 7.2). Emitted in the
  generator's `finally` block when the WebSocket handler closes the
  generator because the browser disconnected. Fields: `call_id`,
  `reason="client_disconnect"`, `chunks_sent`, `duration_ms`. This is
  not an error; a healthy system will see a steady trickle of these as
  users navigate away mid-response. Alert only if the ratio of aborted
  to complete climbs sharply (user-side network issues or a new client
  bug closing the socket too eagerly).

### Metrics to watch

Two endpoints surface the runtime metrics that drive rollback decisions.
Both are read-only snapshots of in-memory state and are safe to poll at
any rate.

**From `DeepSeekAIService.get_provider_status()`** — the operational
dashboard view, one entry per metric:

- `streaming_total_calls` — cumulative count of streaming invocations
  since process start, including those that failed or fell back. Equal
  to the `deepseek_stream_start` log count over the same window.
- `streaming_successful_calls` — cumulative count of streams that
  reached a clean `[DONE]` (or an accepted `content_filter` finish,
  which is recorded as success per Req 6.5).
- `streaming_failed_calls` — cumulative count of streams that yielded
  a terminal error chunk (HTTP error, timeout, network drop, circuit
  breaker open). The ratio
  `streaming_failed_calls / streaming_total_calls` is the operator's
  high-level success indicator.
- `streaming_avg_duration_ms` — rolling mean wall-clock duration over
  the last 100 successful streams (deque window, not a time window).
  Watch for sudden upward shifts that indicate DeepSeek slowdown.
- `streaming_avg_time_to_first_token_ms` — rolling mean TTFT over the
  last 100 streams where a first token was observed. A sharp rise
  here is an early warning before `deepseek_stream_error` spikes;
  DeepSeek often slows down before it fails outright.
- `streaming_avg_chunks_per_response` — rolling mean chunk count over
  the last 100 successful streams. A sudden drop toward zero suggests
  responses are being truncated early; a sudden rise suggests the
  model is generating runaway output that may hit the total timeout.
- `circuit_breaker_state` — current state of the shared
  `CircuitBreaker` as one of `"closed"`, `"half_open"`, `"open"`.
  `"closed"` is healthy. `"half_open"` means the breaker is probing
  recovery and should transition back to `"closed"` within a few
  successful calls; sustained `"half_open"` suggests DeepSeek is still
  partially failing. `"open"` means all streaming requests are
  short-circuited to a terminal error chunk without an HTTP call — the
  production alert fires on this state persisting for more than 60
  seconds.
- `streaming_enabled` — the composite effective feature flag
  (`streaming_enabled_config AND error_rate_tracker.streaming_enabled`).
  `true` means new chat requests will take the streaming path. `false`
  means either the operator has flipped the config flag or the
  `ErrorRateTracker` has disabled streaming automatically. Compare the
  raw config flag against this composite to tell the two apart.

**From `DeepSeekAIService.get_performance_stats()`** — the richer
view used by the `/api/performance`-style endpoint, keyed by provider
name (`"deepseek"`):

- `circuit_breaker` — the full `CircuitBreaker.get_stats()` payload,
  containing `state`, `failure_count`, `success_count`,
  `last_failure_time`, `last_state_change`, and the active `config`
  (`failure_threshold`, `reset_timeout_seconds`, `half_open_max_calls`).
  Use this to see how close the breaker is to opening (`failure_count`
  approaching `failure_threshold`) and to audit the exact time of
  state transitions. `last_state_change` is an epoch timestamp; pair
  it with the server's current time to compute "how long has the
  breaker been open?" for the 60-second alerting rule.
- `error_rate` — the full `ErrorRateTracker.get_stats()` payload,
  containing `streaming_enabled`, `error_rate` (the current failure
  rate as a float in `[0.0, 1.0]`), `total_calls` (the number of
  samples in the active sliding window), `window_size_seconds`
  (300), `disable_threshold` (0.5), `enable_threshold` (0.3). This is
  the authoritative source for "did the `ErrorRateTracker` engage?"
  — `streaming_enabled` is the tracker's own gate, independent of the
  config flag, and `error_rate` tells you how far past the threshold
  the task is. If `total_calls` is below `min_samples` (10, not
  exposed in the stats payload but documented above), the tracker is
  not making decisions regardless of what `error_rate` shows.

For convenience, the two payloads overlap — `circuit_breaker_state`
and `streaming_enabled` from `get_provider_status()` are derived from
the same underlying state as the richer payloads under
`get_performance_stats()`. Dashboards typically chart
`get_provider_status()` and drill into `get_performance_stats()` when
investigating an incident.
