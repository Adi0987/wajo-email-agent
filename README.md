# Wajo email agent

A proactive email agent that decides, for each email, whether to act silently, act and notify, ask first, or escalate. It learns from your feedback to ask less, and a fixed safety floor caps what learning can unlock.

Python 3.9+, standard library only. Design decisions: [DESIGN.md](DESIGN.md).

## Try it

```
python3 wajo.py
```

Opens the assistant in your browser. Press **Next email** and an email arrives; the assistant tells you what it is, what it wants to do and why, and whether it's asking first or already did it. Answer **Yes**, **No**, **Undo**, or tell it what you'd rather do ("label reading"), and it learns. **Wait a day** moves the clock so follow-ups and deadline reminders fire.

**Admin** has two tabs:
- **Session:** where emails come from (a random sample of a real Enron inbox, acting as that person, or the synthetic test inbox), how many, and who decides (DeepSeek or an offline rule-based stand-in). Starting a new session resets what the assistant has learned.
- **Plant an email:** deliver any email you write, with presets for prompt injection, a spoofed colleague, a wire request, an invoice, a deadline and a newsletter. Tick "Sent by me", then **Wait a day** a few times, to test follow-ups.

The Enron option needs `enron-email-dataset.zip` ([Kaggle](https://www.kaggle.com/datasets/wcukierski/enron-email-dataset)) in this folder; DeepSeek needs `LLM_API_KEY=...` in `.env`. Without them, the synthetic inbox and the offline stand-in work with nothing to set up. Every decision and your response are saved to `runs/audit_<time>.csv`. `python3 wajo.py try` is the same assistant in the terminal.

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
| `app/` | The assistant you talk to: `assistant.py` turns decisions into plain language for both `web.py` (browser) and `cli.py` (terminal). |
| `eval/` | Synthetic inbox, simulated user, metrics, baselines, tuning and transcripts. |
| `tests/` | Unit tests. |
