# Wajo email agent

A proactive email agent that decides, for each email, whether to act silently, act and notify, ask first, or escalate. It learns from your feedback to ask less, and a fixed safety floor caps what learning can unlock.

Python 3.9+, standard library only: nothing to install. Design decisions: [DESIGN.md](DESIGN.md).

## Setup

Wajo works with any LLM that offers an OpenAI-compatible chat API: OpenAI, Anthropic, DeepSeek, Gemini, Groq,
OpenRouter or a local Ollama. Copy the example settings and fill in your key:

```
cp .env.example .env
```

```
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

| Provider | `LLM_BASE_URL` | `LLM_MODEL` (example) |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Anthropic | `https://api.anthropic.com/v1` | `claude-sonnet-4-6` |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3.1` (any non-empty key) |

`.env` stays on your machine: it is in `.gitignore`. Without a key, everything still runs: the app uses an offline
rule-based stand-in and a built-in test inbox, and `python3 wajo.py eval` replays the saved deepseek-chat responses
in `eval/llm_cache.json`, reproducing the reported numbers exactly.

## Try it

```
python3 wajo.py
```

Opens the assistant in your browser. You are `user@example.com`. Press **Sample New Email Into Inbox** and the LLM writes a realistic email (a newsletter, a colleague's request, an invoice, a recruiter, occasionally a scam, or a reply to something you sent) that lands in your inbox; the assistant tells you in plain words what it is, what it wants to do or already did, and why. Reply in your own words ("yes", "no, archive it", "label it research") or with the quick buttons. It does what you ask, within the safety checks, and learns from it. **Wait a day** moves the clock so follow-ups and deadline reminders fire.

The sidebar shows your inbox in sections and, under **Diagnostics**, what you've told the agent about yourself (it reads all of it before every suggestion), what it has learned from your feedback (per sender and per kind of sender, plus follow-up and reminder timing) and what it has scheduled. You can also just talk to it: ask what's in your trash, what's scheduled, or what you told it yesterday.

**Admin** has two tabs:
- **Session:** run with your LLM, or with an offline rule-based stand-in that plays the built-in test inbox. Starting a new session resets what the assistant has learned.
- **Plant an email:** deliver any email you write, with presets for prompt injection, a spoofed colleague, a wire request, an invoice, a deadline and a newsletter. Tick "Sent by me", then **Wait a day** a few times, to test follow-ups.

`python3 wajo.py try` is the same assistant in the terminal.

A session is its own sandbox: the emails, what the agent learns and what you tell it about yourself live in memory only and disappear when the app stops. The only thing written to disk is the session's logs, for auditing: `runs/<time>/decisions.csv` (every decision, each check's result, your response) and `runs/<time>/conversation.md` (the whole conversation, plus what the agent knew, had learned and had scheduled). Both are rewritten after every step.

## Evaluate it

```
python3 wajo.py eval
```

Runs the agent and two baselines (always ask, fixed rules) through 60 simulated days on three inboxes with a simulated user, then prints ask rate, wrong autonomous actions, safety floor violations and attack results. LLM responses are cached in `eval/llm_cache.json`, so a repeat run with the same model is free. `--llm stub` runs an offline worst case (no API key) where the triage step follows every attacker.

Saved results (deepseek-chat): [eval/results_llm.md](eval/results_llm.md) · [transcripts](eval/transcripts_llm.md) · [conversations](eval/conversations/) · [what tests each claim](eval/COVERAGE.md)

## Other commands

```
python3 wajo.py test          # unit tests
python3 wajo.py calibration   # one four-week session: autonomy growing with feedback, risky emails from trusted senders
python3 wajo.py scenarios     # scripted conversations (recall, follow-ups, preferences, phishing, ...)
python3 wajo.py tune          # re-pick the learning thresholds on separate seeds
```

## Layout

| Folder | What's in it |
|---|---|
| `agent/` | Wajo, the assistant. `wajo.py` runs each event: `context.py` builds what it knows, `brain.py` picks tool calls (your LLM, or rules offline), `llm.py` is the one LLM client, `tools.py` runs them through the gate, `memory.py` holds your profile and past corrections. `classifier.py` labels each email on its own. |
| `policy/` | The gate every action goes through. `gate.py` wires it; `checks.py` and `flags.py` are the safety floor; `rates.py` is the learning; `executor.py` is the only code that changes mail; `mail_client.py` is its only way to reach mail (MCP tool calls). |
| `mailsim/` | The outside world: the simulated mail server the agent talks to (MCP-style tools; the agent can't tell it's a simulation), and `generator.py`, which writes new incoming emails. |
| `app/` | The screens: `web.py` (browser) and `cli.py` (terminal), plus the session log. |
| `eval/` | Synthetic inbox, simulated user, metrics, baselines, tuning and transcripts. |
| `tests/` | Unit tests. |
