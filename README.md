# Wajo email agent

A proactive email agent that decides, for each email, whether to act silently, act and notify, ask first, or escalate. It learns from your feedback to ask less, and a fixed safety floor caps what learning can unlock.

Python 3.9+, standard library only. Design decisions: [DESIGN.md](DESIGN.md).

## Try it

```
python3 wajo.py
```

Opens the assistant in your browser. Press **Sample New Email Into Inbox** and an email arrives; the assistant tells you in plain words what it is, what it wants to do or already did, and why. Reply in your own words ("yes", "no, archive it", "label it research") or with the quick buttons. It does what you ask, within the safety checks, and learns from it. **Wait a day** moves the clock so follow-ups and deadline reminders fire.

The sidebar shows your inbox in sections and, under **Diagnostics**, what you've told the agent about yourself (it reads all of it before every suggestion), what it has learned from your feedback (per sender and per kind of sender, plus follow-up and reminder timing) and what it has scheduled. When Wajo isn't asking anything, whatever you type goes into what it knows about you.

**Admin** has two tabs:
- **Session:** where emails come from (a random sample of a real Enron inbox, acting as that person, or the synthetic test inbox), how many to sample from, and who decides (DeepSeek or an offline rule-based stand-in). Starting a new session resets what the assistant has learned.
- **Plant an email:** deliver any email you write, with presets for prompt injection, a spoofed colleague, a wire request, an invoice, a deadline and a newsletter. Tick "Sent by me", then **Wait a day** a few times, to test follow-ups.

The Enron option needs `enron-email-dataset.zip` ([Kaggle](https://www.kaggle.com/datasets/wcukierski/enron-email-dataset)) in this folder; DeepSeek needs `LLM_API_KEY=...` in `.env`. Without them, the synthetic inbox and the offline stand-in work with nothing to set up. `python3 wajo.py try` is the same assistant in the terminal.

A session is its own sandbox: the emails, what the agent learns, what you tell it about yourself and the audit log live in memory only and disappear when the app stops. Nothing is written to disk. Diagnostics has a **Download the audit log** link (every decision, each check's result and your response) for when you want to keep one.

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
