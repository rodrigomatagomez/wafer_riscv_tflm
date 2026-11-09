# Section 2 — per-incident classification table (timer scope / timeout causes)

Every row is tied to a specific documented incident in `docs/issues.md` /
`docs/development_log.jsonl`. "Cause not established" is used verbatim
where the source material itself leaves this open (quoting its own hedge
words, not softening a confirmed finding).

| # | run_id / incident | Symptom (file:line) | Classification | Config/marker it is tied to | Confidence |
|---|---|---|---|---|---|
| 1 | `case0_attempt_001` bounded probe | `docs/issues.md:47-48,65-69` — `SIM_TIMEOUT` fired at cycle 5,000,000 under `+MAXCYCLES=5000000` | testbench `SIM_TIMEOUT` (cycle-count cutoff, not wall-clock) | `tb/soc_tb.sv:212-217`, `+MAXCYCLES` plusarg | CONFIRMED |
| 2 | `case0_attempt_001` `run_simulation` call | `docs/issues.md:79` — MCP tool call exceeded harness's own 300s idle wait while the job kept running server-side | client/MCP waiting timeout (harness-side, non-configurable, distinct from `timeout_seconds`) | fixed 300s client idle timeout | CONFIRMED |
| 3 | `cases1_19_attempt_001` | `docs/issues.md:92-99` — progress frozen 20+ min, daemon still consuming CPU, no cancel API available, terminated via SIGTERM | stalled daemon, root cause **not isolated** ("may have been a genuine RTL/data-dependent hang... a simulator-side scheduling anomaly, or an extreme, unexplained buffering delay") | none confirmed — explicitly not attributed to `timeout_seconds`, SIM_TIMEOUT, or quota | UNAVAILABLE (cause not established, by the source document's own words) |
| 4 | `case2_diag_001` | `docs/development_log.jsonl:37` (E038) — idle after progress to ~cycle 5,961,876, two independent CPU-delta measurements = 0 jiffies | stalled daemon, same unresolved-cause family as #3; Zenith-level/`timeout_seconds`-level causes explicitly ruled out before terminating | none confirmed | UNAVAILABLE (cause not established) |
| 5 | `full20_attempt_001` | `docs/issues.md:112-118` — 0-byte `zsim.log`, zero CPU-time delta, `cwd` reverted, only one idle socket fd | hedged ("**most likely**") attribution to the disk-quota exhaustion in `docs/storage_cleanup.md` | disk/quota incident (separate from ISS-007) | PARTIALLY SUPPORTED — circumstantial/timing correlation, not a direct causal trace |
| 6 | "Wall-clock cap (30 min) reached -- simulation cancelled." | `docs/issues.md:128-132` (ISS-009) | Attributed **by elimination** to Animas-backend `run_simulation`'s `timeout_seconds` (Zenith's own `--help` has no wall-clock flag at all) | `timeout_seconds` (inferred, not directly traced to a log line/GUI source) | PARTIALLY SUPPORTED — Zenith is confirmed ruled OUT directly; the positive attribution to `timeout_seconds` is inference, not a traced log line. No run_id/timestamp is attached to this message anywhere in the record. |
| 7 | Every `mcp__animas__*` call (recurring) | `docs/issues.md:17-31` (ISS-002) — `MCP error -32602`; `animas.log`: "Received request before initialization was complete" at `session.py:383` | connectivity/session-handshake failure, unrelated to timeout/quota | MCP `initialize` handshake desync | CONFIRMED (explicitly, repeatedly, never linked to timeout/quota anywhere in the record) |
| 8 | `docs/animas_capabilities.md` append failure | `docs/issues.md:101-110` (ISS-007) — `cat: write error: Disk quota exceeded` | storage/quota failure, confirmed cause: `waveform_mode="off"` unreliable + accumulated ZWDB files | per-user disk quota, ZWDB accumulation | CONFIRMED |
| 9 | `.git/index.lock` quota incident (sibling repo) | `docs/storage_cleanup.md`, `docs/development_log.jsonl:40` (E041) | storage/quota failure, separate incident from #8 | per-user disk quota (block/byte, not inode) | CONFIRMED |

## Reconciling the two `timeout_seconds` framings

- "Job-level allowance" framing (`docs/animas_capabilities.md:169-172`): "...is
  therefore the only documented, per-run-configurable wall-clock-affecting
  setting in this whole stack... Passing a larger value... is the correct,
  supported way to ask for a longer **wall-clock allowance for one job**."
- The product-reviewer framing ("only bounds waiting, a separate GUI cap
  cancels jobs") is **not found verbatim in any project document** — no
  file in this repository describes `timeout_seconds` as a pure
  wait/response-only bound, or claims a separate Animas-GUI-level wall-clock
  cap distinct from `timeout_seconds` exists.
- What IS attested, consistently, across `docs/animas_capabilities.md`,
  `docs/decisions.md`, `docs/issues.md`, `docs/development_log.jsonl`: (a)
  `timeout_seconds` is the backend's per-job wall-clock allowance on the
  `run_simulation` tool call; (b) a categorically separate, non-configurable
  **300-second harness/MCP-client idle timeout** also exists and is
  explicitly called "a different thing."
- Conclusion for the reply package: **do not assert the reviewer's
  "GUI-level cap distinct from timeout_seconds" framing as confirmed** --
  it is not corroborated by any artifact in this project, and the project's
  own attribution of the "Wall-clock cap (30 min)" message to
  `timeout_seconds` is itself inference-by-elimination, not a traced log
  line. Recommend reporting both framings side by side, neither as proven,
  per the governing instructions.
