# Draws the one-slide architecture diagram (docs/architecture.png) with Pillow.
# Run: .venv\Scripts\python.exe docs\make_architecture.py
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 820
OUT = Path(__file__).with_name("architecture.png")
FONTS = Path("C:/Windows/Fonts")

INK = "#14213d"
MUTED = "#4a5568"
NEO4J = "#018bff"
NEO4J_FILL = "#e8f3ff"
BOX_FILL = "#f7f9fc"
LINE = "#9aa9bf"
ACCENT = "#0f9d58"


def font(name, size):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.truetype(str(FONTS / "arial.ttf"), size)


TITLE, SUB, HEAD, BODY, SMALL = (font("segoeuib.ttf", 40), font("segoeui.ttf", 22), font("segoeuib.ttf", 22),
                                 font("segoeui.ttf", 18), font("segoeui.ttf", 16))

img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)


def box(x1, y1, x2, y2, title, lines, fill=BOX_FILL, outline=LINE, title_color=INK, width=2):
    d.rounded_rectangle((x1, y1, x2, y2), radius=14, fill=fill, outline=outline, width=width)
    d.text((x1 + 18, y1 + 14), title, font=HEAD, fill=title_color)
    y = y1 + 50
    for line in lines:
        d.text((x1 + 18, y), line, font=BODY, fill=MUTED)
        y += 26


def arrow(x1, y1, x2, y2, label=None, color=INK, label_dy=-28):
    d.line((x1, y1, x2, y2), fill=color, width=3)
    # arrow head pointing from (x1,y1) to (x2,y2)
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    size = 13
    left = (x2 - size * math.cos(ang - 0.45), y2 - size * math.sin(ang - 0.45))
    right = (x2 - size * math.cos(ang + 0.45), y2 - size * math.sin(ang + 0.45))
    d.polygon([(x2, y2), left, right], fill=color)
    if label:
        tx = (x1 + x2) / 2
        ty = (y1 + y2) / 2 + label_dy
        w = d.textlength(label, font=SMALL)
        d.text((tx - w / 2, ty), label, font=SMALL, fill=color)


# Title
d.text((40, 28), "Kavach — Architecture", font=TITLE, fill=INK)
d.text((40, 82), "User → Agent → Memory / Retrieval → Neo4j → Response", font=SUB, fill=NEO4J)

# Main flow row
box(40, 140, 300, 300, "User", ["Customer reporting a scam,", "or a support agent", "helping them"])
box(360, 140, 690, 300, "Streamlit UI", ["Chat + customer picker", "Memory ON / OFF switch", "Live graph (neo4j-viz)", "\"Why I said this\" panel"])
box(750, 140, 1060, 300, "Kavach agent", ["LangChain create_agent", "LLM via OpenRouter", "Memory loaded each turn;", "picks the Neo4j tools"])
box(1120, 140, 1560, 300, "Memory & retrieval tools", ["recall_customer · extract_clues", "save_complaint · find_ring", "search_advisories · take_action"])

arrow(300, 200, 360, 200)
arrow(690, 200, 750, 200)
arrow(1060, 200, 1120, 200)
# Response path back to the user
arrow(1120, 270, 1060, 270, color=ACCENT)
arrow(750, 270, 690, 270, color=ACCENT)
arrow(360, 270, 300, 270, color=ACCENT)
d.text((40, 312), "Green arrows: the response path - contextual reply + actions taken (card block, dispute, refund promise)",
       font=SMALL, fill=ACCENT)

# Neo4j graph
d.rounded_rectangle((540, 400, 1560, 740), radius=18, fill=NEO4J_FILL, outline=NEO4J, width=3)
d.text((562, 414), "Neo4j AuraDB — one graph", font=HEAD, fill=NEO4J)
box(562, 460, 880, 720, "Bank data (structured)", ["Customer · Account · Card", "Device · LoginSession", "Transaction · Merchant", "Counterparty accounts", "Fraud-intel transfers", "between accounts"],
    fill="white", outline=NEO4J)
box(900, 460, 1220, 720, "Text → graph", ["Complaint · CallTranscript", "AgentNote · KbChunk", "(vector indexes,", " 1024-d embeddings)", "—MENTIONS→ Clue", "(phone · UPI ID · app)"],
    fill="white", outline=NEO4J)
box(1240, 460, 1540, 720, "Agent memory", ["Interaction", "Promise (refund due)", "Preference (language)", "—USED→ the nodes", "each answer relied on"],
    fill="white", outline=NEO4J)

# Tools <-> Neo4j
arrow(1340, 300, 1340, 400, None, color=NEO4J)
d.text((1352, 318), "Cypher traversals", font=SMALL, fill=NEO4J)
d.text((1352, 340), "APOC money-trail paths", font=SMALL, fill=NEO4J)
d.text((1352, 362), "vector search (neo4j-graphrag)", font=SMALL, fill=NEO4J)

# Data pipeline
box(40, 400, 480, 690, "Data pipeline (load_graph.py)", ["Structured: customers, accounts, cards,", "  devices, logins, ~35k transactions", "Unstructured: complaints, call transcripts,", "  agent notes, bank knowledge base", "→ clue extraction (patterns + LLM)", "→ Gemini embeddings (1024-d)", "→ MERGE into Neo4j"])
arrow(480, 545, 540, 545, None, color=NEO4J)

d.text((40, 720), "Result: the agent remembers each victim and", font=BODY, fill=INK)
d.text((40, 746), "connects complaints that share a caller, UPI ID", font=BODY, fill=INK)
d.text((40, 772), "or money trail — exposing the whole scam ring.", font=BODY, fill=INK)

img.save(OUT)
print("wrote", OUT)
