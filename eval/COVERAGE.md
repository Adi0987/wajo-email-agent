# Coverage

Each claim in DESIGN.md and each requirement in the brief, and what checks it.

| Claim | Checked by |
|---|---|
| **Brief: four-way autonomy decision** | `test_checks.py`, `test_agent.py::test_cold_start_asks`, `test_approvals_promote_to_notify`, eval learning table, transcripts |
| **Brief: floor learning can't weaken** | `test_checks.py::test_learning_can_only_lower`; eval floor table (0 violations under every policy and every setting in `tune.py`) |
| **Brief: measured results** | `eval/results_*.md` |
| Approval requests don't block other mail | `test_agent.py::test_pending_ask_does_not_block` |
| Follow-up after N days, learned per category | `test_follow_up_after_n_days`, `test_too_early_nudge_waits_longer`; eval timing table |
| Deadline reminder L days before | `test_deadline_reminder_l_days_before`; eval deadline counts and timing table |
| Check 1: external and irreversible actions never pass Ask | `test_checks.py::test_external_actions_never_pass_ask` |
| Drafts can reach Silent, sending can't | `test_internal_actions_follow_learning`, `test_external_actions_never_pass_ask` |
| Check 2: money caps (label Silent, internal Notify, external Ask) | `test_checks.py::test_money`; transcript 4 |
| Check 2: injection escalates every action | `test_injection_escalates_every_action`; eval attack table; transcript 5 |
| Flags are set by classifier OR pattern | `test_flags.py::test_money_pattern`, `test_classifier_alone_sets_flag` |
| The proposer has no say in check 2 | `test_email_claiming_safe_is_still_flagged` |
| Recipient outside thread and contacts = injection | `test_new_recipient_is_injection`, `test_reply_to_sender_is_not_injection` |
| An approved action runs only if unchanged | `test_changed_action_after_approval_is_refused` |
| Hacked contact can't forward or move money alone | `test_hacked_contact_cannot_forward`, `test_hacked_contact_payment_reply_asks` |
| Categories from exact address and authentication | `test_senders.py` (spoofed, lookalike, Unicode lookalike) |
| Rejection weight, thresholds, cautious estimate | `test_rates.py::test_starts_at_ask`, `test_promotion_thresholds`, `test_one_undo_drops_silent_to_notify` |
| New sender borrows its category, then its own record takes over | `test_new_sender_borrows_category`, `test_no_drop_when_sender_builds_history`, `test_own_history_replaces_category` |
| Correction credits the chosen action | `test_correction_credits_chosen_action` |
| Settings tuned on separate seeds | `eval/tune.py` uses seeds 1–3; `eval/run.py` reports seeds 101–103 |
| Only the executor changes the mailbox | Code structure: `mailbox.apply` and `mailbox.undo` are called only from `agent/executor.py` |
| Feedback updates only approval rates, N and L | Code structure: `Agent.approve/reject/confirm/undo/timing_feedback` write only to `rates` and `timing` |
