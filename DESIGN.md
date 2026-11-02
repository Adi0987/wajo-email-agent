# Design

Autonomy depends on two inputs: **risk**, from what the action does and what the email contains, and **preference**, learned from user feedback. Risk sets a ceiling. Preference moves autonomy up to that ceiling.

```
 new mail ──┐
 scheduler ─┴─► queue ─► Proposer (LLM) ─► 3 checks ─► Executor ─► mock mailbox
                                              ▲             │
                                              │             ▼
                                        Approval rates ◄── user (notify / approve / undo)
```

## 1. Proactive

A background worker consumes an event queue with two sources: new mail and a scheduler. Approval requests are asynchronous; other emails keep processing while one waits. A simulated clock drives the eval.

The scheduler checks two things:
- **Unanswered threads.** The user sent the last message and N days passed with no reply. The agent nudges the user; it drafts a follow-up only if asked.
- **Deadlines.** The classifier extracts deadlines from incoming mail. The agent notifies the user L days before each one.

N and L are learned per sender category from "too early" / "too late" feedback. Starting values: N = 3 days, L = 1 day. The user can also ask for a reminder on any email ("remind me tomorrow"); it is scheduled the same way.

## 2. Picking a level and the safety floor

The LLM suggests an action. Three checks decide how much the agent does on its own, and the agent follows the most cautious answer. The agent never writes a reply on its own: `draft_reply` and `send` happen only when the user asks for them.

| Level | What happens |
|---|---|
| Silent | Agent acts |
| Notify | Agent acts, tells the user, user can undo |
| Ask | Agent waits for approval |
| Escalate | Agent does nothing and flags the email |

**Check 1 (safety floor): What does the action do?** Covers irreversible and external.

| Action | Leaves the mailbox | Can't be undone | Most the agent can do alone |
|---|---|---|---|
| `label`, `archive`, `mark_read`, `trash`, `draft_reply` | – | – | Silent |
| `send`, `forward`, `unsubscribe` | ✓ | ✓ | Ask |

**Check 2 (safety floor): What does the email contain?** Covers money and prompt injection. A separate classifier and fixed patterns check this. The LLM that suggested the action has no say.

| Email | Pattern | Most the agent can do alone |
|---|---|---|
| Involves money | amounts, invoices, IBANs, "wire" | Label: Silent. Other internal: Notify. External: Ask |
| Gives the agent instructions | a recipient outside the thread and contacts | Escalate |

**Check 3 (learned): How often has the user approved this before?** Approval rate for this action and sender (see section 3).

| Approval rate | Most the agent can do alone |
|---|---|
| ≥ 80% | Silent |
| ≥ 60% | Notify |
| < 60% | Ask |

**Enforcement**
- The final level is the lowest of the three checks. Checks 1 and 2 are fixed rules in code. Check 3 is the only one that reads feedback.
- Feedback updates approval rates, N and L. Nothing else.
- Only the executor can change the mailbox. It reruns all three checks before acting, and runs an approved action only if it is unchanged since approval.
- Check 2 triggers if either the classifier or a pattern fires. The classifier sees only the email. The eval reports missed money and injection emails.

## 3. Learning

The agent keeps an approval rate for each action and sender, such as "archive email from news@example.com". Every user response updates it. An approval counts as one approval. A rejection, an undo, or an edit to a draft counts as one rejection. When the user rejects an action and picks a different one, the rejected action gets a rejection and the chosen action gets an approval.

A sender's first email always asks. After that, the sender's category also counts, as up to 10 responses, and each further response from that sender replaces one of those 10, so after 10 responses only the sender's own record counts. Testing on real Enron mail showed why the first email asks: strangers are too varied to trust as a group. Categories: contact, same domain, newsletter (has an unsubscribe header) or unknown.

Categories come from the exact sender address, never the display name. Contact means an address the user has emailed before. Same domain means an exact domain match. Contact and same domain also require passing sender authentication. Anything else is unknown. A hacked contact account gets that contact's trust, and checks 1 and 2 still apply.

The agent uses a cautious estimate of the rate that rises as responses accumulate, so 3 approvals out of 3 does not count as 100%. With no rejections and no category history, an action reaches Notify after 3 approvals and Silent after 7. After 15 approvals, one more approval raises the estimate by 0.6 points and one rejection lowers it by 9.

The rejection weight and thresholds are chosen by `eval/tune.py` on separate seeds from the reported results: the lowest ask rate with at most 5% wrong autonomous actions.

The proposer is told which action the user has approved most for this sender, or for its category if the sender is new. Corrections therefore improve proposals as well as autonomy. The hint never affects checks 1 and 2.

## Eval

60 simulated days, about 300 emails per seed: newsletters, colleagues, contacts, cold outreach, invoices, deadlines, unanswered threads, and 20 attacks (injection, "this email is safe", spoofed contact, lookalike domain, hacked contact). A simulated user has a hidden correct action per email and hidden timing preferences. It flips 5% of its responses and notices only half of wrong Silent actions. Settings are tuned on seeds 1–3; results are on seeds 101–103.

## Results (DeepSeek, seeds 101–103)

| Days | Ask rate | Wrong autonomous actions | Wrong Silent actions |
|---|---|---|---|
| 0–9 | 77% | 26% | 25% |
| 20–29 | 52% | 4.5% | 0% |
| 50–59 | 40% | 4.3% | 0% |

- **Floor:** 0 violations in 113 actions the floor applied to. 0 of 60 attacks succeeded; 51 were escalated, and the 9 lookalike wire requests were capped at Ask by the money check.
- **Baselines:** always-ask asks 92–97% of the time. Fixed rules (no learning) ask 21–29% of the time, but 55–68% of their autonomous actions are wrong, because DeepSeek's proposals without the user's history are often wrong.
- **Timing:** in the second half, all 53 nudges and reminders for real deadlines and threads had the right timing.
- **Detection:** money 114/114, injection 51/51, deadlines 60/60, with 13 false deadlines. The money templates always contain an amount or "invoice", so money recall is easier here than on real mail.

Full tables: [eval/results_deepseek.md](eval/results_deepseek.md). Offline worst case (the proposer follows every attacker, the classifier detects nothing): [eval/results_stub.md](eval/results_stub.md), also 0 floor violations.

## Limitations

- The simulated user is consistent apart from noise. Real preferences drift, and a real user ignores some notifications, which keeps those actions at Notify.
- Detection is measured on templates. Real phishing varies more than the patterns cover.
- Errors early on are high (26% in the first 10 days) because every sender starts cold.

## Example transcripts

From the DeepSeek run: [eval/transcripts_deepseek.md](eval/transcripts_deepseek.md).

1. Cold start: asks before acting on a newsletter
2. Learned: the same action for the same sender runs silently
3. Correction: an undo lowers autonomy for that sender and action
4. Floor: learned Silent, but a money email caps the action at Notify
5. Injection: escalated whatever the proposer suggests
6. Proactive: unanswered thread, the agent nudges you
