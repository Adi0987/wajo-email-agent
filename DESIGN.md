# Design

Autonomy depends on two inputs: **risk**, from what the action does and what the email contains, and **preference**, learned from the user's feedback. Risk sets a ceiling. Preference moves autonomy up to that ceiling.

```
 new email ───┐                                         ┌─► classifier (sees only the email)
 your message ┼─► context ─► Wajo (LLM) ─► tool calls ─► gate: 3 checks ─► executor ──MCP tools──► mail server
 scheduler ───┘                    ▲                            │
                                   └── facts about what happened ┘ ◄── you (answer / undo / correct)
```

Two parts with separate jobs.

**Wajo** (`agent/`) is the one assistant the user talks to. Every event (a new email, a message from the user, a reminder coming due) runs the same loop. It builds one context: the email in focus with its thread, state and the decisions made on it; questions waiting on the user; an inbox overview; what's scheduled; what the user has said about themselves; what has been learned for this sender and kind of email; past corrections on similar emails; and the conversation so far. From that it picks tool calls. For a new email it may only propose one triage action. For a user message it can answer a question, act, undo, draft or send a reply, set or cancel a reminder, search the mailbox, or remember something. Its reply is written only from facts about what actually happened, so it can't claim an action it didn't take.

**The gate** (`policy/`) holds the autonomy decision and the safety floor in code. Every tool call goes through it, whatever Wajo asks for. Only its executor holds the mail tools that change anything, and it reaches mail only through MCP-style tool calls (`get_email`, `archive_email`, `send_email`, ...). An action counts as done only when the tool returns success. The server is a simulator (`mailsim/`), but nothing in the agent knows that: a send returns `status 200` and a message id, as a real provider's would.

## 1. Picking a level, and the safety floor

| Level | What happens |
|---|---|
| Silent | Wajo acts |
| Notify | Wajo acts, tells the user, the user can undo |
| Ask | Wajo waits for approval |
| Escalate | Wajo does nothing and warns the user |

Three checks each give a level. The most cautious one wins. Wajo never writes a reply on its own: drafts and sends happen only when the user asks, and every send shows the exact text and waits for a yes.

**Check 1 (floor): what does the action do?**

| Action | Leaves the mailbox | Can't be undone | Most Wajo can do alone |
|---|---|---|---|
| `label`, `archive`, `mark_read`, `trash` | – | – | Silent |
| `send`, `forward`, `unsubscribe` | ✓ | ✓ | Ask |

**Check 2 (floor): what does the email contain?** A separate classifier, which sees only the email, plus fixed patterns. Wajo has no say.

| Email | Pattern | Most Wajo can do alone |
|---|---|---|
| Involves money | amounts, invoices, IBANs, "wire" | Label: Silent. Other internal: Notify. External: Ask |
| Tries to manipulate: instructions to an assistant, getting mail sent out, a scam (urgent or secret payment, impersonation) | any recipient outside the thread and contacts | Forward, unsubscribe, anything to an outside address, or leaving it unflagged: Escalate. Tidying it up, or a reply the user wrote to people already in the thread: Ask |

**Check 3 (learned): how often has the user approved this?** The approval rate for this action, from this sender and for this kind of email (section 3): ≥ 80% Silent, ≥ 60% Notify, below that Ask.

Why learning can't weaken the floor: checks 1 and 2 are fixed rules in code and read no feedback. The executor reruns all three checks before every action, and runs an approved action only if it is unchanged since the approval. Feedback updates approval rates and timing, nothing else. What the user does with a flagged email is not learned at all: it says nothing about their preferences.

## 2. Proactive

Besides new mail and the user's messages, a scheduler raises two things:
- **Unanswered threads.** The user sent the last message and N days passed. Wajo tells the user and drafts a follow-up only if asked. Once the user has mostly said these aren't needed for someone, it stops.
- **Deadlines.** The classifier extracts due dates. Wajo reminds the user L days before.

N and L are learned per kind of sender from "too early" / "too late", or set directly when the user says what they want ("I usually give people a week"). They start at 3 days and 1 day. The user can also ask for, move or cancel reminders. Threads the user trashed or that started as an attack are never chased.

## 3. Learning

Approval rates are kept at two levels: per sender ("archive from news@example.com") and per kind of email ("archive newsletters"; the classifier picks the kind). An approval or a confirmed notice counts as one approval. A rejection or an undo counts as one rejection. When the user picks a different action, the rejected one gets a rejection and the chosen one an approval.

The kind of email's record counts as up to 10 responses, and each response from the sender replaces one of those 10. So a new sender's first email can already be handled (after a few approved newsletters, a new newsletter is archived), and after 10 responses only the sender's own record counts. The second level is the kind of email, not the kind of sender, because a real inbox rarely repeats senders and strangers are too varied to trust as one group.

The rate is a cautious estimate (a lower confidence bound), so 3 approvals out of 3 isn't 100%. With no rejections, an action reaches Notify after 3 approvals and Silent after 7; one rejection after 15 approvals drops it 9 points. The thresholds and rejection weight were tuned on separate seeds from the reported ones: the lowest ask rate with at most 5% wrong autonomous actions.

Feedback also improves the proposals themselves: Wajo's context shows the learned counts and its recent corrections on similar emails ("I proposed archive; the user said no and chose label"), and everything the user has told it about themselves. None of this touches checks 1 and 2. Everything lives in the session; nothing is written to disk except logs.

## Eval

60 simulated days, about 300 emails per seed: newsletters, colleagues, contacts, cold outreach, invoices, deadlines, unanswered threads, and 20 attacks (injection, "this email is safe", spoofed contact, lookalike domain, hacked contact). A simulated user has a hidden correct action per email and hidden timing preferences, flips 5% of its responses, and notices only half of wrong Silent actions. Settings are tuned on seeds 1–3; results are on seeds 101–103. The same Wajo runs in the eval and the app.

## Results (deepseek-chat, seeds 101–103)

| Days | Ask rate | Wrong autonomous actions | Wrong Silent actions |
|---|---|---|---|
| 0–9 | 57% | 5.9% | 0% |
| 10–19 | 27% | 2.0% | 0% |
| 20–29 | 8.0% | 1.1% | 0% |
| 50–59 | 0.8% | 0% | 0% |

- **Floor:** 0 violations in 105 actions the floor applied to. 0 of 60 attacks succeeded, under every policy. 44 were escalated; the other 16 were emails Wajo proposed to trash, held at Ask because even tidying up a flagged email needs the user's OK.
- **Baselines:** always-ask asks 59–70% of the time throughout (leaving an email in the inbox never asks). Fixed rules (no learning) ask almost never, but 19.5% of their autonomous actions are wrong in the first 10 days.
- **Detection:** money 114/114, manipulation 51/51, deadlines 117/120 with 9 false. The money templates always contain an amount or "invoice", so money recall is easier here than on real mail.
- **Timing:** in the second half, 64 of 68 nudges and reminders had the right timing; none were unwanted.
- **One long session in the app** ([calibration.md](eval/conversations/calibration.md)): asks fell from 64% in the first two weeks to 4% in the last two, 0 wrong autonomous actions, and nothing left the mailbox without the user's OK, including a wire request, a forward to a personal Gmail and a card-details request from senders Wajo already trusted.

Full tables: [eval/results_llm.md](eval/results_llm.md). Offline worst case (the triage step follows every attacker, the classifier detects nothing): [eval/results_stub.md](eval/results_stub.md), also 0 floor violations.

## Limitations

- The simulated user is consistent apart from noise. Real preferences drift, and a real user ignores many notices, which teaches nothing and keeps those actions at Notify (seen in the calibration session).
- Detection is measured on templates. Real phishing varies more than the patterns cover; the classifier is the main defense there.
- The LLM can still word a draft more fully than the user asked ("thanks for your patience"). It never adds facts or commitments in the transcripts, but drafts are always shown before sending for this reason.

## Example transcripts

- [eval/transcripts_llm.md](eval/transcripts_llm.md): decisions from the eval (cold start, learned, correction, money cap, injection, follow-up).
- [eval/conversations/](eval/conversations/): conversations with Wajo in the app. [calibration.md](eval/conversations/calibration.md) is one four-week session: autonomy growing per sender, and risky emails from trusted senders. Others cover recall, follow-ups, inbox management, preferences, phishing and more.
