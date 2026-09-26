# Kavach web app: a ChatGPT-style chat with the agent as a chosen customer, a
# memory ON/OFF switch, live progress while the agent works, and the part of the
# Neo4j graph each answer came from.
# Run: .venv\Scripts\python.exe -m streamlit run app.py
import base64
import html
import re
import time
from datetime import date

import streamlit as st
import streamlit.components.v1 as components
from neo4j import Result

st.set_page_config(page_title="Kavach · Sahyadri Bank", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

from agent import demo_customers, handle_turn, recall_customer, reset_customer  # noqa: E402
from common import CHAT_MODEL, DATABASE, driver, run  # noqa: E402

COLORS = {"Customer": "#018BFF", "Complaint": "#F79767", "Clue": "#E0115F", "Transaction": "#8DCC93",
          "Account": "#4C8EDA", "Counterparty": "#C990C0", "CashOutPoint": "#6A0DAD", "Promise": "#FFC454",
          "Preference": "#57C7E3", "Card": "#A5ABB6"}
LEGEND = [("Customer", "Customer"), ("Complaint", "Complaint"), ("Clue", "Clue"), ("Transaction", "Payment"),
          ("Counterparty", "Receiving account"), ("CashOutPoint", "Cash-out"), ("Promise", "Promise"),
          ("Preference", "Preference")]
LANGS = {"hi": "Hindi", "mr": "Marathi", "en": "English", "hinglish": "Hinglish"}
CLUE_NAMES = {"phone": "Caller number", "upi": "UPI id", "handle": "Telegram handle", "sms_sender": "SMS sender",
              "app": "App"}
STEPS = {  # step name -> (icon, what it did, short chip label)
    "recall_customer": ("🧠", "Recalled this customer's memory from Neo4j", "Memory"),
    "check_recent_payments": ("💳", "Checked payments from the last 3 days", "Payments"),
    "extract_scam_clues": ("🧩", "Pulled scam clues out of the message", "Clues"),
    "find_linked_complaints_and_money_trail": ("🕸️", "Searched the graph: linked complaints and money trail",
                                               "Graph search"),
    "search_bank_advisories": ("📚", "Searched bank advisories (GraphRAG)", "Advisories"),
    "open_fraud_case": ("📝", "Opened the fraud case: card block, dispute, refund promise", "Case opened"),
    "save_customer_preference": ("⚙️", "Saved a customer preference", "Preference"),
    "log_interaction": ("🗂️", "Saved this conversation to memory", "Saved"),
    "none": ("⚪", "Memory OFF: no Neo4j history, no graph lookups", "No memory"),
    "fallback": ("⚠️", "LangChain agent failed, so the fixed pipeline answered", "Fallback"),
}
ALIASES = {"recent_debits": "check_recent_payments", "extract_clues": "extract_scam_clues",
           "find_ring": "find_linked_complaints_and_money_trail", "search_advisories": "search_bank_advisories",
           "save_preference": "save_customer_preference"}
SUGGESTIONS = [
    ("🚨", "Report a scam", "Mujhe KYC team se call aaya, unhone AnyDesk install karwaya aur ab mere account se "
                           "40000 rupaye kat gaye. Please help!"),
    ("🔄", "Ask for an update", "Koi update?"),
    ("🕵️", "Ask about the gang", "Did other people lose money to the same account? Where did my money go?"),
    ("🛡️", "Ask a safety question", "How do I spot a fake UPI collect request?"),
]

SHIELD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" rx="20" '
          'fill="{bg}"/><path d="M20 8.5l9.5 3.6v6.8c0 6.1-4 10.8-9.5 12.6-5.5-1.8-9.5-6.5-9.5-12.6v-6.8z" '
          'fill="#fff"/><path d="M15.8 20.2l3 3 5.6-6.1" fill="none" stroke="{bg}" stroke-width="2.6" '
          'stroke-linecap="round" stroke-linejoin="round"/></svg>')
AVATAR_ON, AVATAR_OFF = SHIELD.format(bg="#018BFF"), SHIELD.format(bg="#94A3B8")


def svg_img(svg, cls=""):
    return f'<img class="{cls}" src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}">'


CSS = """
<style>
:root { --ink:#0F172A; --muted:#64748B; --line:#E6E9EF; --soft:#F5F7FA; --blue:#018BFF; }
[data-testid="stMainBlockContainer"] { padding-top:1.4rem; padding-bottom:.8rem; max-width:1560px; }
[data-testid="stHeader"] { background:transparent; }
[data-testid="stDecoration"], [data-testid="stAppDeployButton"] { display:none; }

/* sidebar */
.kv-brand { display:flex; align-items:center; gap:.75rem; margin:.1rem 0 .3rem; }
.kv-brand img { width:44px; height:44px; filter:drop-shadow(0 6px 14px rgba(1,139,255,.3)); }
.kv-brand b { display:block; font-size:1.35rem; letter-spacing:-.02em; color:var(--ink); line-height:1.2; }
.kv-brand span { font-size:.8rem; color:var(--muted); }
.kv-label { font-size:.68rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:#94A3B8;
            margin:.6rem 0 -.3rem; }
.kv-stack { font-size:.8rem; color:var(--muted); line-height:1.75; }
.kv-stack b { color:var(--ink); font-weight:600; }
.kv-foot { font-size:.72rem; color:#94A3B8; margin-top:.4rem; }

/* chat header */
.kv-head { display:flex; align-items:center; gap:.8rem; padding:0 .1rem .75rem; border-bottom:1px solid var(--line); }
.kv-ava { width:44px; height:44px; border-radius:50%; background:#E8F3FF; color:#0369C9; font-weight:700;
          display:grid; place-items:center; flex:none; font-size:1rem; }
.kv-who { flex:1; min-width:0; }
.kv-who b { font-size:1.08rem; color:var(--ink); }
.kv-who div { font-size:.82rem; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.kv-pills { display:flex; gap:.4rem; flex-wrap:wrap; justify-content:flex-end; }
.kv-pill { display:inline-flex; align-items:center; gap:.4rem; padding:.28rem .7rem; border-radius:999px;
           font-size:.75rem; font-weight:600; white-space:nowrap; }
.kv-pill i { width:7px; height:7px; border-radius:50%; background:currentColor; }
.kv-on { background:#E8F7EE; color:#15803D; } .kv-off { background:#F1F5F9; color:#64748B; }
.kv-due { background:#FFF4E0; color:#B45309; }

/* conversation */
[data-testid="stLayoutWrapper"]:has(> .st-key-chat_scroll) { flex:0 0 auto !important;
    height:max(22rem, calc(100vh - 12.8rem)) !important; }
.st-key-chat_scroll { height:100% !important; }
.kv-user { display:flex; justify-content:flex-end; margin:.6rem 0 .9rem; }
.kv-user div { background:#EEF2F7; color:var(--ink); padding:.7rem 1.05rem; border-radius:1.4rem 1.4rem .4rem 1.4rem;
               max-width:80%; white-space:pre-wrap; line-height:1.55; font-size:.97rem; }
[data-testid="stChatMessage"] { background:transparent !important; padding:.1rem 0 .4rem; gap:.75rem; }
[data-testid="stChatMessageContent"] { font-size:.97rem; line-height:1.65; color:var(--ink); }
.kv-meta { display:flex; flex-wrap:wrap; align-items:center; gap:.35rem; margin-top:-.2rem; }
.kv-chip { font-size:.72rem; color:#475569; background:#F8FAFC; border:1px solid var(--line); padding:.12rem .55rem;
           border-radius:999px; }
.kv-chip.t { border-color:transparent; background:none; color:#94A3B8; padding-left:.15rem; }

/* input */
[data-testid="stChatInput"] { border-radius:1.75rem !important; border:1px solid #DCE1E8 !important;
                              box-shadow:0 4px 18px rgba(15,23,42,.07); background:#fff !important; }
[data-testid="stChatInput"]:focus-within { border-color:#9CCBFF !important; box-shadow:0 4px 22px rgba(1,139,255,.16); }
[data-testid="stChatInput"] > div { background:#fff !important; }
[data-testid="stChatInput"] textarea { font-size:.98rem; }
[data-testid="stChatInputSubmitButton"] { background:var(--ink) !important; color:#fff !important;
                                          border-radius:50% !important; }
[data-testid="stChatInputSubmitButton"]:disabled { background:#CBD5E1 !important; }

/* welcome */
.kv-hello { text-align:center; padding:7vh 1rem 1.2rem; }
.kv-hello img { width:58px; height:58px; }
.kv-hello .h { font-size:1.8rem; font-weight:700; letter-spacing:-.02em; margin:.8rem 0 .35rem; color:var(--ink); }
.kv-hello .p { color:var(--muted); max-width:31rem; margin:0 auto; font-size:.95rem; line-height:1.55; }
.st-key-suggest { max-width:40rem; margin:0 auto; }
.st-key-suggest button { justify-content:flex-start; min-height:3.9rem; padding:.65rem .95rem; border-radius:1rem;
                         border:1px solid var(--line); background:#fff; box-shadow:0 1px 2px rgba(15,23,42,.04); }
.st-key-suggest button:hover { border-color:#9CCBFF; background:#F5FAFF; color:var(--ink); }
.st-key-suggest button p { font-size:.86rem; white-space:normal; text-align:left; line-height:1.4; }

/* right panel */
.kv-legend { display:flex; flex-wrap:wrap; gap:.25rem .9rem; font-size:.76rem; color:#475569; margin:.1rem 0 .3rem; }
.kv-legend span { display:inline-flex; align-items:center; gap:.35rem; }
.kv-legend i { width:10px; height:10px; border-radius:50%; }
.kv-sec { font-size:.72rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#94A3B8;
          margin:.9rem 0 .4rem; }
.kv-card { border:1px solid var(--line); border-radius:.9rem; padding:.7rem .9rem; margin-bottom:.5rem; background:#fff; }
.kv-card .h { display:flex; justify-content:space-between; align-items:center; gap:.5rem; font-size:.76rem;
              color:var(--muted); }
.kv-card .t { font-weight:600; color:var(--ink); margin:.2rem 0 .1rem; font-size:.92rem; }
.kv-card .x { font-size:.84rem; color:#334155; line-height:1.5; }
.kv-card .n { font-size:.8rem; color:var(--muted); font-style:italic; margin-top:.3rem; }
.kv-tag { font-size:.66rem; font-weight:700; padding:.12rem .5rem; border-radius:999px; background:#F1F5F9;
          color:#475569; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; }
.kv-tag.red { background:#FDECEC; color:#B91C1C; } .kv-tag.green { background:#E8F7EE; color:#15803D; }
.kv-tag.amber { background:#FFF4E0; color:#B45309; } .kv-tag.blue { background:#E8F3FF; color:#0369C9; }
.kv-tiles { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:.55rem; margin:.5rem 0 .6rem; }
.kv-tile { border:1px solid var(--line); border-radius:.9rem; padding:.7rem .85rem; background:#fff; }
.kv-tile span { display:block; font-size:.7rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em;
                font-weight:600; }
.kv-tile b { display:block; font-size:.98rem; color:var(--ink); margin-top:.2rem; word-break:break-word; }
.kv-banner { border-radius:.9rem; padding:.8rem 1rem; font-size:.88rem; margin:.3rem 0 .6rem; line-height:1.5; }
.kv-banner.ok { background:#EEF9F2; color:#14532D; border:1px solid #BFE6CC; }
.kv-banner.ring { background:#FFF3F7; color:#831843; border:1px solid #F8CADB; }
.kv-banner.off { background:#F5F7FA; color:#475569; border:1px solid var(--line); }
.kv-banner ul { margin:.35rem 0 0 1.1rem; padding:0; } .kv-banner li { margin:.2rem 0; }
.kv-step { display:flex; gap:.75rem; padding:.6rem 0; border-bottom:1px dashed var(--line); }
.kv-step .i { width:32px; height:32px; border-radius:10px; background:#F1F6FF; display:grid; place-items:center;
              flex:none; font-size:1rem; }
.kv-step .l { font-size:.88rem; font-weight:600; color:var(--ink); }
.kv-step .s { font-size:.8rem; color:var(--muted); margin-top:.1rem; line-height:1.45; }
.kv-muted { font-size:.8rem; color:var(--muted); margin:.2rem 0 .4rem; }
.kv-empty { text-align:center; color:var(--muted); padding:3.5rem 1.5rem; font-size:.9rem; line-height:1.6; }
.kv-empty div { font-size:2rem; margin-bottom:.4rem; }
</style>
"""

SUBGRAPH = """
MATCH (c:Customer {customer_id: $cid})
CALL (c) {
  MATCH p = (c)-[:RAISED|HAS_PROMISE|PREFERS]->() RETURN p
  UNION
  MATCH p = (c)-[:RAISED]->(:Complaint)-[:MENTIONS]->(k:Clue) WHERE k.kind <> 'app' RETURN p
  UNION
  MATCH (c)-[:RAISED]->(:Complaint)-[:MENTIONS]->(k:Clue) WHERE k.kind IN ['phone', 'upi', 'handle', 'sms_sender']
  MATCH p = (k)<-[:MENTIONS]-(:Complaint)<-[:RAISED]-(o:Customer) WHERE o <> c RETURN p
  UNION
  MATCH p = (c)-[:RAISED]->(:Complaint)-[:REPORTS]->(:Transaction)-[:TO]->(:Counterparty) RETURN p
  UNION
  MATCH (c)-[:RAISED]->(:Complaint)-[:REPORTS]->(:Transaction)-[:TO]->(x:Counterparty)
  MATCH p = (x)-[:TRANSFERRED_TO*1..3]->(:Counterparty) RETURN p
  UNION
  MATCH (c)-[:RAISED]->(:Complaint)-[:REPORTS]->(:Transaction)-[:TO]->(x:Counterparty)
  MATCH p = (:Counterparty)-[:TRANSFERRED_TO*1..2]->(x) RETURN p
  UNION
  MATCH (c)-[:RAISED]->(:Complaint)-[:REPORTS]->(:Transaction)-[:TO]->(x:Counterparty)
  MATCH (x)-[:TRANSFERRED_TO*0..3]->(y:Counterparty)
  MATCH p = (y)-[:CASHED_OUT]->(:CashOutPoint) RETURN p
  UNION
  MATCH (c)-[:RAISED]->(:Complaint)-[:MENTIONS]->(k:Clue)
  MATCH p = (k)-[:IDENTIFIES]->(:Counterparty) RETURN p
}
RETURN p LIMIT 400
"""

HEADER = """
MATCH (c:Customer {customer_id: $cid})
OPTIONAL MATCH (c)-[:HAS_PROMISE]->(p:Promise {status: 'OPEN'})
RETURN c.full_name AS name, c.age AS age, c.city AS city, c.preferred_language AS lang,
       toString(min(p.due_on)) AS due
"""


def caption(node):
    label = next((l for l in node.labels if l in COLORS), next(iter(node.labels), "Node"))
    p = dict(node)
    text = {"Customer": p.get("full_name"), "Complaint": p.get("complaint_id"), "Clue": p.get("value"),
            "Transaction": f"Rs {p.get('amount_inr', 0):,.0f}" if p.get("amount_inr") else "txn",
            "Account": f"a/c ..{str(p.get('account_number', ''))[-4:]}", "Counterparty": p.get("holder_name"),
            "CashOutPoint": f"{p.get('exit_type', '')} {p.get('city', '')}",
            "Promise": f"refund decision by {p.get('due_on')}", "Preference": p.get("value")}.get(label)
    return label, str(text or label)


def graph_html(cid):
    g = driver.execute_query(SUBGRAPH, cid=cid, database_=DATABASE, result_transformer_=Result.graph)
    if not g.nodes:
        return None, 0
    try:
        from neo4j_viz import Node, Relationship, VisualizationGraph
        nodes = []
        for n in g.nodes:
            label, text = caption(n)
            is_me = label == "Customer" and dict(n).get("customer_id") == cid
            nodes.append(Node(id=n.element_id, caption=text, color=COLORS.get(label, "#A5ABB6"),
                              size=34 if is_me else (22 if label in ("Customer", "Counterparty") else 16)))
        rels = [Relationship(source=r.start_node.element_id, target=r.end_node.element_id, caption=r.type)
                for r in g.relationships]
        return VisualizationGraph(nodes=nodes, relationships=rels).render(height="560px", theme="light").data, len(nodes)
    except Exception:  # fall back to pyvis if the NVL widget API differs
        from pyvis.network import Network
        net = Network(height="560px", width="100%", directed=True, bgcolor="#ffffff")
        for n in g.nodes:
            label, text = caption(n)
            net.add_node(n.element_id, label=text, color=COLORS.get(label, "#A5ABB6"), title=label)
        for r in g.relationships:
            net.add_edge(r.start_node.element_id, r.end_node.element_id, label=r.type)
        return net.generate_html(), len(g.nodes)


# --- Cached reads (keyed by a per-customer version that changes after each write)

@st.cache_data(ttl=600, show_spinner=False)
def customers():
    return demo_customers()


@st.cache_data(ttl=600, show_spinner=False)
def graph_size():
    return run("MATCH (n) RETURN count(n) AS n")[0]["n"], run("MATCH ()-[r]->() RETURN count(r) AS r")[0]["r"]


@st.cache_data(ttl=120, show_spinner=False)
def header_info(cid, version):
    rows = run(HEADER, cid=cid)
    return rows[0] if rows else {}


@st.cache_data(ttl=120, show_spinner=False)
def memory_of(cid, version):
    return recall_customer(cid)


@st.cache_data(ttl=120, show_spinner=False)
def graph_of(cid, version):
    return graph_html(cid)


# --- Small formatting helpers

def esc(x):
    return html.escape(str(x if x is not None else ""))


def inr(x):
    return f"₹{x:,.0f}" if x else "₹0"


def nice_date(s):
    try:
        return date.fromisoformat(str(s)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(s or "")


def nice_time(s):
    return str(s or "")[:16].replace("T", " · ")


def canonical(name):
    name = str(name).split(" ")[0]
    return ALIASES.get(name, name)


def status_tag(status):
    s = str(status or "").upper()
    tone = ("red" if s in ("ESCALATED", "HOTLISTED", "BLOCKED", "CRITICAL") else
            "green" if s in ("RESOLVED", "CLOSED", "ACTIVE", "DONE") else "amber" if s in ("OPEN", "IN_PROGRESS") else "")
    return f'<span class="kv-tag {tone}">{esc(s.replace("_", " ") or "-")}</span>'


def typing(text):
    """Stream a finished reply word by word, like a chat model typing."""
    for i, piece in enumerate(re.split(r"(\s+)", text)):
        yield piece
        if i % 3 == 0:
            time.sleep(0.01)


def ring_lines(ring):
    """Scam-ring signals found in the graph, as short sentences."""
    lines = []
    for s in (ring or {}).get("shared_clues", [])[:3]:
        if s.get("other_customers"):
            lines.append(f"{CLUE_NAMES.get(s['kind'], s['kind'])} <b>{esc(s['value'])}</b> appears in complaints from "
                         f"<b>{s['other_customers']}</b> other customers")
    for p in (ring or {}).get("other_customers_paying_same_accounts", [])[:2]:
        if p.get("other_payers"):
            lines.append(f"<b>{p['other_payers']}</b> other customers paid <b>{esc(p['beneficiary'])}</b> "
                         f"({inr(p.get('paid_by_others_inr'))})")
    for t in (ring or {}).get("money_trail", [])[:2]:
        if t.get("forwarded_to"):
            exits = sorted({c.split(" in ")[0].replace("_", " ").lower() for c in t.get("cash_out") or []})
            lines.append(f"Money moved from <b>{esc(t['start'])}</b> to <b>{len(t['forwarded_to'])}</b> more accounts, "
                         f"then out as {esc(', '.join(exits) or 'unknown')} ({inr(t.get('cashed_out_inr'))})")
    feeders = [u for u in (ring or {}).get("accounts_feeding_the_same_account", []) if u.get("feeder")]
    if feeders:
        lines.append(f"<b>{len(feeders)}</b> accounts from other scams send money into the same account "
                     f"({esc(', '.join(f['feeder'] for f in feeders[:3]))}): one gang")
    return lines


def step_summary(name, result, last):
    """One line saying what a step found."""
    try:
        if name == "recall_customer":
            c = result.get("customer") or {}
            return (f"{len(result.get('complaint_history', []))} past complaints · {len(result.get('promises', []))} "
                    f"promises · {len(result.get('recent_kavach_interactions', []))} past chats · replies in "
                    f"{LANGS.get(c.get('preferred_language'), 'English')}")
        if name == "check_recent_payments":
            if not result:
                return "No suspicious payments in the last 3 days"
            apps = sorted({str(p["remote_access_app"]) for p in result if p.get("remote_access_app")})
            to = sorted({p["to_upi"] for p in result if p.get("to_upi")})
            return (f"{len(result)} payments · {inr(sum(p.get('amount_inr') or 0 for p in result))} to {', '.join(to)}"
                    + (f" · {', '.join(apps)} active during the session" if apps else ""))
        if name == "extract_scam_clues":
            return " · ".join(f"{CLUE_NAMES.get(c['kind'], c['kind'])}: {c['value']}" for c in result) or "No clues in the text"
        if name == "find_linked_complaints_and_money_trail":
            lines = ring_lines(last.get("ring") or (result if isinstance(result, dict) else {}))
            return re.sub("<[^>]+>", "", "; ".join(lines[:2])) or "No linked complaints"
        if name == "search_bank_advisories":
            return " · ".join(h["title"] for h in result[:3])
        if name == "open_fraud_case":
            return (f"{result['complaint_id']} · dispute {result['dispute_id']} · refund decision due "
                    f"{nice_date(result['refund_decision_due'])}")
        return str(result or "")
    except Exception:
        return ""


def step_detail(name, detail):
    """Extra words for the live progress line."""
    if name == "recall_customer" and isinstance(detail, dict):
        return f": {step_summary(name, detail, {})}"
    if name == "find_linked_complaints_and_money_trail" and isinstance(detail, dict) and detail.get("clue_values"):
        return f": {', '.join(map(str, detail['clue_values'][:3]))}"
    if name == "search_bank_advisories" and isinstance(detail, dict) and detail.get("query"):
        return f': "{detail["query"]}"'
    return ""


# --- Chat rendering

def chat_header(info, memory_on, fallback_name):
    name = info.get("name") or fallback_name
    bits = [b for b in (info.get("city"), f"{info['age']} yrs" if info.get("age") else None,
                        f"replies in {LANGS.get(info.get('lang'), 'English')}") if b]
    pills = [f'<span class="kv-pill {"kv-on" if memory_on else "kv-off"}"><i></i>Memory {"ON" if memory_on else "OFF"}</span>']
    if info.get("due"):
        pills.append(f'<span class="kv-pill kv-due">📌 Refund decision due {esc(nice_date(info["due"]))}</span>')
    initials = "".join(p[0] for p in name.split()[:2]).upper()
    return (f'<div class="kv-head"><div class="kv-ava">{esc(initials)}</div><div class="kv-who"><b>{esc(name)}</b>'
            f'<div>{esc(" · ".join(bits))}</div></div><div class="kv-pills">{"".join(pills)}</div></div>')


def meta_html(m):
    chips = [f'<span class="kv-chip">{STEPS[t][0]} {STEPS[t][2]}</span>' for t in m.get("tools", []) if t in STEPS]
    chips.append(f'<span class="kv-chip t">{m.get("secs", 0):.1f}s</span>')
    return f'<div class="kv-meta">{"".join(chips)}</div>'


def show_message(m):
    if m["role"] == "user":
        st.html(f'<div class="kv-user"><div>{esc(m["content"])}</div></div>')
        return
    with st.chat_message("assistant", avatar=AVATAR_ON if m.get("memory", True) else AVATAR_OFF):
        st.markdown(m["content"])
        st.html(meta_html(m))


def welcome(first, memory_on):
    text = ("I'm Kavach, Sahyadri Bank's support agent. I remember your past complaints and promises, check your "
            "payments and search the bank's fraud graph." if memory_on else
            "Memory is OFF: this is the same LLM with no history and no Neo4j graph. Compare the answers.")
    st.html(f'<div class="kv-hello">{svg_img(AVATAR_ON if memory_on else AVATAR_OFF)}'
            f'<div class="h">Namaste, {esc(first)} 👋</div><div class="p">{esc(text)}</div></div>')
    with st.container(key="suggest"):
        cols = st.columns(2)
        for i, (icon, title, text) in enumerate(SUGGESTIONS):
            short = text if len(text) <= 58 else text[:55].rsplit(" ", 1)[0] + "…"
            cols[i % 2].button(f"{icon} **{title}**: {short}", key=f"suggest_{i}", width="stretch",
                               on_click=lambda t=text: st.session_state.update(pending=t))


def answer(cid, prompt, memory_on, chat):
    chat.append({"role": "user", "content": prompt})
    show_message(chat[-1])
    with st.chat_message("assistant", avatar=AVATAR_ON if memory_on else AVATAR_OFF):
        status = st.status("Checking memory and the graph…" if memory_on else "Answering without memory…",
                           expanded=True)

        def on_step(name, detail):
            icon, label, _ = STEPS.get(name, ("🔧", name, name))
            status.write(f"{icon} {label}{step_detail(name, detail)}")

        started = time.time()
        with status:
            if not memory_on:
                st.write(f"{STEPS['none'][0]} {STEPS['none'][1]}")
            result = handle_turn(cid, prompt, memory_on, on_step=on_step)
        secs = time.time() - started
        tools = list(dict.fromkeys(canonical(s["tool"]) for s in result["trace"]))
        used = [t for t in tools if t not in ("none", "fallback")]
        status.update(label=(f"Used {len(used)} Neo4j memory and graph steps · {secs:.1f}s" if memory_on
                             else f"No memory used · {secs:.1f}s"), state="complete", expanded=False)
        st.write_stream(typing(result["reply"]))
        message = {"role": "assistant", "content": result["reply"], "tools": tools, "secs": secs, "memory": memory_on}
        st.html(meta_html(message))
    chat.append(message)
    st.session_state.traces[cid] = {**result, "secs": secs, "message": prompt, "memory": memory_on}
    st.session_state.version[cid] = time.time()


# --- Right-hand panel

def memory_view(mem, memory_on):
    if not memory_on:
        st.html('<div class="kv-banner off">Memory is OFF, so Kavach is not using anything below. It is still '
                'stored in Neo4j and comes back when you switch memory ON.</div>')
    c = mem.get("customer") or {}
    accounts = " · ".join(f"a/c ..{str(a.get('account_number', ''))[-4:]} ({esc(a.get('upi_id'))})"
                          for a in mem.get("accounts", []))
    cards = " ".join(f'{esc(k.get("masked_pan"))} {status_tag(k.get("status"))}' for k in mem.get("cards", []))
    prefs = ", ".join(f"{esc(p['kind']).replace('_', ' ')}: {esc(LANGS.get(p['value'], p['value']))}"
                      for p in mem.get("preferences", []))
    st.html(f'<div class="kv-sec">Profile</div><div class="kv-card"><div class="t">{esc(c.get("full_name"))}</div>'
            f'<div class="x">{esc(c.get("age"))} yrs · {esc(c.get("city"))} · {esc(str(c.get("segment", "")).replace("_", " "))}'
            f' · replies in {esc(LANGS.get(c.get("preferred_language"), "English"))}</div>'
            f'<div class="x">{accounts}</div><div class="x">Cards: {cards or "-"}</div>'
            + (f'<div class="x">Saved preferences: {prefs}</div>' if prefs else "") + "</div>")

    promises = mem.get("promises", [])
    if promises:
        st.html('<div class="kv-sec">Promises Kavach made</div>' + "".join(
            f'<div class="kv-card"><div class="h"><span>{esc(p.get("dispute_id"))}</span>{status_tag(p.get("status"))}'
            f'</div><div class="t">Due {esc(nice_date(p.get("due_on")))}</div><div class="x">{esc(p.get("what"))}</div></div>'
            for p in promises))

    history = mem.get("complaint_history", [])
    st.html('<div class="kv-sec">Complaint history</div>' + ("".join(
        f'<div class="kv-card"><div class="h"><span>{esc(h.get("complaint_id"))} · {esc(nice_time(h.get("at")))} · '
        f'{esc(str(h.get("channel", "")).replace("_", " "))}</span>{status_tag(h.get("status"))}</div>'
        f'<div class="t">{esc(h.get("subject"))}</div><div class="x">{esc((h.get("text") or "")[:180])}'
        f'{"…" if len(h.get("text") or "") > 180 else ""}</div>'
        + "".join(f'<div class="n">Staff note: {esc(n[:160])}{"…" if len(n) > 160 else ""}</div>'
                  for n in (h.get("staff_notes") or [])[:1])
        + "</div>" for h in history) or '<div class="kv-muted">No complaints on record.</div>'))

    chats = mem.get("recent_kavach_interactions", [])
    if chats:
        st.html('<div class="kv-sec">Past conversations with Kavach</div>' + "".join(
            f'<div class="kv-card"><div class="h"><span>{esc(nice_time(i.get("at")))}</span></div>'
            f'<div class="x">“{esc((i.get("customer_said") or "")[:140])}”</div>'
            f'<div class="n">{esc(i.get("kavach_did"))}</div></div>' for i in chats))


def why_view(last):
    if not last:
        st.html('<div class="kv-empty"><div>🔍</div>Send a message to see which memories and graph lookups Kavach '
                'used for its answer.</div>')
        return
    steps = last.get("trace", [])
    st.html(f'<div class="kv-muted">For “{esc(last["message"][:90])}{"…" if len(last["message"]) > 90 else ""}” · '
            f'{len(steps)} steps · {last.get("secs", 0):.1f}s · {esc(CHAT_MODEL)}</div>')
    lines = ring_lines(last.get("ring"))
    if lines:
        st.html('<div class="kv-banner ring"><b>🔗 Scam-ring signals found in the graph</b><ul>'
                + "".join(f"<li>{line}</li>" for line in lines) + "</ul></div>")
    rows = []
    for s in steps:
        name = canonical(s["tool"])
        icon, label, _ = STEPS.get(name, ("🔧", name, name))
        summary = step_summary(name, s.get("result", s.get("note")), last)
        rows.append(f'<div class="kv-step"><div class="i">{icon}</div><div><div class="l">{esc(label)}</div>'
                    f'<div class="s">{esc(summary)}</div></div></div>')
    st.html("".join(rows))
    with st.expander("Raw tool calls and results (JSON)"):
        for s in steps:
            st.markdown(f"**{s['tool']}**")
            st.json(s.get("result", s.get("note")), expanded=False)


def actions_view(last, mem):
    actions = (last or {}).get("actions")
    if actions:
        st.html(f'<div class="kv-banner ok">✅ Kavach opened complaint <b>{esc(actions["complaint_id"])}</b> · '
                f'{esc(actions["status"])}</div><div class="kv-tiles">'
                f'<div class="kv-tile"><span>Dispute raised</span><b>{esc(actions["dispute_id"])}</b></div>'
                f'<div class="kv-tile"><span>Refund decision due</span><b>{esc(nice_date(actions["refund_decision_due"]))}</b></div>'
                f'<div class="kv-tile"><span>Card blocked</span><b>{esc(", ".join(actions["cards_hotlisted"]) or "No active card")}</b></div>'
                f'<div class="kv-tile"><span>Freeze requested on</span><b>{esc(", ".join(actions["beneficiary_lien_requested_for"]) or "-")}</b></div>'
                '</div><div class="kv-muted">Written to Neo4j in one transaction: the complaint and its clues, the '
                'reported payments, the card status and the promise.</div>')
    promises = mem.get("promises", [])
    if promises and not actions:
        st.html('<div class="kv-sec">Open promises (from memory)</div>' + "".join(
            f'<div class="kv-card"><div class="h"><span>{esc(p.get("dispute_id"))}</span>{status_tag(p.get("status"))}'
            f'</div><div class="t">Refund decision due {esc(nice_date(p.get("due_on")))}</div>'
            f'<div class="x">{esc(p.get("what"))}</div></div>' for p in promises))
    if not actions and not promises:
        st.html('<div class="kv-empty"><div>✅</div>No actions yet. When a customer reports fraud, Kavach blocks the '
                'card, raises a dispute, requests a freeze on the receiving account and records the refund '
                'promise here.</div>')


# --- Page

if "chats" not in st.session_state:
    st.session_state.update(chats={}, traces={}, version={})
st.html(CSS)

with st.sidebar:
    st.html(f'<div class="kv-brand">{svg_img(AVATAR_ON)}<div><b>Kavach</b>'
            '<span>Sahyadri Bank support agent</span></div></div>')
    new_chat = st.button("New chat", icon=":material/edit_square:", type="primary", width="stretch")
    st.html('<div class="kv-label">Talking as</div>')
    options = customers()
    names = {c["id"]: f"{c['name']} · {c['city']}" for c in options}
    ids = list(names)
    cid = st.selectbox("Talking as", ids, format_func=names.get, label_visibility="collapsed",
                       index=ids.index("C000150") if "C000150" in ids else 0)
    st.html('<div class="kv-label">Memory</div>')
    memory_on = st.toggle("Neo4j memory", value=True, help="OFF = the same LLM with no Neo4j memory or lookups")
    st.caption("Kavach recalls this customer's history and searches the fraud graph." if memory_on
               else "Same LLM, no history and no graph. Compare the answers.")
    reset = st.button("Reset demo for this customer", icon=":material/restart_alt:", width="stretch")
    nodes, rels = graph_size()
    st.html(f'<div class="kv-label">Under the hood</div><div class="kv-stack" style="margin-top:.5rem">'
            f'<b>Neo4j AuraDB</b> · {nodes:,} nodes · {rels:,} relationships<br><b>LangChain</b> agent with 6 '
            f'Neo4j tools<br><b>LLM</b> {esc(CHAT_MODEL)} via OpenRouter<br><b>GraphRAG</b> neo4j-graphrag · '
            'Gemini embeddings</div><div class="kv-foot">Sahyadri Bank and all data are fictional.</div>')

if new_chat:
    st.session_state.chats[cid] = []
if reset:
    reset_customer(cid)
    st.session_state.chats[cid] = []
    st.session_state.traces.pop(cid, None)
    st.session_state.version[cid] = time.time()

chat = st.session_state.chats.setdefault(cid, [])
fallback_name = names.get(cid, cid).split(" · ")[0]
first = fallback_name.split()[0]
chat_col, side_col = st.columns([1.05, 1], gap="large")

with chat_col:
    head = st.empty()
    head.html(chat_header(header_info(cid, st.session_state.version.get(cid, 0)), memory_on, fallback_name))
    box = st.container(height=560, border=False, key="chat_scroll", autoscroll=True)
    prompt = st.chat_input(f"Message Kavach as {first}…", key="chat_input", submit_mode="disable")
    prompt = prompt or st.session_state.pop("pending", None)
    with box:
        if not chat and not prompt:
            welcome(first, memory_on)
        for m in chat:
            show_message(m)
        if prompt:
            answer(cid, prompt, memory_on, chat)
            head.html(chat_header(header_info(cid, st.session_state.version[cid]), memory_on, fallback_name))

version = st.session_state.version.get(cid, 0)
last = st.session_state.traces.get(cid)
mem = memory_of(cid, version)
with side_col:
    tab_graph, tab_memory, tab_why, tab_actions = st.tabs(
        ["🕸️ Memory graph", "🧠 Memory", "🔍 Why this answer", "✅ Actions"])
    with tab_graph:
        graph, count = graph_of(cid, version)
        if graph:
            st.html('<div class="kv-legend">' + "".join(
                f'<span><i style="background:{COLORS[k]}"></i>{v}</span>' for k, v in LEGEND) + "</div>")
            components.html(graph, height=575, scrolling=False)
            st.caption(f"{count} nodes around {first}: complaints, clues, other customers who reported the same "
                       "clues, reported payments and where the money went. Drag to explore, scroll to zoom.")
        else:
            st.html('<div class="kv-empty"><div>🕸️</div>No graph yet for this customer.</div>')
    with tab_memory:
        memory_view(mem, memory_on)
    with tab_why:
        why_view(last)
    with tab_actions:
        actions_view(last, mem)
