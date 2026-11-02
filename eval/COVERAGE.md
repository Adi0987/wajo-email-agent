# Coverage

Each requirement in the brief and each claim in DESIGN.md, and what checks it.

| Claim | Checked by |
|---|---|
| **Brief: four-way autonomy decision** | `test_checks.py`, `test_gate.py::test_cold_start_asks`, `test_approvals_promote_to_notify`; eval learning table; transcripts |
| **Brief: floor learning can't weaken** | `test_checks.py::test_learning_can_only_lower`; eval floor table (0 violations under every policy and every setting in `tune.py`) |
| **Brief: measured results** | `eval/results_*.md` |
| **Brief: example transcripts** | `eval/transcripts_*.md` (decisions, simulated user), `eval/conversations/` (conversations with Wajo) |
| Every action goes through the gate; Wajo never proposes a reply | `test_gate.py::test_never_proposes_a_reply_on_its_own`; code structure: tools call only `Gate` methods |
| Wajo's messages come from what actually happened | `test_wajo.py::test_messages_speak_from_what_happened`, `test_send_again_after_sending_says_it_was_sent` |
| Context has the email, both sides of the chat, feedback and corrections | `test_llm_steps.py::test_context_has_the_email_and_its_kind`, `test_feedback_goes_in_context`, `test_wajo.py::test_context_has_both_sides_of_the_chat` |
| Replies only when asked, drafted from the user's words, sent only after OK | `test_reply_is_drafted_shown_and_sent_only_after_ok`, `test_no_invented_name_in_drafts`, `test_sending_is_not_learned_as_a_preference` |
| Preferences remembered, updated, used in drafts | `test_new_preference_replaces_the_old_one`, `test_profile_sign_off_used_in_drafts`, `test_unrelated_note_leaves_a_waiting_draft_alone` |
| Approval requests don't block other mail | `test_gate.py::test_pending_ask_does_not_block` |
| Follow-up after N days; N learned or stated; can be cancelled | `test_follow_up_after_n_days`, `test_too_early_nudge_waits_longer`, `test_stated_follow_up_wait_is_used`, `test_cancelled_follow_up_does_not_fire`, `test_follow_ups_stop_once_the_user_says_they_are_not_needed`; eval timing table |
| Deadline reminder L days before; reminders the user asks for | `test_deadline_reminder_l_days_before`, `test_reminder_the_user_asked_for`; eval deadline counts and timing table |
| Check 1: external and irreversible actions never pass Ask | `test_checks.py::test_external_actions_never_pass_ask` |
| Check 2: money caps (label Silent, internal Notify, external Ask) | `test_checks.py::test_money`, `test_gate.py::test_reply_to_a_payment_email_always_asks`; transcript 4 |
| Check 2: manipulation escalates outward actions; the user can still tidy up or reply in the thread | `test_injection_escalates_outward_actions_and_asks_for_the_rest`, `test_user_can_still_trash_an_injection_email`, `test_wajo.py::test_user_can_reply_to_the_sender_of_a_flagged_email`; eval attack table; transcript 5 |
| Flags are set by classifier OR pattern | `test_flags.py::test_money_pattern`, `test_classifier_alone_sets_flag` |
| Wajo has no say in check 2 | `test_email_claiming_safe_is_still_flagged` |
| Recipient outside thread and contacts = manipulation | `test_new_recipient_is_injection`, `test_reply_to_sender_is_not_injection`, `test_hacked_contact_cannot_forward` |
| An approved action runs only if unchanged | `test_changed_action_after_approval_is_refused` |
| A tool call counts only if the mail server says it succeeded | `test_gate.py::test_send_returns_200_and_a_message_id`, `test_failed_tool_call_is_not_counted_as_done` |
| Categories from exact address and authentication | `test_senders.py` (spoofed, lookalike, Unicode lookalike) |
| Rejection weight, thresholds, cautious estimate | `test_rates.py::test_starts_at_ask`, `test_promotion_thresholds`, `test_one_undo_drops_silent_to_notify` |
| New sender borrows the kind of email, then its own record takes over | `test_new_sender_borrows_the_kind_of_email_from_the_first_email`, `test_no_drop_when_sender_builds_history`, `test_own_history_replaces_category` |
| Correction credits the chosen action | `test_correction_credits_chosen_action` |
| LLM: any OpenAI-compatible provider | `test_llm_steps.py::test_falls_back_to_a_plain_request_when_json_mode_is_rejected`, `test_reads_json_with_or_without_fences` |
| Settings tuned on separate seeds | `eval/tune.py` uses seeds 1–3; `eval/run.py` reports seeds 101–103 |
| Only the executor changes the mailbox | Code structure: `mail.act` and `mail.undo` are called only from `policy/executor.py` |
| Feedback updates only approval rates, N and L | Code structure: `Gate.approve/reject/confirm/undo/timing_feedback` write only to `rates` and `timing` |
