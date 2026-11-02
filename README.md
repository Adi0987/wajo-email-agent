# Wajo email agent

A proactive email agent that decides, for each email, whether to act silently, act and notify, ask first, or escalate. It learns from your feedback to ask less, and a fixed safety floor caps what learning can unlock.

Python 3.9+, standard library only. Design decisions: [DESIGN.md](DESIGN.md).

## Try it

```
python3 wajo.py try
```

You are the user. Emails arrive one at a time, and the agent talks to you like an assistant: what the email is, what it wants to do and why, and why it's asking (or that it went ahead). You approve, reject, undo, or tell it what you'd rather do, and it learns. `--details` also shows each safety check's result. A summary prints at the end, and every decision is saved to `runs/audit_<time>.csv`.

- With `enron-email-dataset.zip` ([Kaggle](https://www.kaggle.com/datasets/wcukierski/enron-email-dataset)) in this folder, a random sample of a real Enron inbox arrives one email at a time, different each run (`--persona kaminski-v`, `--count 20`). This uses DeepSeek: put `LLM_API_KEY=...` in `.env`.
- Without it, or with `--offline`, emails come from the synthetic inbox and no API key is needed.

## Evaluate it

```
python3 wajo.py eval
```

Runs the agent and two baselines (always ask, fixed rules) through 60 simulated days on three inboxes with a simulated user, then prints ask rate, wrong autonomous actions, safety floor violations and attack results. DeepSeek responses are cached in `eval/llm_cache.json`, so this needs no API key. `--llm stub` runs an offline worst case where the proposer follows every attacker.

Saved results: [eval/results_deepseek.md](eval/results_deepseek.md) · [transcripts](eval/transcripts_deepseek.md) · [what tests each claim](eval/COVERAGE.md)

## Other commands

```
python3 wajo.py test    # unit tests
python3 wajo.py tune    # re-pick the learning thresholds on separate seeds
```

## Layout

| Folder | What's in it |
|---|---|
| `agent/` | The agent. `agent.py` wires it; `checks.py` and `flags.py` are the safety floor; `rates.py` is the learning; `executor.py` is the only code that changes the mailbox. |
| `eval/` | Synthetic inbox, simulated user, metrics, baselines, tuning, transcripts, the `try` session and the Enron loader. |
| `tests/` | Unit tests. |
