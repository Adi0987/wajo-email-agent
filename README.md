# Wajo email agent

A proactive email agent that decides, for each email, whether to act silently, act and notify, ask first, or escalate. It learns from feedback to ask less, and a fixed safety floor caps what learning can unlock.

- Design decisions: [DESIGN.md](DESIGN.md)
- Results: [eval/results_deepseek.md](eval/results_deepseek.md), offline worst-case run in [eval/results_stub.md](eval/results_stub.md)
- Transcripts: [eval/transcripts_deepseek.md](eval/transcripts_deepseek.md)
- What tests each claim: [eval/COVERAGE.md](eval/COVERAGE.md)

Python 3.9+, standard library only.

## Run

```
python3 -m unittest discover -s tests -t .   # unit tests
python3 -m eval.run --llm stub                # eval offline, worst-case stand-in for the LLM
python3 -m eval.run --llm deepseek            # eval with DeepSeek (LLM_API_KEY in .env)
python3 -m eval.tune --llm deepseek           # pick rate settings on tuning seeds
python3 -m eval.transcripts --llm deepseek    # write example transcripts
python3 run_agent.py                          # type your own emails and answer the agent (DeepSeek)
```

To try the agent on a real inbox, download the [Enron dataset](https://www.cs.cmu.edu/~enron/), extract it here (it creates `maildir/`, which git ignores), then:

```
python3 run_agent.py --enron maildir --person kaminski-v --count 30
```

It acts as that person: their sent mail becomes history (contacts), and a random sample of their inbox arrives one email at a time.

Every decision and your response are saved to `runs/audit_<time>.csv` (one row per decision: proposal, each check's result, final level, classifier flags, your response). A summary prints when the session ends.

DeepSeek responses are cached in `eval/llm_cache.json`, so the DeepSeek eval reruns without an API key.

## Layout

| File | Does |
|---|---|
| `agent/agent.py` | Background worker: queue in, decisions out, feedback back |
| `agent/checks.py` | Checks 1 and 2: the safety floor |
| `agent/flags.py` | Money and injection flags: classifier OR patterns |
| `agent/rates.py` | Check 3: learned approval rates |
| `agent/executor.py` | The only code that changes the mailbox; reruns the checks |
| `agent/approvals.py` | Pending approvals, each bound to one exact action |
| `agent/scheduler.py`, `agent/timing.py` | Follow-ups and deadline reminders, learned timing |
| `agent/senders.py` | Sender categories |
| `agent/proposer.py`, `agent/classifier.py`, `agent/prompts.py`, `agent/llm.py` | LLM steps |
| `agent/mailbox.py`, `agent/models.py`, `agent/notices.py` | Mock mailbox and shared types |
| `agent/audit.py` | Audit log of decisions and responses for `run_agent.py` |
| `eval/inbox.py`, `eval/user.py` | Synthetic inbox with ground truth, simulated user |
| `eval/simulate.py`, `eval/metrics.py`, `eval/report.py`, `eval/run.py` | Run the eval and report results |
| `eval/baselines.py`, `eval/stub_llm.py`, `eval/llm_steps.py` | Baselines and LLM setup |
| `eval/tune.py`, `eval/transcripts.py` | Tuning and example transcripts |
| `tests/` | Unit tests |
