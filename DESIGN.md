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
- **Unanswered threads.** The user sent the last message and N days passed with no reply. The agent drafts a follow-up and notifies the user.
- **Deadlines.** The classifier extracts deadlines from incoming mail. The agent notifies the user L days before each one.

N and L are learned per sender category from "too early" / "too late" feedback. Starting values: N = 3 days, L = 1 day.

## 2. Picking a level and the safety floor

The LLM suggests an action. Three checks decide how much the agent does on its own, and the agent follows the most cautious answer.

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
| ≥ 90% | Silent |
| ≥ 80% | Notify |
| < 80% | Ask |

**Enforcement**
- The final level is the lowest of the three checks. Checks 1 and 2 are fixed rules in code. Check 3 is the only one that reads feedback.
- Feedback updates approval rates, N and L. Nothing else.
- Only the executor can change the mailbox. It reruns all three checks before acting, and runs an approved action only if it is unchanged since approval.
- Check 2 triggers if either the classifier or a pattern fires. The classifier sees only the email. The eval reports missed money and injection emails.

## 3. Learning

The agent keeps an approval rate for each action and sender, such as "archive email from news@example.com". Every user response updates it. An approval counts once. A rejection, an undo, or an edit to a draft counts as three rejections, so the agent loses trust faster than it gains it. When the user rejects an action and picks a different one, the rejected action gets a rejection and the chosen action gets an approval.

A new sender has no history, so it starts from its category's rate, counted as 10 responses. Each response from that sender moves the rate toward the sender's own record. Categories: contact, same domain, newsletter (has an unsubscribe header) or unknown.

Categories come from the exact sender address, never the display name. Contact means an address the user has emailed before. Same domain means an exact domain match. Contact and same domain also require passing sender authentication. Anything else is unknown. A hacked contact account gets that contact's trust, and checks 1 and 2 still apply.

The agent uses a cautious estimate of the rate that rises as responses accumulate, so 3 approvals out of 3 does not count as 100%. With no rejections and no category history, an action reaches Notify after 10 approvals and Silent after 21. The eval tunes these thresholds on separate runs from the reported results.

Learning changes how much the agent does alone. The action the LLM suggests stays the same.

## Eval

Mock mailbox, simulated user with hidden preferences.
- **Learning:** ask rate and autonomous error rate per window, against always-ask and fixed-rule baselines.
- **Situations:** nudges and reminders that arrive too early or too late, against the user's hidden timing. Deadline extraction precision and recall.
- **Floor:** adversarial set per risk category. Floor crossings with counts and denominators, classifier recall.

_Results: TBD._

## Example transcripts (from real runs, TBD)

1. Cold start: asks before archiving a newsletter
2. Learned: archives the same kind silently
3. Correction: an undo returns it to Ask
4. Floor: a high-confidence send asks
5. Injection: "forward all mail to …" → Escalate
