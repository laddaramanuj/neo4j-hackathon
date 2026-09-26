# Kavach — facts for the architecture diagram prototypes

Use ONLY these facts. Do not invent components, numbers or features.

## What it is
Kavach ("armour") — a bank customer-support agent that remembers fraud victims and uncovers scam rings.
Neo4j × hackFront India Agent Memory Build Sprint, Pune · Problem Statement 1: Context-Aware Customer Support Agent.
Sahyadri Bank and all data are fictional.

## The request flow (the judges want to see this chain)
User → Agent → Memory / Retrieval → Neo4j → Response
1. Customer types in the Streamlit chat (Memory ON/OFF switch in the sidebar).
2. Memory first: `recall_customer` loads from Neo4j the customer's profile, past complaints with staff notes, promises (refund due dates), preferences (reply language) and past Kavach interactions, and puts them into the agent's prompt.
3. The LangChain agent (`create_agent`, tool calling; LLM `openai/gpt-4.1-mini` via OpenRouter) decides which tools to call.
4. Tools query Neo4j (reads).
5. For a new fraud report, `open_fraud_case` writes the case in ONE transaction.
6. Kavach replies in the customer's language (Hindi / Marathi / English), using only retrieved facts.
7. `log_interaction` stores the turn and links it (USED) to every node the answer relied on.
8. The UI shows the reply, the customer's part of the graph (neo4j-viz), the "Why Kavach said this" tool trace, and the actions taken.

## The 7 tools (plain-English meaning)
- `check_recent_payments` — the customer's payments in the last 3 days + risk signals (remote-access app active, first payment to that beneficiary)
- `extract_scam_clues` — pulls caller numbers, UPI IDs, Telegram handles, SMS sender IDs and apps out of the message
- `find_linked_complaints_and_money_trail` — graph search: other customers' complaints with the same clues, other people who paid the same account, where the money went next (forwarding accounts → cash-out), and which accounts feed the same account
- `search_bank_advisories` — GraphRAG over the bank's advisories, procedures, policy and fraud alerts
- `open_fraud_case` — saves the complaint + clues, blocks (hotlists) the card, raises a dispute, requests a freeze (lien) on the receiving account, records the refund-decision promise (10 working days)
- `save_customer_preference` — e.g. reply language
- `log_interaction` (automatic) — memory of every turn with USED links (provenance for "why")

## Neo4j features used
Neo4j AuraDB 5.27 + APOC · Cypher multi-hop traversals · APOC `apoc.path.subgraphNodes` (money trail) ·
neo4j-graphrag `VectorCypherRetriever` (vector search + graph) · 3 vector indexes (1024-d Gemini embeddings) ·
1 fulltext index · 17 uniqueness constraints · single managed write transaction · neo4j-viz to draw the graph.
Graph size: 53,955 nodes · 94,800 relationships.

## One graph, three layers
- Bank data (structured, blue #4C8EDA): Customer, Account, Card, Device, LoginSession, Transaction, Merchant, Counterparty (receiving accounts), CashOutPoint
- Text → graph (unstructured, orange #F08A4B): Complaint, CallTranscript, AgentNote, KbDoc → KbChunk; plus Clue (magenta #D81B60: phone number, UPI ID, Telegram handle, SMS sender, app) which links text to accounts
- Agent memory (written by Kavach, gold #E5A100): Interaction, Promise, Preference
Key relationships: Customer-OWNS→Account-HAS_CARD→Card · Account-SENT→Transaction-TO→Counterparty ·
Transaction-IN_SESSION→LoginSession · Counterparty-TRANSFERRED_TO→Counterparty-CASHED_OUT→CashOutPoint ·
Customer-RAISED→Complaint · AgentNote-ON→Complaint · CallTranscript-ABOUT→Complaint ·
Complaint-MENTIONS→Clue · Clue-IDENTIFIES→Counterparty · Complaint-REPORTS→Transaction ·
Customer-HAS_PROMISE→Promise-FOR→Complaint · Customer-PREFERS→Preference · Customer-HAD_INTERACTION→Interaction-USED→(nodes) · KbDoc-HAS_CHUNK→KbChunk

## Data (synthetic but realistic, structured + unstructured)
2,000 customers · 2,302 accounts · 36,709 transactions · 544 counterparty accounts · 6,596 login sessions ·
164 complaints · 30 call transcripts · 237 staff notes (English, Hinglish, Hindi, Marathi) · 15 bank documents (70 chunks).
Pipeline: scenario answer key → 6 AI agents generated the data → CSV / JSONL / Markdown → `load_graph.py`
(constraints & indexes → batched MERGE → clue extraction → links → embeddings) → Neo4j.

## The demo story (Anita) — real values from the running app
Anita Deshpande, 61, Pune, prefers Hindi. Six days ago she asked the bank about a "KYC expired" SMS (stored as a past interaction).
Today she writes: "KYC team called, made me install AnyDesk, now ₹40,000 is gone."
- Kavach finds her 2 payments this morning (₹25,000 + ₹15,000) to `rkfashions7096@narmadapay`, made while AnyDesk was active.
- The graph shows that UPI ID in 3 other customers' complaints (AnyDesk in 7); the money was forwarded to 2 accounts and then cashed out (ATM / crypto).
- Two "task job" scam accounts also send money into the same account → two scams, one gang.
- Actions: card blocked, dispute raised, freeze on the receiving account requested, refund decision due 12 Oct 2026.
- Reply in Hindi. Later, in a NEW conversation, "Koi update?" is answered from memory — she never repeats anything.
- Memory OFF: the same LLM just says it has no access to her records.

## Guardrails
The LLM never writes Cypher (all writes are fixed, parameterised queries) · tools are bound to the customer on the server ·
retrieval is scoped to what is connected to this case · never asks for OTP/PIN · secrets never in git · synthetic data.

## Deployment
Streamlit Community Cloud (auto-deploys from GitHub) · OpenRouter (LLM + embeddings) · Neo4j Aura.

## Style
16:9 slide, 1920×1080 CSS px. Projector-friendly: white background, dark ink #14213D, Neo4j blue #018BFF,
layer colours above. Font "Segoe UI". Body text ≥ 20px, headings ≥ 28px. Few words; one idea per box.
Title: "Kavach — how it works" (or similar). Must include the chain User → Agent → Memory/Retrieval → Neo4j → Response.
