# Kavach data generation guide

Read this fully, then `scenario.json` (same folder), before writing anything.

You are producing part of a realistic synthetic dataset for **Kavach**, a customer-support agent for
**Sahyadri Bank**, a fictional Pune-based bank. The data must look like a real bank's export: messy,
inconsistent, human, full of the small details real records have. `scenario.json` is the ground truth
(the answer key). Every fact you write about a scenario customer, payment, scammer contact or account
must match it exactly.

## Hard rules

1. **Never leak the answer key.** Do not write ring ids (R1…R4) or the words "ring", "mule", "victim",
   "gang", "fraud network" into the data. A bank employee may write "suspected fraud", "beneficiary
   a/c", "possible cyber fraud", "same number reported earlier" — the way real staff write.
2. **Phone numbers:** only numbers that appear in `scenario.json`, or new ones in the same format
   `+91 5XXXX XXXXX` (10 digits starting with 5: not a real Indian mobile range). The only other numbers
   allowed are the bank helpline in `scenario.json` and the national cyber helpline **1930**.
3. **No real people or organisations as actors.** Emails only `@example.com` / `@example.in`
   (bank staff: `@sahyadribank.example.in`). Counterparty banks only from `scenario.json` / its fictional
   list. Real apps (AnyDesk, TeamViewer QuickSupport, Telegram, WhatsApp) may appear only as tools
   misused by scammers — never say those companies did anything wrong. QuickCart and FoodDash are
   fictional brands.
4. **Time:** ISO 8601 with `+05:30`. Nothing later than `latest_allowed_timestamp` in `scenario.json`.
   A complaint is never earlier than the incident; agent actions happen in plausible working hours.
5. **Anita Deshpande** (`demo_customer`) reports her fraud live in the demo. Her only records are the
   ones listed in `demo_customer` (her 2026-09-20 app-chat query about the KYC SMS). Never write a fraud
   complaint, call or note from her.
6. Write only the files your task names. Do not touch other folders, `.env`, or install packages.
   Use `python` (Python 3.14, standard library only) for any helper or validation script.

## Formats (UTF-8 JSONL: one JSON object per line, `ensure_ascii=False`)

### Complaints — `unstructured/complaints_<part>.jsonl`
The CRM export of every customer contact: a few structured fields plus the free text as written.
```json
{"complaint_id": "CMP-2026-104233", "customer_id": "C000871", "channel": "app_chat",
 "created_at": "2026-09-18T14:22:05+05:30", "language": "hinglish",
 "category_selected": "UPI - payment issue", "subject": "paise kat gaye",
 "text": "free text exactly as the customer wrote it", "status": "IN_PROGRESS",
 "priority": "HIGH", "assigned_team": "Cyber Fraud Desk"}
```
- `channel`: `app_chat | email | phone_call | branch_visit | social_media_dm | cybercrime_portal_forward`.
  For `phone_call` / `branch_visit`, `text` is the agent's or branch officer's write-up of what the
  customer said (third person, typed quickly).
- `language`: the language `text` is written in — `en` (Indian English), `hinglish` (romanised
  Hindi-English mix), `hi` (Hindi, Devanagari), `mr` (Marathi, Devanagari, English words mixed in).
  Follow the customer's `writes_in`.
- `category_selected`: the dropdown category the customer picked — realistically often wrong or vague
  ("Others", "Card related", "UPI - payment issue", "Account related", "Net banking").
- `status` as of demo day: `OPEN | IN_PROGRESS | AWAITING_CUSTOMER | ESCALATED | RESOLVED | CLOSED`.
- `priority`: `LOW | MEDIUM | HIGH | CRITICAL`; `assigned_team`: e.g. `Cyber Fraud Desk`, `UPI Disputes`,
  `Card Services`, `ATM Reconciliation`, `Retail Banking`, `Senior Citizen Desk`, `Loans Servicing`.

### Call transcripts — `unstructured/call_transcripts_<part>.jsonl`
Speech-to-text style: fillers, repetitions, mis-heard words, numbers read digit by digit.
```json
{"call_id": "CALL-510232", "complaint_id": "CMP-2026-104233", "customer_id": "C000871",
 "started_at": "2026-09-18T15:02:11+05:30", "duration_sec": 412, "agent_id": "AGT-1043",
 "language": "hinglish",
 "turns": [{"speaker": "AGENT", "text": "..."}, {"speaker": "CUSTOMER", "text": "..."}]}
```

### Agent notes — `unstructured/agent_notes_<part>.jsonl`
Terse internal case notes in bank shorthand ("cx", "a/c", "txn", "benef", "hotlisted", "FRM",
"shadow cr", "TAT", "SR", "IVR", "NCRP ack").
```json
{"note_id": "NOTE-801122", "complaint_id": "CMP-2026-104233", "customer_id": "C000871",
 "author": "AGT-1043 (Pooja S.)", "created_at": "2026-09-18T15:10:40+05:30",
 "text": "Cx reports unauth UPI dr 25k to rkfashions...@konkanpay after AnyDesk install. Card hotlisted, dispute DSP-2026-10442 raised, benef lien req sent. Advised 1930 + NCRP. Shadow cr decision TAT 02-Oct."}
```
Notes record what was **done and promised** (dispute ids, lien requests, TAT dates, callbacks,
refunds, compensation) using `bank_policy_facts` — this is the memory the agent will rely on.

### Knowledge-base documents — `unstructured/kb/<doc_id>.md`
Markdown with YAML front matter:
```
---
doc_id: ADV-001
title: ...
doc_type: customer_advisory | internal_sop | policy | faq | fraud_alert
version: 1.2
published_on: 2026-08-14
audience: customers | staff
tags: [remote-access, kyc, upi]
---
```

## ID ranges (so parallel agents never collide)
| Part | complaint_id | call_id | note_id |
|---|---|---|---|
| `ring_a` | CMP-2026-100000 – 199999 | CALL-100000 – 199999 | NOTE-100000 – 199999 |
| `ring_b` | CMP-2026-200000 – 299999 | CALL-200000 – 299999 | NOTE-200000 – 299999 |
| `general_1` | CMP-2026-300000 – 399999 | CALL-300000 – 399999 | NOTE-300000 – 399999 |
| `general_2` | CMP-2026-400000 – 499999 | CALL-400000 – 499999 | NOTE-400000 – 499999 |

Use non-sequential numbers inside your range. Agent ids: `AGT-1001` … `AGT-1099` (invent first name +
initial, e.g. `AGT-1043 (Pooja S.)`). Dispute ids: `DSP-2026-#####`.

## Realism guide
- Real customers are stressed, vague, repetitive, sometimes rude, sometimes very polite; they paste
  forwarded SMS text, write in ALL CAPS, misspell, give partial details ("number was 55… something"),
  mix up dates ("yesterday", "on Tuesday"), and add irrelevant life details. Keep lengths varied
  (15 to 250 words).
- A fraud complaint mentions exactly what the customer would remember — see `recalls_in_complaint` in
  `scenario.json` (the exact caller number, UPI id or app) — plus amount(s) and rough time. Phone-call
  write-ups and later follow-ups may add details (UTR number, the caller's name, the exact SMS text).
- Follow-ups ("any update??", "still no refund", "3 din ho gaye") reference the earlier complaint and
  what the bank promised.
- Near-miss reports: the customer did NOT lose money but reports the call/SMS/message and its number.
- Staff notes and statuses must be consistent with timestamps and with `bank_policy_facts`.

## Before you finish
Write a small validation script in your scratch area (not in `data/`) or run inline Python that:
parses every line, checks required fields and id ranges, checks every `customer_id` exists in
`scenario.json` `special_customers`, checks no timestamp exceeds `latest_allowed_timestamp`, and
checks every phone number in your text starts with `+91 5` or is 1930 / the bank helpline. Fix issues,
then report: files written, record counts, and anything you could not satisfy.
