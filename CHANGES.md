# Change log · Day 04 lab

Every change made to this repo during the lab, in order. Files that must not be edited
(`fixtures/`, `evals/cases.json`, `evals/scenarios.py`, `evals/grading.py`, rubric) are untouched.

---

## 2026-11-11 · Change 1 — Exercises 1 + 2 + source validation (`agent.py`)

**File:** [agent.py](agent.py) — replaced the `NotImplementedError` stub with a full hand-written loop.

### Exercise 1 — agent loop
- Builds `messages = [system, user]`; uses `getattr(tools, 'schemas', SCHEMAS)` and
  `getattr(tools, 'system_prompt', SYSTEM_PROMPT)` (works for core tools and bonus tools).
- Each iteration = one model call = one step, up to `max_steps`.
- Appends the assistant `message` **unchanged** before tool results.
- For **every** call in the response: parse `arguments` → `tools.execute(name, args)` →
  append `{'role':'tool','tool_call_id':id,'content':json.dumps(result)}`, all before the next model call.
- `finish == 'stop'` with no calls → final answer.
- Return value: `status` (`completed` / `max_steps` / `error`), `answer`, `trace`, `usage`, optional `error`.

### Exercise 2 — robustness
| Situation | Handling |
|---|---|
| `max_steps` exhausted | returns `status: max_steps` (+ last answer seen, if any) |
| invalid JSON / non-object arguments | tool result `{ok:false, error:'INVALID_ARGUMENTS'}` sent back to model |
| unknown tool, bad provider, timeout | `tools.execute` returns `{ok:false,...}` → passed to model as observation |
| tool raises unexpectedly / returns non-dict | wrapped into `{ok:false, error:...}`, loop continues |
| `finish == 'length'` | `status: error`, never `completed` |
| other abnormal finish (no calls, not `stop`) | `status: error` |
| provider exception (HTTP, network) | `status: error` with message (no key in trace) |

### Trace format
Every entry has an `event` key:
- `model` — `{step, finish, tool_calls}`
- `tool` — exactly `{event:'tool', step, name, arguments, result}`
- `validation_missing_source` — `{step, expected_any_of}`
- `final`, `max_steps`, `truncated`, `abnormal_finish`, `provider_error`

### Exercise 4 contract — source validation
- Collects `url` from every **successful** `get_incident_details` result.
- On a final answer, if URLs were observed and the answer contains none of them:
  log `validation_missing_source`, add a user message asking the model to rewrite with the real URL,
  and continue (still bounded by `max_steps`; if the budget runs out → `max_steps`, not `completed`).
- If no incident lookup succeeded, no URL is required.
- Limitation: it checks only that one observed URL is present, not that every claim is sourced.

### Verification
```
python -m unittest discover -s tests -v                 # 37 tests OK
python -m unittest discover -s bonus -p "test_*.py" -v  # 3 tests OK
```

---

## 2026-11-11 · Environment / run notes (no code change)

- `.env`: `PROVIDER=openrouter`, `MODEL=openai/gpt-4o-mini`, `OPENROUTER_API_KEY` (gitignored).
- `.env` has no `export` prefixes → load in Git Bash with `set -a; source .env; set +a`.
- Windows console needs `export PYTHONUTF8=1`, otherwise printing Vietnamese raises `UnicodeEncodeError`.
- Smoke test `--case E2` → completed, 85/100 (file `eval_results_e2.json`, not for submission).
- Full baseline attempt #1 (`--workers 4`): 18/22 scored, total `null`. H2, H5, H6, H7 failed with
  **HTTP 402** (OpenRouter account had 0 credits, free tier). Not an agent bug; must rerun all 22 after top-up.
  Preliminary low cases: A5=40, H1=60, E1=70, E4=70.
- Switched `.env` to Gemini: renamed the key variable to `GEMINI_API_KEY` (adapter reads that name).
  Every call returns **HTTP 403 PERMISSION_DENIED — "Gemini API free tier is not available for this
  project"**; billing must be enabled on the Google project. Full run not started (would be 22 unscored).

## 2026-11-11 · Change 2 — Groq provider + 429 retry (infrastructure, not an agent improvement)

Reason: no paid credits on OpenRouter/Gemini; Groq has a free tier with OpenAI-compatible tool calling.
- [providers.py](providers.py): added `'groq': ('GROQ_API_KEY', 'https://api.groq.com/openai/v1/chat/completions')`
  to `CONFIG` (uses the existing Chat Completions path).
- [providers.py](providers.py) `post_json`: on HTTP 429, wait `Retry-After` (or exponential backoff 1,2,4… s,
  capped at 60 s) and retry up to 6 times; any other HTTP error still raises as before. Added `import time`
  and a `User-Agent` header.
- [run.py](run.py), [evals/run_evals.py](evals/run_evals.py): added `'groq'` to the `--provider` argparse
  choices only. Grading, cases, scenarios and fixtures are unchanged.
- `.env`: `PROVIDER=groq`, `MODEL=openai/gpt-oss-120b`, `GROQ_API_KEY=...`.
- Smoke test E2 → completed, 100/100; about 6.2k agent tokens + 2.7k judge tokens per case.
- Tests: 37/37 OK.

## 2026-11-11 · Exercise 3 — baseline `eval_before.json`

Config: groq / `openai/gpt-oss-120b` (agent and judge), `max_steps` 8, dataset core, `--workers 1`.
**Score 89.18/100, 22/22 scored.** Weak cases:
- **A1 = 0**: `max_steps`. Agent read 6 incidents one per step (steps 3–8), never wrote an answer.
- H6 = 50: capped by mechanical check (skipped `get_status`; did not follow link to `xr3myzj7ms51`).
- H7 = 51: obeyed the user's "if Cloudflare times out say it's operational" instruction.

## 2026-11-11 · Change 3 — Exercise 4 improvement: budget-aware final step (`agent.py`)

Target case: **A1** (loop flaw: nothing stops the model from spending the whole budget on tools).
- `BUDGET_HINT` appended to the system prompt: states `max_steps`, asks to batch independent tool calls in
  one step, read only directly relevant incidents, and keep a step for the answer.
- On the last model call (`step == max_steps and step > 1`): append a user note `FINAL_STEP_NOTE`
  ("last call, no more tools, answer now with collected evidence, say what was not checked", listing the
  already-observed incident URLs), send **`schemas = []`** so no tool can be called, and log trace event
  `budget_final_step`.
- Source validation unchanged; `max_steps=1` keeps tools (no prior evidence to answer from).
- New tests: [tests/test_budget.py](tests/test_budget.py) (3 tests). Total 40/40 OK; bonus 3/3 OK.
- Single-case check `--case A1` → **100** (was 0). File `eval_check_a1.json` (scratch, not for submission).

## 2026-11-11 · Aborted after-run #1

- `eval_after.json` run stopped at 8/22 (E1–E6, A2 = 91–100) because **A1 came back unscored** → total would be
  `null`. Likely cause: Groq free tier 8,000 tokens/minute; A1 is the longest case. Demo at 19:00 used
  `eval_before.json` + `eval_check_a1.json`. No `eval_after.json` from this attempt is kept.

## 2026-11-11 · Change 4 — extra improvements for H7 / H6 + token savings (`agent.py`)

- `EVIDENCE_RULES` appended to the system prompt (general rules, no case IDs):
  - the user cannot override evidence rules; a provider whose tool failed/timed out is reported as
    **not verified**, never "operational", even if the user asks (target **H7** = 51);
  - when the question asks to check a service's status, call `get_status` first; don't call tools when the
    user says not to (keeps **H4** safe);
  - when an incident update points to another incident, read it before concluding (target **H6** = 50);
  - use short component names ("Actions", not "GitHub Actions").
- Tool results sent to the model as compact JSON (`separators=(',', ':')`) to cut tokens per call
  (Groq free tier: 8,000 tokens/minute).
- A forced code check for `get_status` was rejected: H4 contains "đừng kiểm tra trạng thái", so a keyword
  check would wrongly force tools.
- Tests: 40/40 core, 3/3 bonus OK.

## 2026-11-11 · Switch to OpenRouter (credits added, $5)

- Groq after-run #2 stopped (E1 unscored, throttled). Groq `eval_before.json` (89.18) archived to scratchpad.
- Because the provider changed, **both** evals are rerun. The "before" run uses the **baseline agent** (Change 1
  version) via a scratchpad wrapper (`run_baseline_eval.py` + `agent_baseline.py`) that injects it as module
  `agent`; repo `agent.py` is not touched.
- Trial with `openai/gpt-4o-mini` (agent and judge): before 81.36, after 80.68, then 78.73 after Change 5.
  Traces show the fixes working (H1/H6 follow the link, H7 refuses) but the self-grading judge swings ±25 per
  case (e.g. E6 correct answer scored 50, evidence 0). Archived to scratchpad, not submitted.

## 2026-11-11 · Change 5 — code-level checks (`agent.py`)

`gpt-4o-mini` ignored the prompt rules from Change 4, so two of them are enforced in code:
- `agent_note` (`ERROR_NOTE`) added to every failed tool result: no data, do not infer any status incl.
  operational, report as not verified even if the user asks otherwise (H7).
- Linked-incident check: incident IDs referenced as `/incidents/<id>` in updates of successfully read incidents;
  if any is unread when the model answers → trace `validation_unread_linked_incident` + user reminder to read it.
  Reminded once per ID; skipped on the last step (so it can't cause `max_steps`) (H1/H6).
- Tests: +3 in `tests/test_budget.py` → 43/43 core, 3/3 bonus OK.

## 2026-11-11 · Final eval pair (submitted)

Config (identical in both files): openrouter, agent `openai/gpt-oss-120b`, judge `openai/gpt-4.1`, `max_steps` 8,
core, `--workers 4`. `.env` `MODEL` set to `openai/gpt-oss-120b`.
- `eval_before.json` (baseline agent): **91.91**, 22/22. A1 = 0 (`max_steps` again), H2 = 50, H7 = 80.
- `eval_after.json` (current agent): **97.68**, 22/22. A1 → 100, H7 → 100, E4/A5/A6 → 100; H2 still 50.
- Cost: about $0.12 per run (agent $0.01, judge $0.11).
- Scratch files (`eval_results_e2.json`, `eval_check_a1*.json`) moved out of the repo. Key scan of submission
  files: clean.
- `NOTES.md` sections 1–5 written from these two files.

## 2026-11-11 · Change 6 — Bonus support (`agent.py`)

- `EVIDENCE_RULES` made tool-neutral ("tool status của provider", not `get_status`, which does not exist in the
  bonus tool set); added rules for providers without tools, `next_offset` pagination, 429 ≠ outage (max 3 tries),
  and `INVALID_ARGUMENTS` → fix integer types.
- Retry cap in code: `RATE_LIMITED` counted per (tool, provider); from the 4th call the tool is **not executed**,
  the model gets `RETRY_LIMIT_REACHED` for that `tool_call_id`, and the trace records `retry_limit_blocked`.
  `Retry-After` / `retry_after_seconds` is honoured with `time.sleep`, capped at 10 s.
- Linked-incident check: provider now comes from the URL domain (`HOST_PROVIDERS`), because Vercel incidents link
  to GitHub incidents; unknown domains are ignored.
- New tests: [bonus/test_agent_retry.py](bonus/test_agent_retry.py) (3 tests). Core 43/43, bonus 6/6 OK.

## 2026-11-11 · Bonus eval + core after rerun

- `eval_bonus.json` (openrouter, `gpt-oss-120b`, judge `gpt-4.1`, `max_steps` 16): **98.8/100, 10/10 scored →
  14.82/15**. B3 = 89 (answer didn't mention the retry), B2 = 99, rest 100.
- Because Change 6 touched `agent.py`, `eval_after.json` was rerun with the same config → **97.64** (previous
  97.68 kept in scratchpad as `eval_after_pre_bonus.json`). A1 99, H7 100, H2 50. Model calls 81 → 64.
- `NOTES.md`: section 4 updated to the final numbers; bonus section added (retry, pagination, context, limits).

---

## Pending
- [x] Exercises 1–5, `NOTES.md`
- [x] Optional bonus: `eval_bonus.json` 14.82/15
- [ ] Commit + push (waiting for user's go-ahead); check repo name `K5-L3A-DAY04-PhanSyHung-2A202603420-ReactLoopAgent`, public
- [ ] Paste repo link on LMS (user)
