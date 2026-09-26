# Shared plumbing for Kavach: settings from the .env one folder up, the Neo4j
# driver, the OpenRouter client, embeddings, and pattern-based clue extraction.
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

ROOT = Path(__file__).parent
DATA = ROOT / "data"
load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")  # optional override, e.g. on a deployment

DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "google/gemini-embedding-001")
EMBED_DIM = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
CHAT_MODEL = os.getenv("KAVACH_CHAT_MODEL", "openai/gpt-4.1-mini")

# Schema hints ("label does not exist yet") and deprecation notices are noise here.
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)
llm = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
)


def run(query, **params):
    """Run a Cypher query and return the rows as plain dicts."""
    records, _, _ = driver.execute_query(query, parameters_=params, database_=DATABASE)
    return [r.data() for r in records]


def embed(texts, batch_size=64):
    """Embed texts with the configured model, EMBED_DIM floats each."""
    vectors = []
    for i in range(0, len(texts), batch_size):
        batch = [(t or " ")[:6000] for t in texts[i:i + batch_size]]
        resp = llm.embeddings.create(model=EMBED_MODEL, input=batch, dimensions=EMBED_DIM)
        got = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
        if got and len(got[0]) != EMBED_DIM:
            raise RuntimeError(f"{EMBED_MODEL} returned {len(got[0])}-d vectors, expected {EMBED_DIM}")
        vectors.extend(got)
    return vectors


# Clue patterns. Phones in this dataset are +91 5XXXX XXXXX; UPI ids have no dot
# after the '@' (which keeps emails out); Telegram handles stand alone.
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]*)?(5\d{4})[\s-]?(\d{5})(?!\d)")
UPI = re.compile(r"(?<![\w.@])([a-z0-9][a-z0-9._-]{1,63}@[a-z][a-z0-9]{2,20})(?![\w.@])", re.I)
HANDLE = re.compile(r"(?<![\w@.])@([a-z][a-z0-9_]{4,31})(?![\w@])", re.I)
SMS_SENDER = re.compile(r"\b([A-Z]{2}-[A-Z0-9]{5,6})\b")
UTR = re.compile(r"(?<!\d)(\d{12})(?!\d)")
APPS = {
    "AnyDesk": re.compile(r"any\s*desk", re.I),
    "TeamViewer QuickSupport": re.compile(r"team\s*viewer|quick\s*support", re.I),
    "Bill Update APK": re.compile(r"bill[\s-]*update", re.I),
}


def extract_clues(text):
    """Return (kind, value) pairs for the scam clues a text mentions."""
    text = text or ""
    found = set()
    for a, b in PHONE.findall(text):
        found.add(("phone", f"+91 {a} {b}"))
    upi_ids = {m.lower() for m in UPI.findall(text)}
    for u in upi_ids:
        found.add(("upi", u))
    for h in HANDLE.findall(text):
        if not any(u.endswith("@" + h.lower()) for u in upi_ids):
            found.add(("handle", "@" + h.lower()))
    for s in SMS_SENDER.findall(text):
        found.add(("sms_sender", s))
    for app, pattern in APPS.items():
        if pattern.search(text):
            found.add(("app", app))
    return sorted(found)


def extract_utrs(text):
    return sorted(set(UTR.findall(text or "")))
