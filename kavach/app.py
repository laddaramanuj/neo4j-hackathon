# Kavach web app: chat with the agent as a chosen customer, switch memory on or
# off, and see the part of the Neo4j graph each answer came from.
# Run: .venv\Scripts\python.exe -m streamlit run app.py
import streamlit as st
import streamlit.components.v1 as components
from neo4j import Result

st.set_page_config(page_title="Kavach", page_icon="🛡️", layout="wide")

from agent import demo_customers, handle_turn, reset_customer  # noqa: E402
from common import DATABASE, driver  # noqa: E402

COLORS = {"Customer": "#018BFF", "Complaint": "#F79767", "Clue": "#E0115F", "Transaction": "#8DCC93",
          "Account": "#4C8EDA", "Counterparty": "#C990C0", "CashOutPoint": "#6A0DAD", "Promise": "#FFC454",
          "Preference": "#57C7E3", "Card": "#A5ABB6"}

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


@st.cache_data(ttl=600)
def customers():
    return demo_customers()


if "chats" not in st.session_state:
    st.session_state.chats, st.session_state.traces = {}, {}

with st.sidebar:
    st.title("🛡️ Kavach")
    st.caption("A bank support agent that remembers victims and uncovers scam rings. Memory lives in Neo4j.")
    options = customers()
    names = {c["id"]: f"{c['name']} · {c['city']}" for c in options}
    ids = list(names)
    cid = st.selectbox("Talking as customer", ids, format_func=names.get,
                       index=ids.index("C000150") if "C000150" in ids else 0)
    memory_on = st.toggle("Memory ON", value=True, help="OFF = the same LLM with no Neo4j memory or lookups")
    if st.button("New conversation", use_container_width=True):
        st.session_state.chats[cid] = []
    if st.button("Reset demo for this customer", use_container_width=True):
        reset_customer(cid)
        st.session_state.chats[cid] = []
        st.session_state.traces.pop(cid, None)
    st.divider()
    st.caption("Sahyadri Bank and all data are fictional.")

chat = st.session_state.chats.setdefault(cid, [])
chat_col, info_col = st.columns([1, 1.05], gap="large")

with chat_col:
    st.subheader(f"Chat · {names.get(cid, cid)}")
    st.caption("🟢 Memory ON — Kavach reads and writes Neo4j" if memory_on else "⚪ Memory OFF — no history, no graph")
    history = st.container()  # messages render above the input box
    prompt = st.chat_input("Type as the customer…")
    with history:
        for m in chat:
            with st.chat_message(m["role"], avatar="🛡️" if m["role"] == "assistant" else "🙂"):
                st.markdown(m["content"])
        if prompt:
            chat.append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar="🙂"):
                st.markdown(prompt)
            with st.chat_message("assistant", avatar="🛡️"):
                with st.spinner("Checking memory and the graph…"):
                    result = handle_turn(cid, prompt, memory_on)
                st.markdown(result["reply"])
            chat.append({"role": "assistant", "content": result["reply"]})
            st.session_state.traces[cid] = result

with info_col:
    tab_graph, tab_why, tab_actions = st.tabs(["🕸️ Memory graph", "🧠 Why Kavach said this", "✅ Actions"])
    with tab_graph:
        html, count = graph_html(cid)
        if html:
            st.caption(f"{count} nodes around this customer: complaints, clues, other customers who reported the "
                       "same clues, reported payments and where the money went.")
            components.html(html, height=580, scrolling=False)
        else:
            st.info("No graph yet for this customer.")
    last = st.session_state.traces.get(cid)
    with tab_why:
        if not last:
            st.info("Send a message to see which memories and graph lookups Kavach used.")
        for step in (last or {}).get("trace", []):
            with st.expander(f"🔧 {step['tool']}", expanded=step["tool"] in ("find_ring", "open_fraud_case")):
                st.json(step.get("result", step.get("note")))
    with tab_actions:
        actions = (last or {}).get("actions")
        if actions:
            st.success(f"Complaint {actions['complaint_id']} · {actions['status']}")
            st.write(f"**Dispute:** {actions['dispute_id']}")
            st.write(f"**Refund decision due:** {actions['refund_decision_due']}")
            st.write(f"**Cards hotlisted:** {', '.join(actions['cards_hotlisted']) or 'none active'}")
            st.write(f"**Beneficiary lien requested:** {', '.join(actions['beneficiary_lien_requested_for']) or '-'}")
        else:
            st.info("Actions Kavach takes (card block, dispute, refund promise) appear here.")
