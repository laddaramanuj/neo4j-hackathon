# Kavach's agent. For each customer message it runs its memory and retrieval
# tools against Neo4j, takes the actions a fraud report needs, writes what it
# did back into the graph as memory, and asks the LLM for a reply grounded in
# exactly what it retrieved.
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from neo4j_graphrag.embeddings.base import Embedder
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from common import CHAT_MODEL, DATABASE, driver, embed, extract_clues, llm, run

IST = timezone(timedelta(hours=5, minutes=30))
HOLIDAYS = {date(2026, 10, 2)}
FRAUD_WORDS = re.compile(
    r"fraud|scam|cheat|hack|unauthori[sz]ed|stolen|not me|didn'?t do|kyc|otp|anydesk|screen ?shar|remote|"
    r"paise? kat|paisa gaya|money (is )?gone|debited|refund|task|telegram|electricity|bill update|"
    r"धोखा|ठगी|फसवणूक|पैसे कट|पैसे गेले", re.I)
LANGUAGE_WORDS = {"hi": re.compile(r"hindi|हिंदी", re.I), "mr": re.compile(r"marathi|मराठी", re.I),
                  "en": re.compile(r"\benglish\b", re.I)}
LANGUAGE_NAMES = {"hi": "simple Hindi (Devanagari script)", "mr": "simple Marathi (Devanagari script)",
                  "en": "simple Indian English", "hinglish": "Hinglish (romanised Hindi-English)"}


def now_ist():
    """Current time, or KAVACH_NOW when set - pins a deployed demo to demo day."""
    pinned = os.getenv("KAVACH_NOW")
    return datetime.fromisoformat(pinned) if pinned else datetime.now(IST)


class OpenRouterEmbedder(Embedder):
    """neo4j-graphrag embedder backed by the same OpenRouter embeddings."""

    def embed_query(self, text):
        return embed([text])[0]

    async def async_embed_query(self, text):
        return self.embed_query(text)


_advisory_retriever = None


def advisory_retriever():
    """Built on first use: the constructor checks the vector index exists."""
    global _advisory_retriever
    if _advisory_retriever is None:
        _advisory_retriever = VectorCypherRetriever(
            driver,
            index_name="kbchunk_embedding",
            embedder=OpenRouterEmbedder(),
            retrieval_query=("MATCH (d:KbDoc)-[:HAS_CHUNK]->(node) "
                             "RETURN d.doc_id AS doc_id, d.title AS title, node.text AS text, score "
                             "ORDER BY score DESC"),
            result_formatter=lambda record: RetrieverResultItem(
                content=record["text"],
                metadata={"doc_id": record["doc_id"], "title": record["title"], "score": record["score"]}),
            neo4j_database=DATABASE,
        )
    return _advisory_retriever


# --- Memory and retrieval tools -------------------------------------------

def recall_customer(cid):
    """Everything Kavach remembers about this customer, anchored at their node."""
    profile = run("""
        MATCH (c:Customer {customer_id: $cid})
        OPTIONAL MATCH (c)-[:OWNS]->(a:Account)
        OPTIONAL MATCH (a)-[:HAS_CARD]->(k:Card)
        OPTIONAL MATCH (c)-[:PREFERS]->(pf:Preference)
        RETURN c {.customer_id, .full_name, .age, .city, .segment, .preferred_language} AS customer,
               collect(DISTINCT a {.account_number, .account_type, .upi_id}) AS accounts,
               collect(DISTINCT k {.masked_pan, .card_type, .status}) AS cards,
               collect(DISTINCT pf {.kind, .value}) AS preferences""", cid=cid)
    history = run("""
        MATCH (:Customer {customer_id: $cid})-[:RAISED]->(p:Complaint)
        OPTIONAL MATCH (n:AgentNote)-[:ON]->(p)
        WITH p, n ORDER BY n.created_at
        WITH p, [x IN collect(n.text) WHERE x IS NOT NULL] AS notes
        RETURN p.complaint_id AS complaint_id, toString(p.created_at) AS at, p.channel AS channel,
               p.status AS status, p.subject AS subject, left(p.text, 500) AS text, notes[..4] AS staff_notes
        ORDER BY p.created_at DESC LIMIT 6""", cid=cid)
    promises = run("""
        MATCH (:Customer {customer_id: $cid})-[:HAS_PROMISE]->(pr:Promise)
        RETURN pr.what AS what, toString(pr.due_on) AS due_on, pr.status AS status, pr.dispute_id AS dispute_id
        ORDER BY pr.created_at DESC""", cid=cid)
    interactions = run("""
        MATCH (:Customer {customer_id: $cid})-[:HAD_INTERACTION]->(i:Interaction)
        RETURN toString(i.at) AS at, i.user_message AS customer_said, i.summary AS kavach_did
        ORDER BY i.at DESC LIMIT 4""", cid=cid)
    base = profile[0] if profile else {"customer": None, "accounts": [], "cards": [], "preferences": []}
    return {**base, "complaint_history": history, "promises": promises, "recent_kavach_interactions": interactions}


def recent_debits(cid, days=3):
    """Outgoing payments in the last few days, with the login-session signals."""
    return run("""
        MATCH (:Customer {customer_id: $cid})-[:OWNS]->(a:Account)-[:SENT]->(t:Transaction)-[:TO]->(x:Counterparty)
        WHERE datetime($now) - duration({days: $days}) <= t.ts <= datetime($now)
        OPTIONAL MATCH (t)-[:IN_SESSION]->(s:LoginSession)
        RETURN t.txn_id AS txn_id, t.utr AS utr, toString(t.ts) AS ts, t.amount_inr AS amount_inr,
               x.ext_id AS ext_id, x.holder_name AS to_name, x.upi_id AS to_upi, x.bank AS to_bank,
               s.remote_access_app_detected AS remote_access_app, s.new_device AS new_device,
               COUNT { (a)-[:SENT]->(:Transaction)-[:TO]->(x) } AS payments_to_this_beneficiary
        ORDER BY t.ts DESC LIMIT 10""", cid=cid, days=days, now=now_ist().isoformat())


def find_ring(cid, clue_values, ext_ids):
    """Graph thinking: who else mentioned the same clues, who else paid the same
    accounts, and where the money went next."""
    shared = run("""
        UNWIND $values AS v
        MATCH (k:Clue {value: v})<-[:MENTIONS]-(src)
        OPTIONAL MATCH (src)-[:ON|ABOUT]->(p:Complaint)
        WITH k, coalesce(p, src) AS s
        MATCH (o:Customer)-[:RAISED|HAD_CALL]->(s)
        WHERE o.customer_id <> $cid
        RETURN k.kind AS kind, k.value AS value, count(DISTINCT o) AS other_customers,
               collect(DISTINCT o.full_name)[..6] AS names,
               collect(DISTINCT s.complaint_id)[..6] AS complaint_ids
        ORDER BY other_customers DESC""", cid=cid, values=clue_values)
    payers = run("""
        UNWIND $ext_ids AS e
        MATCH (x:Counterparty {ext_id: e})<-[:TO]-(t:Transaction)<-[:SENT]-(:Account)<-[:OWNS]-(o:Customer)
        WHERE o.customer_id <> $cid
        RETURN x.upi_id AS beneficiary, count(DISTINCT o) AS other_payers, sum(t.amount_inr) AS paid_by_others_inr,
               collect(DISTINCT o.full_name)[..6] AS names""", cid=cid, ext_ids=ext_ids)
    try:  # APOC path expansion follows the money downstream
        trail = run("""
            UNWIND $ext_ids AS e
            MATCH (x:Counterparty {ext_id: e})
            CALL apoc.path.subgraphNodes(x, {relationshipFilter: 'TRANSFERRED_TO>', maxLevel: 3}) YIELD node
            WITH x, collect(DISTINCT node) AS chain
            UNWIND chain AS n
            OPTIONAL MATCH (n)-[co:CASHED_OUT]->(p:CashOutPoint)
            RETURN x.upi_id AS start,
                   [m IN chain WHERE m <> x | m.holder_name + ' (' + m.upi_id + ', ' + m.bank + ')'] AS forwarded_to,
                   collect(DISTINCT p.exit_type + ' in ' + p.city) AS cash_out, sum(co.amount_inr) AS cashed_out_inr""",
                    ext_ids=ext_ids)
    except Exception:
        trail = run("""
            UNWIND $ext_ids AS e
            MATCH (x:Counterparty {ext_id: e})
            OPTIONAL MATCH (x)-[:TRANSFERRED_TO*1..3]->(y:Counterparty)
            OPTIONAL MATCH (y)-[co:CASHED_OUT]->(p:CashOutPoint)
            RETURN x.upi_id AS start, collect(DISTINCT y.holder_name + ' (' + y.upi_id + ')') AS forwarded_to,
                   collect(DISTINCT p.exit_type + ' in ' + p.city) AS cash_out, sum(co.amount_inr) AS cashed_out_inr""",
                    ext_ids=ext_ids)
    upstream = run("""
        UNWIND $ext_ids AS e
        MATCH (w:Counterparty)-[:TRANSFERRED_TO*1..2]->(x:Counterparty {ext_id: e})
        OPTIONAL MATCH (k:Clue)-[:IDENTIFIES]->(w)
        OPTIONAL MATCH (k)<-[:MENTIONS]-(:Complaint)<-[:RAISED]-(o:Customer)
        RETURN x.upi_id AS receiving_account, w.holder_name AS feeder, w.upi_id AS feeder_upi,
               count(DISTINCT o) AS complaints_about_feeder""", ext_ids=ext_ids)
    return {"shared_clues": shared, "other_customers_paying_same_accounts": payers,
            "money_trail": trail, "accounts_feeding_the_same_account": upstream}


def search_advisories(query, k=3):
    """GraphRAG over the bank's knowledge base (vector search + graph)."""
    result = advisory_retriever().search(query_text=query, top_k=k)
    return [{"doc_id": i.metadata["doc_id"], "title": i.metadata["title"], "excerpt": i.content[:600]}
            for i in result.items]


# --- Actions: memory the agent writes back ---------------------------------

def add_working_days(start, n):
    d = start
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in HOLIDAYS:
            n -= 1
    return d


CLUE_LABELS = [("phone", "Phone"), ("upi", "UpiId"), ("handle", "TelegramHandle"),
               ("sms_sender", "SmsSender"), ("app", "App")]


def open_fraud_case_db(cid, message, language, clues, debits):
    """Write a new fraud case in ONE transaction: complaint and its clues, the
    reported payments, clue-to-account links, card hotlisting and the promise."""
    complaint_id = f"CMP-2026-K{uuid.uuid4().hex[:8].upper()}"
    dispute_id = f"DSP-2026-K{uuid.uuid4().hex[:6].upper()}"
    promise_id = f"PRM-{uuid.uuid4().hex[:12]}"
    due = add_working_days(now_ist().date(), 10).isoformat()
    amount = sum(d["amount_inr"] or 0 for d in debits)
    what = (f"Shadow-credit / refund decision on disputed amount Rs {amount:,.0f}" if amount
            else "Decision on the reported fraud")
    set_labels = " ".join(f"FOREACH (_ IN CASE WHEN k.kind = '{kind}' THEN [1] ELSE [] END | SET k:{label})"
                          for kind, label in CLUE_LABELS)

    def work(tx):
        tx.run("""
            MATCH (c:Customer {customer_id: $cid})
            CREATE (p:Complaint {complaint_id: $complaint_id, channel: 'kavach_chat', created_at: datetime(),
                    language: $language, category_selected: 'Fraud - unauthorised transaction',
                    subject: 'Fraud reported to Kavach', text: $message, status: 'ESCALATED', priority: 'CRITICAL',
                    assigned_team: 'Cyber Fraud Desk', customer_id: $cid, source: 'kavach'})
            MERGE (c)-[:RAISED]->(p)
            WITH p
            UNWIND $clues AS cl
            MERGE (k:Clue {key: cl.kind + ':' + cl.value}) ON CREATE SET k.kind = cl.kind, k.value = cl.value
            MERGE (p)-[:MENTIONS]->(k)""",
               cid=cid, complaint_id=complaint_id, language=language, message=message, clues=clues)
        tx.run(f"MATCH (:Complaint {{complaint_id: $complaint_id}})-[:MENTIONS]->(k:Clue) {set_labels}",
               complaint_id=complaint_id)
        tx.run("""
            MATCH (p:Complaint {complaint_id: $complaint_id})
            UNWIND $txn_ids AS tid MATCH (t:Transaction {txn_id: tid}) MERGE (p)-[:REPORTS]->(t)""",
               complaint_id=complaint_id, txn_ids=[d["txn_id"] for d in debits])
        tx.run("""
            MATCH (:Complaint {complaint_id: $complaint_id})-[:MENTIONS]->(k:Clue {kind: 'upi'})
            OPTIONAL MATCH (x:Counterparty {upi_id: k.value})
            OPTIONAL MATCH (a:Account {upi_id: k.value})
            FOREACH (_ IN CASE WHEN x IS NULL THEN [] ELSE [1] END | MERGE (k)-[:IDENTIFIES]->(x))
            FOREACH (_ IN CASE WHEN a IS NULL THEN [] ELSE [1] END | MERGE (k)-[:IDENTIFIES]->(a))""",
               complaint_id=complaint_id)
        hot = tx.run("""
            MATCH (:Customer {customer_id: $cid})-[:OWNS]->(:Account)-[:HAS_CARD]->(k:Card)
            WHERE k.status = 'ACTIVE'
            SET k.status = 'HOTLISTED', k.hotlisted_by = 'kavach', k.hotlisted_at = datetime()
            RETURN k.masked_pan AS card""", cid=cid).data()
        tx.run("""
            MATCH (c:Customer {customer_id: $cid}), (p:Complaint {complaint_id: $complaint_id})
            CREATE (pr:Promise {promise_id: $promise_id, what: $what, due_on: date($due), status: 'OPEN',
                    dispute_id: $dispute_id, created_at: datetime(), source: 'kavach'})
            MERGE (c)-[:HAS_PROMISE]->(pr) MERGE (pr)-[:FOR]->(p)""",
               cid=cid, complaint_id=complaint_id, promise_id=promise_id, due=due, dispute_id=dispute_id, what=what)
        return hot

    with driver.session(database=DATABASE) as session:
        hotlisted = session.execute_write(work)
    return {"complaint_id": complaint_id, "dispute_id": dispute_id, "refund_decision_due": due,
            "cards_hotlisted": [h["card"] for h in hotlisted], "beneficiary_lien_requested_for":
            sorted({d["to_upi"] for d in debits}), "status": "ESCALATED to Cyber Fraud Desk"}


def save_preference(cid, kind, value):
    run("""
        MATCH (c:Customer {customer_id: $cid})
        MERGE (c)-[:PREFERS]->(p:Preference {kind: $kind, customer_id: $cid})
        SET p.value = $value, p.updated_at = datetime(), p.source = 'kavach'""", cid=cid, kind=kind, value=value)
    if kind == "reply_language":
        run("MATCH (c:Customer {customer_id: $cid}) SET c.preferred_language = $value", cid=cid, value=value)


def log_interaction(cid, message, reply, summary, used):
    run("""
        MATCH (c:Customer {customer_id: $cid})
        CREATE (i:Interaction {interaction_id: $iid, at: datetime(), user_message: $message, reply: $reply,
                summary: $summary, source: 'kavach'})
        MERGE (c)-[:HAD_INTERACTION]->(i)
        WITH i
        CALL (i) { UNWIND $complaints AS x MATCH (n:Complaint {complaint_id: x}) MERGE (i)-[:USED]->(n) }
        CALL (i) { UNWIND $clues AS x MATCH (n:Clue {value: x}) MERGE (i)-[:USED]->(n) }
        CALL (i) { UNWIND $docs AS x MATCH (n:KbDoc {doc_id: x}) MERGE (i)-[:USED]->(n) }
        CALL (i) { UNWIND $txns AS x MATCH (n:Transaction {txn_id: x}) MERGE (i)-[:USED]->(n) }""",
        cid=cid, iid=f"INT-{uuid.uuid4().hex[:12]}", message=message, reply=reply, summary=summary,
        complaints=used["complaints"], clues=used["clues"], docs=used["docs"], txns=used["txns"])


# --- One turn ---------------------------------------------------------------

SYSTEM = """You are Kavach, the customer-support agent of Sahyadri Bank (fictional). You help customers who
report fraud or ask about their cases. Use ONLY the facts in CONTEXT: never invent ids, dates or amounts.
- Reply in {language}. Keep amounts, ids and dates in digits. Be warm, calm and brief (under 170 words).
- If this is a fraud report: say what you already see (their payments, the app, the caller), what you have done
  (actions_taken: card blocked, dispute id, lien request, refund decision date), and what they should do now
  (never share OTP/PIN, uninstall the screen-sharing app, call 1930 / cybercrime.gov.in).
- If graph_findings show other customers reported the same caller number, UPI id or handle, or paid the same
  account, say so in one sentence naming the exact clue type that matched (e.g. "the UPI id you paid was reported
  by 3 other customers") - numbers only, no other customers' names. A lien is REQUESTED, not yet confirmed.
- If this is a follow-up, answer from complaint_history, promises and recent_kavach_interactions without asking
  them to repeat anything.
- Never blame the customer. Do not ask for OTP, PIN, card number or password."""

NO_MEMORY = """You are a bank's customer-support chatbot. You have no access to customer records, history or
bank systems. Reply briefly in English."""


def handle_turn(cid, message, memory_on=True):
    """Run one customer message through Kavach. Returns the reply plus a trace
    of every tool call, so the UI can show why it answered."""
    if not memory_on:
        reply = chat(NO_MEMORY, f"Customer message: {message}")
        return {"reply": reply, "trace": [{"tool": "none", "note": "memory OFF - no Neo4j lookups"}], "actions": None}
    try:
        return handle_turn_langchain(cid, message)
    except Exception as error:  # keep the demo alive: fall back to the fixed pipeline
        result = handle_turn_pipeline(cid, message)
        result["trace"].insert(0, {"tool": "fallback", "note": f"LangChain agent failed ({error}); used pipeline"})
        return result


# --- LangChain agent ------------------------------------------------------------

lc_model = ChatOpenAI(model=CHAT_MODEL, temperature=0.2, api_key=os.environ["OPENROUTER_API_KEY"],
                      base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))

AGENT_SYSTEM = """You are Kavach, the customer-support agent of Sahyadri Bank (fictional), talking to the customer
below. MEMORY is what Neo4j remembers about them, loaded for this turn. Use tools for everything else; never guess.

How to work:
- NEW fraud or scam report (money lost, unknown debit, scam call/SMS/app): call check_recent_payments and
  extract_scam_clues, then find_linked_complaints_and_money_trail, then search_bank_advisories, then
  open_fraud_case exactly once. Then reply.
- Follow-up on an existing case: answer from MEMORY (complaint_history, promises, recent_kavach_interactions)
  without asking them to repeat anything; call find_linked_complaints_and_money_trail only if they ask about
  the investigation.
- Other banking questions: answer from MEMORY and search_bank_advisories.
- If they state a preference (reply language, contact time), call save_customer_preference.

Reply rules: reply in {language}; keep amounts, ids and dates in digits; warm, calm, under 170 words. Say what
you found (their payments, the clue that matched), what you did (card blocked, dispute id, lien REQUESTED,
refund decision date) and what they should do now (never share OTP/PIN, uninstall screen-sharing apps, call 1930
or cybercrime.gov.in). If other customers reported the same caller number, UPI id or handle, or paid the same
account, say so in one sentence naming the clue type - numbers only, never other customers' names. Never blame
the customer; never ask for OTP, PIN, card number or password.

MEMORY:
{memory}"""


def build_tools(cid, message, state):
    """Neo4j tools for one turn, bound to the customer being served."""

    def suspicious_payments():
        if "suspicious" not in state:
            debits = recent_debits(cid)
            state["suspicious"] = [d for d in debits if d["remote_access_app"] or d["payments_to_this_beneficiary"] <= 1]
        return state["suspicious"]

    @tool
    def check_recent_payments() -> str:
        """List the customer's outgoing payments in the last 3 days with fraud signals from the bank's records
        (remote-access app active in the session, first payment to that beneficiary)."""
        return json.dumps(suspicious_payments(), default=str)

    @tool
    def extract_scam_clues(text: str) -> str:
        """Extract caller phone numbers, UPI ids, Telegram handles, SMS sender ids and apps from a text."""
        clues = [{"kind": k, "value": v} for k, v in extract_clues(text)]
        state.setdefault("clues", [])
        state["clues"] += [c for c in clues if c not in state["clues"]]
        return json.dumps(clues)

    @tool
    def find_linked_complaints_and_money_trail(clue_values: list[str]) -> str:
        """Graph search in Neo4j: other customers' complaints that mention the same clues (phone numbers, UPI
        ids, handles, apps), other customers who paid the same receiving accounts, where the money went next
        (forwarding accounts and cash-out) and which accounts feed the same account. Pass clue values; the
        receiving UPI ids of the customer's suspicious payments are added automatically."""
        pays = suspicious_payments()
        values = sorted(set(clue_values) | {p["to_upi"] for p in pays if p["to_upi"]}
                        | {c["value"] for c in state.get("clues", [])})
        ring = find_ring(cid, values, sorted({p["ext_id"] for p in pays}))
        state["ring"], state["ring_values"] = ring, values
        return json.dumps(ring, ensure_ascii=False, default=str)[:7000]

    @tool
    def search_bank_advisories(query: str) -> str:
        """Search the bank's knowledge base (customer advisories, SOPs, liability policy, fraud alerts) with
        GraphRAG vector search, for correct advice and timelines."""
        hits = search_advisories(query)
        state["advisories"] = hits
        return json.dumps(hits, ensure_ascii=False)

    @tool
    def open_fraud_case() -> str:
        """For a NEW fraud report only: store the complaint and its clues in Neo4j, hotlist the customer's active
        cards, raise a dispute, request a lien on the receiving account and record the refund-decision promise.
        Call once per report, never for follow-ups."""
        if state.get("actions"):
            return json.dumps(state["actions"])
        pays = suspicious_payments()
        clues = state.get("clues") or [{"kind": k, "value": v} for k, v in extract_clues(message)]
        clues = clues + [{"kind": "upi", "value": p["to_upi"]} for p in pays
                         if p["to_upi"] and p["to_upi"] not in {c["value"] for c in clues}]
        language = (state["memory"].get("customer") or {}).get("preferred_language", "en")
        state["actions"] = open_fraud_case_db(cid, message, language, clues, pays)
        return json.dumps(state["actions"])

    @tool
    def save_customer_preference(kind: str, value: str) -> str:
        """Save a customer preference, e.g. kind='reply_language' value='hi'|'mr'|'en'|'hinglish', or
        kind='contact_time' value='after 6 pm'."""
        save_preference(cid, kind, value)
        return f"saved {kind}={value}"

    return [check_recent_payments, extract_scam_clues, find_linked_complaints_and_money_trail,
            search_bank_advisories, open_fraud_case, save_customer_preference]


def handle_turn_langchain(cid, message):
    for lang, pattern in LANGUAGE_WORDS.items():
        if pattern.search(message):
            save_preference(cid, "reply_language", lang)
    memory = recall_customer(cid)
    state = {"memory": memory}
    language = LANGUAGE_NAMES.get((memory.get("customer") or {}).get("preferred_language"), "simple Indian English")
    system = AGENT_SYSTEM.format(language=language, memory=json.dumps(
        {"today": now_ist().strftime("%Y-%m-%d %H:%M IST"), **memory}, ensure_ascii=False, default=str)[:9000])
    agent = create_agent(lc_model, tools=build_tools(cid, message, state), system_prompt=system)
    out = agent.invoke({"messages": [{"role": "user", "content": message}]}, config={"recursion_limit": 14})

    trace = [{"tool": "recall_customer (memory loaded into the prompt)", "result": memory}]
    calls = {}
    for m in out["messages"]:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                calls[tc["id"]] = {"tool": tc["name"], "args": tc["args"]}
        elif isinstance(m, ToolMessage):
            entry = calls.get(m.tool_call_id, {"tool": m.name})
            try:
                entry["result"] = json.loads(m.content)
            except (TypeError, ValueError):
                entry["result"] = m.content
            trace.append(entry)
    reply = out["messages"][-1].content

    actions = state.get("actions")
    ring = state.get("ring") or {}
    used = {"complaints": [h["complaint_id"] for h in memory["complaint_history"]]
            + [c for s in ring.get("shared_clues", []) for c in s["complaint_ids"] if c],
            "clues": state.get("ring_values", []), "docs": [a["doc_id"] for a in state.get("advisories", [])],
            "txns": [p["txn_id"] for p in state.get("suspicious", [])]}
    summary = (f"Opened {actions['complaint_id']}, dispute {actions['dispute_id']}, refund decision due "
               f"{actions['refund_decision_due']}" if actions else "Answered using stored memory")
    log_interaction(cid, message, reply, summary, used)
    return {"reply": reply, "trace": trace, "actions": actions}


def handle_turn_pipeline(cid, message):
    """Fixed-order fallback: the same tools, called deterministically."""
    trace = []
    memory = recall_customer(cid)
    trace.append({"tool": "recall_customer", "result": memory})

    for lang, pattern in LANGUAGE_WORDS.items():
        if pattern.search(message):
            save_preference(cid, "reply_language", lang)
            memory["customer"]["preferred_language"] = lang
            trace.append({"tool": "save_preference", "result": {"reply_language": lang}})

    clues = [{"kind": k, "value": v} for k, v in extract_clues(message)]
    trace.append({"tool": "extract_clues", "result": clues})

    debits = recent_debits(cid)
    suspicious = [d for d in debits if d["remote_access_app"] or d["payments_to_this_beneficiary"] <= 1]
    trace.append({"tool": "recent_debits", "result": debits})

    open_case = any(h["status"] in ("ESCALATED", "OPEN", "IN_PROGRESS") and h["channel"] == "kavach_chat"
                    for h in memory["complaint_history"])
    is_fraud = bool(FRAUD_WORDS.search(message) or [c for c in clues if c["kind"] != "app"])
    new_report = is_fraud and not open_case

    upi_values = [d["to_upi"] for d in suspicious if d["to_upi"]]
    clue_values = sorted({c["value"] for c in clues} | set(upi_values))
    ring = find_ring(cid, clue_values, sorted({d["ext_id"] for d in suspicious})) if (clue_values or suspicious) else {}
    if not ring and open_case:
        reported = run("""
            MATCH (:Customer {customer_id: $cid})-[:RAISED]->(p:Complaint {source: 'kavach'})-[:MENTIONS]->(k:Clue)
            RETURN collect(DISTINCT k.value) AS values""", cid=cid)[0]["values"]
        ring = find_ring(cid, reported, []) if reported else {}
    if ring:
        trace.append({"tool": "find_ring", "result": ring})

    advisories = search_advisories(message) if is_fraud else []
    if advisories:
        trace.append({"tool": "search_advisories", "result": advisories})

    actions = None
    if new_report:
        all_clues = clues + [{"kind": "upi", "value": u} for u in upi_values if u not in {c["value"] for c in clues}]
        actions = open_fraud_case_db(cid, message, memory["customer"]["preferred_language"], all_clues, suspicious)
        trace.append({"tool": "open_fraud_case", "result": actions})
        memory = recall_customer(cid)

    language = LANGUAGE_NAMES.get((memory["customer"] or {}).get("preferred_language"), "simple Indian English")
    context = {"today": now_ist().strftime("%Y-%m-%d %H:%M IST"), "memory": memory,
               "suspicious_recent_payments": suspicious, "graph_findings": ring,
               "bank_advisories": advisories, "actions_taken": actions}
    reply = chat(SYSTEM.format(language=language),
                 f"CONTEXT:\n{json.dumps(context, ensure_ascii=False, default=str)[:14000]}\n\nCUSTOMER: {message}")

    used = {"complaints": [h["complaint_id"] for h in memory["complaint_history"]]
            + [cid_ for s in ring.get("shared_clues", []) for cid_ in s["complaint_ids"] if cid_],
            "clues": clue_values, "docs": [a["doc_id"] for a in advisories],
            "txns": [d["txn_id"] for d in suspicious]}
    summary = (f"Opened {actions['complaint_id']}, dispute {actions['dispute_id']}, refund decision due "
               f"{actions['refund_decision_due']}" if actions else "Answered using stored history")
    log_interaction(cid, message, reply, summary, used)
    return {"reply": reply, "trace": trace, "actions": actions}


def chat(system, user):
    resp = llm.chat.completions.create(model=CHAT_MODEL, temperature=0.2,
                                       messages=[{"role": "system", "content": system},
                                                 {"role": "user", "content": user}])
    return resp.choices[0].message.content


# --- Demo helpers ---------------------------------------------------------------

def demo_customers():
    return run("""
        MATCH (c:Customer) WHERE c.customer_id IN $ids
        RETURN c.customer_id AS id, c.full_name AS name, c.city AS city ORDER BY c.full_name""",
               ids=["C000150"] + [r["id"] for r in run("""
                   MATCH (c:Customer)-[:RAISED]->(:Complaint) RETURN DISTINCT c.customer_id AS id LIMIT 6""")])


def reset_customer(cid):
    """Remove everything Kavach wrote for this customer, so the demo can re-run."""
    run("""
        MATCH (c:Customer {customer_id: $cid})
        OPTIONAL MATCH (c)-[:RAISED|HAS_PROMISE|HAD_INTERACTION|PREFERS]->(n) WHERE n.source = 'kavach'
        DETACH DELETE n""", cid=cid)
    run("""
        MATCH (:Customer {customer_id: $cid})-[:OWNS]->(:Account)-[:HAS_CARD]->(k:Card)
        WHERE k.hotlisted_by = 'kavach'
        SET k.status = 'ACTIVE' REMOVE k.hotlisted_by, k.hotlisted_at""", cid=cid)
