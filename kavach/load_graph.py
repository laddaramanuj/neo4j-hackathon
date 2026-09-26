# Loads Kavach's data into Neo4j: the structured bank export, then complaints,
# call transcripts, agent notes and the knowledge base, with clues pulled out of
# the text and embeddings for vector search. Safe to re-run: everything MERGEs,
# and only nodes without an embedding get embedded.
import csv
import json
import time

from common import DATA, DATABASE, EMBED_DIM, driver, embed, extract_clues, extract_utrs, run

STRUCTURED = DATA / "structured"
UNSTRUCTURED = DATA / "unstructured"
TRUE = "['true', '1', 'yes', 'y']"


def read_csv(name):
    path = STRUCTURED / name
    if not path.exists():
        print(f"  - {name}: not found, skipped")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_jsonl(pattern):
    rows = []
    for path in sorted(UNSTRUCTURED.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            rows += [json.loads(line) for line in f if line.strip()]
    return rows


def batched(query, rows, size=1000):
    for i in range(0, len(rows), size):
        driver.execute_query(query, rows=rows[i:i + size], database_=DATABASE)


def setup_schema():
    for label, prop in [("Customer", "customer_id"), ("Account", "account_number"), ("Card", "card_id"),
                        ("Device", "device_id"), ("LoginSession", "session_id"), ("Merchant", "merchant_id"),
                        ("Counterparty", "ext_id"), ("Transaction", "txn_id"), ("Complaint", "complaint_id"),
                        ("CallTranscript", "call_id"), ("AgentNote", "note_id"), ("KbDoc", "doc_id"),
                        ("KbChunk", "chunk_id"), ("Clue", "key"), ("CashOutPoint", "key"),
                        ("Interaction", "interaction_id"), ("Promise", "promise_id")]:
        run(f"CREATE CONSTRAINT {label.lower()}_{prop} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE")
    for label, prop in [("Counterparty", "upi_id"), ("Account", "upi_id"), ("Transaction", "utr"),
                        ("Customer", "phone"), ("Clue", "kind"), ("Clue", "value"), ("Transaction", "ts")]:
        run(f"CREATE INDEX {label.lower()}_{prop} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})")
    for name, label in [("complaint_embedding", "Complaint"), ("call_embedding", "CallTranscript"),
                        ("kbchunk_embedding", "KbChunk")]:
        run(f"CREATE VECTOR INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.embedding) "
            f"OPTIONS {{indexConfig: {{`vector.dimensions`: {EMBED_DIM}, `vector.similarity_function`: 'cosine'}}}}")
    run("CREATE FULLTEXT INDEX complaint_text IF NOT EXISTS FOR (n:Complaint|AgentNote|CallTranscript) ON EACH [n.text]")


def load_structured():
    rows = read_csv("customers.csv")
    batched("""UNWIND $rows AS r MERGE (c:Customer {customer_id: r.customer_id})
               SET c += apoc.map.clean(r, [], ['']), c.age = toInteger(r.age)""", rows)
    print(f"  customers: {len(rows)}")

    rows = read_csv("accounts.csv")
    batched("""UNWIND $rows AS r MERGE (a:Account {account_number: r.account_number})
               SET a += apoc.map.clean(r, [], ['']), a.current_balance_inr = toFloat(r.current_balance_inr),
                   a.daily_upi_limit_inr = toFloat(r.daily_upi_limit_inr)
               WITH a, r MATCH (c:Customer {customer_id: r.customer_id}) MERGE (c)-[:OWNS]->(a)""", rows)
    print(f"  accounts: {len(rows)}")

    rows = read_csv("cards.csv")
    batched("""UNWIND $rows AS r MERGE (k:Card {card_id: r.card_id}) SET k += apoc.map.clean(r, [], [''])
               WITH k, r MATCH (a:Account {account_number: r.account_number}) MERGE (a)-[:HAS_CARD]->(k)""", rows)
    print(f"  cards: {len(rows)}")

    rows = read_csv("devices.csv")
    batched("""UNWIND $rows AS r MERGE (d:Device {device_id: r.device_id}) SET d += apoc.map.clean(r, [], [''])
               WITH d, r MATCH (c:Customer {customer_id: r.customer_id}) MERGE (c)-[:USES_DEVICE]->(d)""", rows)
    print(f"  devices: {len(rows)}")

    rows = read_csv("merchants.csv")
    batched("UNWIND $rows AS r MERGE (m:Merchant {merchant_id: r.merchant_id}) SET m += apoc.map.clean(r, [], [''])", rows)
    print(f"  merchants: {len(rows)}")

    rows = read_csv("counterparties.csv")
    batched("UNWIND $rows AS r MERGE (x:Counterparty {ext_id: r.ext_id}) SET x += apoc.map.clean(r, [], [''])", rows)
    print(f"  counterparties: {len(rows)}")

    rows = read_csv("login_sessions.csv")
    batched(f"""UNWIND $rows AS r MERGE (s:LoginSession {{session_id: r.session_id}})
                SET s += apoc.map.clean(r, [], ['']), s.started_at = datetime(r.started_at),
                    s.new_device = toLower(coalesce(r.new_device, '')) IN {TRUE},
                    s.screen_share_detected = toLower(coalesce(r.screen_share_detected, '')) IN {TRUE}
                WITH s, r MATCH (c:Customer {{customer_id: r.customer_id}}) MERGE (c)-[:LOGGED_IN]->(s)
                WITH s, r MATCH (d:Device {{device_id: r.device_id}}) MERGE (s)-[:ON_DEVICE]->(d)""", rows)
    print(f"  login sessions: {len(rows)}")

    rows = read_csv("transactions.csv")
    batched("""UNWIND $rows AS r MERGE (t:Transaction {txn_id: r.txn_id})
               SET t += apoc.map.clean(r, [], ['']), t.ts = datetime(r.ts), t.amount_inr = toFloat(r.amount_inr),
                   t.balance_after_inr = toFloat(r.balance_after_inr)
               WITH t, r MATCH (a:Account {account_number: r.account_number})
               FOREACH (_ IN CASE WHEN r.direction = 'DEBIT' THEN [1] ELSE [] END | MERGE (a)-[:SENT]->(t))
               FOREACH (_ IN CASE WHEN r.direction <> 'DEBIT' THEN [1] ELSE [] END | MERGE (t)-[:CREDITED_TO]->(a))
               WITH t, r
               OPTIONAL MATCH (x:Counterparty {ext_id: r.counterparty_id})
               OPTIONAL MATCH (m:Merchant {merchant_id: r.counterparty_id})
               WITH t, r, coalesce(x, m) AS other
               FOREACH (_ IN CASE WHEN other IS NOT NULL AND r.direction = 'DEBIT' THEN [1] ELSE [] END |
                   MERGE (t)-[:TO]->(other))
               FOREACH (_ IN CASE WHEN other IS NOT NULL AND r.direction <> 'DEBIT' THEN [1] ELSE [] END |
                   MERGE (other)-[:PAID]->(t))
               WITH t, r OPTIONAL MATCH (s:LoginSession {session_id: r.session_id})
               FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END | MERGE (t)-[:IN_SESSION]->(s))""",
            rows, size=2000)
    print(f"  transactions: {len(rows)}")

    rows = read_csv("fraud_intel_feed.csv")
    batched("""UNWIND $rows AS r MATCH (a:Counterparty {ext_id: r.from_ext_id})
               OPTIONAL MATCH (b:Counterparty {ext_id: r.to_ext_id})
               FOREACH (_ IN CASE WHEN b IS NOT NULL THEN [1] ELSE [] END |
                   MERGE (a)-[x:TRANSFERRED_TO {intel_id: r.intel_id}]->(b)
                   SET x.amount_inr = toFloat(r.amount_inr), x.txn_ts = datetime(r.txn_ts), x.source = r.source,
                       x.reported_at = datetime(r.reported_at))
               FOREACH (_ IN CASE WHEN coalesce(r.exit_type, '') <> '' THEN [1] ELSE [] END |
                   MERGE (p:CashOutPoint {key: r.exit_type + '|' + coalesce(r.exit_city, '')})
                   SET p.exit_type = r.exit_type, p.city = r.exit_city
                   MERGE (a)-[x:CASHED_OUT {intel_id: r.intel_id}]->(p)
                   SET x.amount_inr = toFloat(r.amount_inr), x.txn_ts = datetime(r.txn_ts), x.source = r.source)""",
            rows)
    print(f"  fraud-intel rows: {len(rows)}")


def load_text():
    complaints = read_jsonl("complaints_*.jsonl")
    batched("""UNWIND $rows AS r MERGE (c:Complaint {complaint_id: r.complaint_id})
               SET c.channel = r.channel, c.created_at = datetime(r.created_at), c.language = r.language,
                   c.category_selected = r.category_selected, c.subject = r.subject, c.text = r.text,
                   c.status = r.status, c.priority = r.priority, c.assigned_team = r.assigned_team,
                   c.customer_id = r.customer_id
               WITH c, r MERGE (cu:Customer {customer_id: r.customer_id}) MERGE (cu)-[:RAISED]->(c)""", complaints)
    print(f"  complaints: {len(complaints)}")

    calls = read_jsonl("call_transcripts_*.jsonl")
    for c in calls:
        c["text"] = "\n".join(f"{t.get('speaker', '')}: {t.get('text', '')}" for t in c.get("turns", []))
    batched("""UNWIND $rows AS r MERGE (k:CallTranscript {call_id: r.call_id})
               SET k.started_at = datetime(r.started_at), k.duration_sec = toInteger(r.duration_sec),
                   k.agent_id = r.agent_id, k.language = r.language, k.text = r.text, k.customer_id = r.customer_id
               WITH k, r MERGE (cu:Customer {customer_id: r.customer_id}) MERGE (cu)-[:HAD_CALL]->(k)
               WITH k, r OPTIONAL MATCH (c:Complaint {complaint_id: r.complaint_id})
               FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END | MERGE (k)-[:ABOUT]->(c))""",
            [{k: v for k, v in c.items() if k != "turns"} for c in calls])
    print(f"  call transcripts: {len(calls)}")

    notes = read_jsonl("agent_notes_*.jsonl")
    batched("""UNWIND $rows AS r MERGE (n:AgentNote {note_id: r.note_id})
               SET n.author = r.author, n.created_at = datetime(r.created_at), n.text = r.text,
                   n.customer_id = r.customer_id
               WITH n, r OPTIONAL MATCH (c:Complaint {complaint_id: r.complaint_id})
               FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END | MERGE (n)-[:ON]->(c))""", notes)
    print(f"  agent notes: {len(notes)}")

    docs = [parse_kb(p) for p in sorted((UNSTRUCTURED / "kb").glob("*.md"))]
    batched("""UNWIND $rows AS r MERGE (d:KbDoc {doc_id: r.doc_id})
               SET d.title = r.title, d.doc_type = r.doc_type, d.version = r.version,
                   d.published_on = r.published_on, d.audience = r.audience, d.tags = r.tags
               WITH d, r UNWIND r.chunks AS ch
               MERGE (k:KbChunk {chunk_id: ch.chunk_id})
               SET k.text = ch.text, k.idx = ch.idx, k.doc_id = r.doc_id, k.title = r.title
               MERGE (d)-[:HAS_CHUNK]->(k)""", docs, size=50)
    print(f"  kb docs: {len(docs)} ({sum(len(d['chunks']) for d in docs)} chunks)")

    link_clues(complaints, calls, notes, docs)


def parse_kb(path):
    raw = path.read_text(encoding="utf-8")
    meta, body = {}, raw
    if raw.startswith("---"):
        _, header, body = raw.split("---", 2)
        for line in header.strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip().strip('"')
    tags = [t.strip() for t in meta.get("tags", "").strip("[]").split(",") if t.strip()]
    chunks, current = [], ""
    for para in [p.strip() for p in body.split("\n\n") if p.strip()]:
        if current and len(current) + len(para) > 900:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{para}".strip()
    if current:
        chunks.append(current)
    doc_id = meta.get("doc_id", path.stem)
    return {"doc_id": doc_id, "title": meta.get("title", doc_id), "doc_type": meta.get("doc_type"),
            "version": meta.get("version"), "published_on": meta.get("published_on"),
            "audience": meta.get("audience"), "tags": tags,
            "chunks": [{"chunk_id": f"{doc_id}#{i}", "idx": i, "text": c} for i, c in enumerate(chunks)]}


def link_clues(complaints, calls, notes, docs):
    """Pull caller numbers, UPI ids, handles, SMS senders, apps and UTRs out of
    every text and connect them - this is what joins separate complaints."""
    sources = ([("Complaint", "complaint_id", c["complaint_id"], f"{c.get('subject', '')}\n{c.get('text', '')}") for c in complaints]
               + [("CallTranscript", "call_id", c["call_id"], c["text"]) for c in calls]
               + [("AgentNote", "note_id", n["note_id"], n.get("text", "")) for n in notes]
               + [("KbChunk", "chunk_id", ch["chunk_id"], ch["text"]) for d in docs for ch in d["chunks"]])
    mentions, utrs = {}, {}
    for label, key, sid, text in sources:
        mentions.setdefault((label, key), []).extend(
            {"id": sid, "kind": kind, "value": value} for kind, value in extract_clues(text))
        utrs.setdefault((label, key), []).extend({"id": sid, "utr": u} for u in extract_utrs(text))
    total = 0
    for (label, key), rows in mentions.items():
        total += len(rows)
        batched(f"""UNWIND $rows AS r MATCH (s:{label} {{{key}: r.id}})
                    MERGE (c:Clue {{key: r.kind + ':' + r.value}})
                    ON CREATE SET c.kind = r.kind, c.value = r.value
                    MERGE (s)-[:MENTIONS]->(c)""", rows)
    for (label, key), rows in utrs.items():
        batched(f"""UNWIND $rows AS r MATCH (s:{label} {{{key}: r.id}})
                    MATCH (t:Transaction {{utr: r.utr}}) MERGE (s)-[:REFERS_TO]->(t)""", rows)
    for kind, label in [("phone", "Phone"), ("upi", "UpiId"), ("handle", "TelegramHandle"),
                        ("sms_sender", "SmsSender"), ("app", "App")]:
        run(f"MATCH (c:Clue {{kind: '{kind}'}}) SET c:{label}")
    # Bridge text to structured data: a UPI id in a complaint IS that account.
    run("MATCH (c:Clue {kind: 'upi'}) MATCH (x:Counterparty {upi_id: c.value}) MERGE (c)-[:IDENTIFIES]->(x)")
    run("MATCH (c:Clue {kind: 'upi'}) MATCH (a:Account {upi_id: c.value}) MERGE (c)-[:IDENTIFIES]->(a)")
    print(f"  clue mentions: {total}")


def embed_missing():
    for label, key, text in [("Complaint", "complaint_id", "coalesce(n.subject, '') + '\\n' + n.text"),
                             ("CallTranscript", "call_id", "n.text"),
                             ("KbChunk", "chunk_id", "n.title + '\\n' + n.text")]:
        rows = run(f"MATCH (n:{label}) WHERE n.embedding IS NULL RETURN n.{key} AS id, {text} AS text")
        if not rows:
            continue
        vectors = embed([r["text"] for r in rows])
        batched(f"""UNWIND $rows AS r MATCH (n:{label} {{{key}: r.id}})
                    CALL db.create.setNodeVectorProperty(n, 'embedding', r.embedding)""",
                [{"id": r["id"], "embedding": v} for r, v in zip(rows, vectors)], size=200)
        print(f"  embedded {len(rows)} {label} nodes")


if __name__ == "__main__":
    t0 = time.time()
    print("schema"); setup_schema()
    print("structured data"); load_structured()
    print("text data"); load_text()
    print("embeddings"); embed_missing()
    counts = run("MATCH (n) WHERE n:Customer OR n:Account OR n:Transaction OR n:Counterparty OR n:Complaint "
                 "OR n:CallTranscript OR n:AgentNote OR n:KbChunk OR n:Clue "
                 "RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC")
    print({r["label"]: r["n"] for r in counts})
    print(f"done in {time.time() - t0:.0f}s")
    driver.close()

