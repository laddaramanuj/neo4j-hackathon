# Builds the ground-truth scenario that every data-generation agent works from:
# the bank, the demo customer (Anita Deshpande), four fraud rings with their
# scammer contacts, mule accounts, victims and fraudulent payments, and the
# pool of ordinary complainants. Seeded, so re-running gives the same world.
# This is the answer key - the Kavach app never reads it.
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

rng = random.Random(20260926)
OUT = Path(__file__).with_name("scenario.json")
TODAY = datetime(2026, 9, 26)
WINDOW_START = TODAY - timedelta(days=90)
LATEST_EVENT = TODAY + timedelta(hours=11)  # nothing in the data is later than 11:00 on demo day

FIRST_F = ["Anita", "Priya", "Sneha", "Kavita", "Sunita", "Meena", "Pooja", "Neha", "Rekha", "Asha",
           "Shalini", "Deepa", "Swati", "Anjali", "Madhuri", "Vandana", "Nisha", "Jyoti", "Lata", "Rohini",
           "Sarita", "Geeta", "Manisha", "Aarti", "Smita", "Radha", "Usha", "Bhavana", "Tejaswini", "Farah",
           "Zoya", "Sana", "Gurpreet", "Harleen", "Lakshmi", "Divya", "Keerthi", "Ananya", "Ishita", "Mrunal"]
FIRST_M = ["Rajesh", "Suresh", "Amit", "Vikram", "Sanjay", "Rahul", "Anil", "Prakash", "Nitin", "Deepak",
           "Ramesh", "Mahesh", "Sachin", "Ajay", "Vijay", "Manoj", "Arun", "Sunil", "Ashok", "Ganesh",
           "Omkar", "Rohit", "Aniket", "Harish", "Yogesh", "Pranav", "Siddharth", "Kunal", "Tushar", "Imran",
           "Faisal", "Gurdeep", "Harpreet", "Karthik", "Srinivas", "Venkat", "Joseph", "Anthony", "Aditya", "Chinmay"]
LAST = ["Deshpande", "Kulkarni", "Patil", "Joshi", "Sharma", "Gupta", "Verma", "Iyer", "Nair", "Reddy",
        "Rao", "Shinde", "Pawar", "Jadhav", "More", "Gaikwad", "Bhosale", "Chavan", "Kale", "Mehta",
        "Shah", "Agarwal", "Mishra", "Pandey", "Singh", "Yadav", "Das", "Banerjee", "Menon", "Pillai",
        "Naidu", "Choudhary", "Thakur", "Saxena", "Bhatt", "Desai", "Kamat", "Naik", "Salunkhe", "Khan"]

CITIES = [  # city, state, pincode prefix, languages customers there write in
    ("Pune", "Maharashtra", "411", ["mr", "hinglish", "en", "hi"]),
    ("Mumbai", "Maharashtra", "400", ["hinglish", "en", "mr", "hi"]),
    ("Thane", "Maharashtra", "400", ["mr", "hinglish", "en"]),
    ("Nashik", "Maharashtra", "422", ["mr", "hi"]),
    ("Nagpur", "Maharashtra", "440", ["mr", "hi", "en"]),
    ("Bengaluru", "Karnataka", "560", ["en", "hinglish"]),
    ("Hyderabad", "Telangana", "500", ["en", "hinglish"]),
    ("Delhi", "Delhi", "110", ["hi", "hinglish", "en"]),
    ("Jaipur", "Rajasthan", "302", ["hi", "hinglish"]),
    ("Lucknow", "Uttar Pradesh", "226", ["hi", "hinglish"]),
    ("Indore", "Madhya Pradesh", "452", ["hi", "hinglish"]),
    ("Ahmedabad", "Gujarat", "380", ["en", "hinglish"]),
]
CITY_WEIGHTS = [30, 16, 7, 6, 6, 8, 6, 7, 3, 3, 4, 4]

FAKE_BANKS = [  # counterparty banks - all fictional
    ("Konkan Mercantile Bank", "KMBL", "konkanpay"),
    ("Indus Valley Bank", "IVBK", "ivbupi"),
    ("Ganga Gramin Bank", "GGBN", "gangaupi"),
    ("Western Ghats Co-operative Bank", "WGCB", "wgcbupi"),
    ("Narmada Small Finance Bank", "NSFB", "narmadapay"),
]
EXIT_CITIES = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Kolkata", "Ahmedabad"]
COMPLAINT_CHANNELS = ["app_chat", "email", "phone_call", "branch_visit", "social_media_dm"]

_customer_ids = [f"C{n:06d}" for n in range(1, 2001)]
rng.shuffle(_customer_ids)
_used = set()


def unique(make):
    while True:
        value = make()
        if value not in _used:
            _used.add(value)
            return value


def digits(k):
    return "".join(str(rng.randint(0, 9)) for _ in range(k))


def phone():
    """+91 and a 10-digit number starting with 5: not a valid Indian mobile
    range, so no real person's number can appear anywhere in the data."""
    n = unique(lambda: "5" + digits(9))
    return f"+91 {n[:5]} {n[5:]}"


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S+05:30")


def at(day, h_from, h_to):
    return day.replace(hour=rng.randint(h_from, h_to - 1), minute=rng.randint(0, 59), second=rng.randint(0, 59))


def random_day(start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def segment_for(age):
    if age >= 60:
        return "senior_citizen"
    if age < 25:
        return rng.choice(["student", "salaried"])
    return rng.choices(["salaried", "self_employed", "homemaker", "business"], [55, 20, 15, 10])[0]


def make_customer(gender=None, age=None, city=None, language=None, age_range=(21, 78)):
    gender = gender or rng.choice("FM")
    first = rng.choice(FIRST_F if gender == "F" else FIRST_M)
    last = rng.choice(LAST)
    city = city or rng.choices(CITIES, CITY_WEIGHTS)[0]
    age = age or rng.randint(*age_range)
    handle = f"{first.lower()}.{last.lower()[:5]}{rng.randint(10, 99)}"
    lang = language or rng.choice(city[3])
    return {
        "customer_id": _customer_ids.pop(),
        "full_name": f"{first} {last}",
        "gender": gender,
        "age": age,
        "dob": (TODAY - timedelta(days=age * 365 + rng.randint(0, 364))).date().isoformat(),
        "city": city[0],
        "state": city[1],
        "pincode": city[2] + f"{rng.randint(1, 999):03d}",
        "phone": phone(),
        "email": f"{handle}@example.com",
        "preferred_language": lang,
        "writes_in": lang,
        "segment": segment_for(age),
        "customer_since": (TODAY - timedelta(days=rng.randint(200, 15 * 365))).date().isoformat(),
        "account_number": unique(lambda: "6021" + digits(10)),
        "account_type": "SENIOR_SAVINGS" if age >= 60 else rng.choices(["SAVINGS", "SALARY", "CURRENT"], [60, 32, 8])[0],
        "upi_id": f"{handle}@sahyadri",
        "debit_card_last4": digits(4),
    }


def make_mule(holder, kind):
    bank, code, psp = rng.choice(FAKE_BANKS)
    slug = "".join(ch for ch in holder.lower() if ch.isalnum())[:14]
    return {
        "ext_id": unique(lambda: f"EXT{rng.randint(10000, 99999)}"),
        "holder_name": holder,
        "holder_type": kind,
        "bank": bank,
        "ifsc": f"{code}0{digits(6)}",
        "account_number": digits(rng.choice([12, 13, 15])),
        "upi_id": f"{slug}{rng.randint(10, 9999)}@{psp}",
        "account_opened_on": (TODAY - timedelta(days=rng.randint(25, 140))).date().isoformat(),
    }


def payment(victim, mule, t, amount, remark):
    return {
        "txn_id": unique(lambda: "TXN" + digits(12)),
        "utr": unique(lambda: str(rng.randint(10**11, 10**12 - 1))),
        "ts": iso(t),
        "amount_inr": amount,
        "channel": "UPI",
        "from_customer_id": victim["customer_id"],
        "from_account": victim["account_number"],
        "from_upi": victim["upi_id"],
        "to_ext_id": mule["ext_id"],
        "to_upi": mule["upi_id"],
        "to_holder_name": mule["holder_name"],
        "upi_remark": remark,
    }


def build_victims(n, day_from, day_to, amounts_menu, k_range, mules, weights, age_range, remarks,
                  contacts, apps, upi_recall=0.5, spread_days=False):
    victims = []
    for _ in range(n):
        v = make_customer(age_range=age_range)
        day = random_day(day_from, day_to)
        k = rng.randint(*k_range)
        amounts = sorted(rng.sample(amounts_menu, k)) if spread_days else [rng.choice(amounts_menu) for _ in range(k)]
        t = at(day, 10, 18)
        pays = []
        for amount in amounts:
            pays.append(payment(v, rng.choices(mules, weights)[0], t, amount, rng.choice(remarks)))
            t += timedelta(days=1, minutes=rng.randint(-180, 180)) if spread_days else timedelta(minutes=rng.randint(2, 20))
        last = datetime.fromisoformat(pays[-1]["ts"][:19])
        complaint_t = min(last + timedelta(hours=rng.randint(1, 40)), LATEST_EVENT - timedelta(minutes=rng.randint(20, 300)))
        recalls = {
            "scammer_contact": rng.choice(contacts) if rng.random() < 0.75 else None,
            "beneficiary_upi": pays[0]["to_upi"] if rng.random() < upi_recall else None,
            "app_or_channel": rng.choice(apps) if rng.random() < 0.8 else None,
        }
        if not recalls["scammer_contact"] and not recalls["beneficiary_upi"]:
            recalls["beneficiary_upi"] = pays[0]["to_upi"]
        victims.append({
            "customer": v,
            "incident_date": day.date().isoformat(),
            "fraud_payments": pays,
            "total_lost_inr": sum(amounts),
            "has_complained": True,
            "first_complaint_ts": iso(complaint_t),
            "first_complaint_channel": rng.choice(COMPLAINT_CHANNELS),
            "sends_follow_up": rng.random() < 0.5,
            "recalls_in_complaint": recalls,
        })
    return victims


def build_near_miss(n, day_from, day_to, contacts, age_range):
    return [{
        "customer": make_customer(age_range=age_range),
        "report_ts": iso(at(random_day(day_from, day_to), 9, 20)),
        "channel": rng.choice(["app_chat", "email", "phone_call", "social_media_dm"]),
        "reports_contact": rng.choice(contacts),
        "lost_money": False,
    } for _ in range(n)]


def follow_money(payments, next_hops):
    """Victim money pools at the first mule, is forwarded in chunks to the next
    mule a few hours later, and is cashed out at the end of the chain."""
    pools = {}
    for p in payments:
        t = datetime.fromisoformat(p["ts"][:19])
        pool = pools.setdefault((p["to_ext_id"], t.date()), [0, t])
        pool[0] += p["amount_inr"]
        pool[1] = max(pool[1], t)
    frontier = [(ext, total, t) for (ext, _), (total, t) in pools.items()]
    transfers, exits = [], []
    while frontier:
        ext, amount, t = frontier.pop()
        hops = next_hops.get(ext, [])
        if not hops:
            exits.append({
                "from_ext_id": ext,
                "exit_type": rng.choice(["ATM_CASH_WITHDRAWAL", "CRYPTO_EXCHANGE_TRANSFER", "CARDLESS_CASH_WITHDRAWAL"]),
                "ts": iso(min(t + timedelta(hours=rng.randint(10, 30)), LATEST_EVENT)),
                "amount_inr": round(amount * rng.uniform(0.92, 0.99)),
                "city": rng.choice(EXIT_CITIES),
            })
            continue
        send_t = min(t + timedelta(hours=rng.randint(1, 5), minutes=rng.randint(0, 59)), LATEST_EVENT)
        targets = rng.sample(hops, k=min(len(hops), rng.randint(1, 2)))
        share = round(amount * rng.uniform(0.86, 0.95)) // len(targets)
        for target in targets:
            transfers.append({"from_ext_id": ext, "to_ext_id": target, "ts": iso(send_t),
                              "amount_inr": share, "channel": rng.choice(["IMPS", "UPI", "NEFT"])})
            frontier.append((target, share, send_t))
    return transfers, exits


# --- The demo customer ----------------------------------------------------
anita = make_customer(gender="F", age=61, city=CITIES[0], language="hi")
anita.update({"full_name": "Anita Deshpande", "email": "anita.deshpande61@example.com",
              "upi_id": "anita.desh61@sahyadri", "writes_in": "hinglish", "pincode": "411038"})

# --- Ring R1: fake KYC call + remote-access app ------------------------------
r1_mules = [make_mule("R K Fashions", "proprietorship"), make_mule("Shree Sai Traders", "proprietorship"),
            make_mule("Pankaj Tiwari", "individual")]
r1_contacts = [
    {"type": "phone", "value": phone(), "persona": "Vikas Sharma, 'KYC Verification Cell, Sahyadri Bank Head Office'"},
    {"type": "phone", "value": phone(), "persona": "Neha Kapoor, 'Video KYC team'"},
]
r1_sms = {"type": "sms_sender_id", "value": "VK-SHYKYC",
          "sample_text": ("Dear Customer, your Sahyadri Bank KYC has EXPIRED today & a/c will be BLOCKED within 24 hrs. "
                          f"Update immediately, call KYC officer {r1_contacts[0]['value']}")}
r1_victims = build_victims(7, TODAY - timedelta(days=13), TODAY - timedelta(days=1),
                           [9999, 14999, 19500, 24000, 25000, 30000, 35000, 49999], (1, 3), r1_mules[:2], [80, 20],
                           (45, 76), ["KYC verification", "", "kyc update", "video kyc", "verification"],
                           [c["value"] for c in r1_contacts], ["AnyDesk"])
anita_payments = [
    payment(anita, r1_mules[0], TODAY.replace(hour=10, minute=47, second=13), 25000, "KYC verification"),
    payment(anita, r1_mules[0], TODAY.replace(hour=10, minute=52, second=40), 15000, "KYC verification"),
]
r1_near_miss = build_near_miss(4, TODAY - timedelta(days=12), TODAY - timedelta(days=1),
                               [c["value"] for c in r1_contacts], (40, 80))

# --- Ring R2: electricity-disconnection SMS ----------------------------------
r2_mules = [make_mule("Maa Bhavani Mobile Point", "proprietorship"), make_mule("Sandeep Rathod", "individual")]
r2_contacts = [
    {"type": "phone", "value": phone(), "persona": "'Electricity officer Rakesh Patil, billing department'"},
    {"type": "phone", "value": phone(), "persona": "'Lineman supervisor' who calls back victims who hesitate"},
]
r2_sms = {"type": "sms_body",
          "sample_text": ("Dear Consumer, your electricity power will be disconnected tonight at 9:30 PM because your "
                          "previous month bill was not updated. Please immediately contact our electricity officer "
                          f"{r2_contacts[0]['value']}. Thank you")}
r2_victims = build_victims(6, TODAY - timedelta(days=24), TODAY - timedelta(days=3),
                           [4999, 10000, 12500, 18000, 25000, 40000], (1, 3), r2_mules, [75, 25], (35, 72),
                           ["bill update", "electricity bill", "", "power bill"], [c["value"] for c in r2_contacts],
                           ["TeamViewer QuickSupport", "a 'Bill Update' APK file sent on WhatsApp"])
r2_near_miss = build_near_miss(3, TODAY - timedelta(days=24), TODAY - timedelta(days=2),
                               [c["value"] for c in r2_contacts], (30, 75))

# --- Ring R3: fake customer-care number + UPI collect request ----------------
r3_mules = [make_mule("QC Refund Helpdesk", "proprietorship"), make_mule("Arvind Solanki", "individual")]
r3_contacts = [
    {"type": "phone", "value": phone(), "persona": "fake 'QuickCart customer care' number shown on a search-results page"},
    {"type": "phone", "value": phone(), "persona": "fake 'FoodDash refund desk' number from a social-media ad"},
]
r3_victims = build_victims(5, TODAY - timedelta(days=30), TODAY - timedelta(days=2),
                           [1999, 2999, 4999, 7499, 9998, 14999, 24999], (1, 4), r3_mules, [85, 15], (22, 65),
                           ["refund", "refund process", "QuickCart refund", ""], [c["value"] for c in r3_contacts],
                           ["UPI collect request", "QR code sent on WhatsApp"], upi_recall=0.7)
r3_near_miss = build_near_miss(2, TODAY - timedelta(days=28), TODAY - timedelta(days=2),
                               [c["value"] for c in r3_contacts], (22, 65))

# --- Ring R4: part-time 'task' job scam; its money ends up at R1's mule ------
r4_mules = [make_mule("Shiv Shakti Enterprises", "proprietorship"), make_mule("Global Digital Services", "proprietorship")]
r4_contacts = [
    {"type": "telegram", "value": "@hr_riya_tasks", "persona": "'HR Riya', admin of the 'Daily Earn 5000' Telegram group"},
    {"type": "phone", "value": phone(), "persona": "WhatsApp number that sends the first 'like videos, earn Rs 150 per task' message"},
]
r4_victims = build_victims(6, TODAY - timedelta(days=20), TODAY - timedelta(days=8),
                           [1000, 3000, 8000, 15000, 25000, 40000], (2, 5), r4_mules, [60, 40], (20, 36),
                           ["task deposit", "prepaid task", "merchant task", "vip task"],
                           [c["value"] for c in r4_contacts], ["Telegram", "WhatsApp"], upi_recall=0.6, spread_days=True)
r4_near_miss = build_near_miss(3, TODAY - timedelta(days=20), TODAY - timedelta(days=2),
                               [c["value"] for c in r4_contacts], (19, 35))

# --- Money flow between mules (the bank sees this via fraud-intel feeds) -----
M = {m["ext_id"]: m for m in r1_mules + r2_mules + r3_mules + r4_mules}
next_hops = {
    r1_mules[0]["ext_id"]: [r1_mules[1]["ext_id"], r1_mules[2]["ext_id"]],
    r2_mules[0]["ext_id"]: [r2_mules[1]["ext_id"]],
    r3_mules[0]["ext_id"]: [r3_mules[1]["ext_id"]],
    r4_mules[0]["ext_id"]: [r4_mules[1]["ext_id"]],
    r4_mules[1]["ext_id"]: [r1_mules[0]["ext_id"]],  # R4 and R1 are one gang: task money lands at R K Fashions
}


def ring(ring_id, modus, script, contacts, extra, tools, mules, victims, near_miss, include_anita=False):
    payments = [p for v in victims for p in v["fraud_payments"]] + (anita_payments if include_anita else [])
    transfers, exits = follow_money(payments, next_hops)
    return {
        "ring_id": ring_id,
        "modus_operandi": modus,
        "scam_script": script,
        "scammer_contacts": contacts + ([extra] if extra else []),
        "tools_used": tools,
        "mule_accounts": mules,
        "victims": victims,
        "near_miss_reporters": near_miss,
        "mule_transfers": transfers,
        "cash_out_events": exits,
    }


rings = [
    ring("R1", "Fake KYC-expiry call + remote-access app",
         "An SMS says the Sahyadri Bank KYC has expired and the account will be blocked; the caller poses as the bank's "
         "KYC cell, asks the customer to install AnyDesk 'for video KYC', then moves money over UPI while screen-sharing, "
         "sometimes asking for the OTP 'to confirm KYC'.",
         r1_contacts, r1_sms, ["AnyDesk"], r1_mules, r1_victims, r1_near_miss, include_anita=True),
    ring("R2", "Electricity-disconnection SMS",
         "An SMS threatens power disconnection tonight over an 'unpaid bill'; the 'electricity officer' has the victim "
         "install TeamViewer QuickSupport or a 'Bill Update' APK and pay a small 'update fee', then drains the account.",
         r2_contacts, r2_sms, ["TeamViewer QuickSupport", "Bill Update APK"], r2_mules, r2_victims, r2_near_miss),
    ring("R3", "Fake customer-care number + UPI collect request",
         "The victim searches online for QuickCart or FoodDash customer care to get a refund, reaches a fake helpline, "
         "and is told to approve a UPI collect request or scan a QR code 'to receive the refund' - entering the UPI PIN "
         "sends money instead.",
         r3_contacts, None, ["UPI collect request", "QR code"], r3_mules, r3_victims, r3_near_miss),
    ring("R4", "Part-time 'task' job scam on Telegram/WhatsApp",
         "A WhatsApp message offers Rs 150 per 'like the video' task; the victim joins a Telegram group, gets small "
         "payouts at first, then is asked to pay escalating 'prepaid task' deposits that are never returned.",
         r4_contacts, None, ["Telegram", "WhatsApp"], r4_mules, r4_victims, r4_near_miss),
]

# --- Ordinary complainants (noise the agent must not confuse with fraud) ----
GENERAL = [("failed_upi_debited_not_credited", 14), ("atm_cash_not_dispensed", 9), ("card_declined", 6),
           ("unrecognised_charges_fees", 8), ("netbanking_locked_password_reset", 7), ("kyc_update_request", 6),
           ("emi_debited_twice", 4), ("credit_card_billing_dispute", 5), ("lost_or_stolen_card", 5),
           ("upi_pin_reset_issue", 5), ("neft_imps_delay", 5), ("debit_card_not_received", 4),
           ("sms_alerts_not_received", 3), ("cheque_bounce_charges", 3), ("fd_interest_query", 3),
           ("merchant_refund_not_received", 3)]
general = []
for category, n in GENERAL:
    for _ in range(n):
        c = make_customer()
        general.append({"customer": c, "category": category,
                        "incident_date": random_day(WINDOW_START, TODAY - timedelta(days=1)).date().isoformat(),
                        "channel": rng.choice(COMPLAINT_CHANNELS)})
rng.shuffle(general)
for i, g in enumerate(general):
    g["group"] = "G1" if i % 2 == 0 else "G2"

special_customers = ([anita] + [v["customer"] for r in rings for v in r["victims"]]
                     + [m["customer"] for r in rings for m in r["near_miss_reporters"]]
                     + [g["customer"] for g in general])

scenario = {
    "about": ("Ground truth for the Kavach dataset. Sahyadri Bank is fictional. Ring ids, the words 'mule', "
              "'victim' and 'ring', and any label from this file must NEVER be copied into the generated data."),
    "today": TODAY.date().isoformat(),
    "latest_allowed_timestamp": iso(LATEST_EVENT),
    "data_window": {"start": WINDOW_START.date().isoformat(), "end": TODAY.date().isoformat()},
    "bank": {
        "name": "Sahyadri Bank", "headquarters": "Pune, Maharashtra",
        "ifsc_prefix": "SAHY0", "upi_suffix": "@sahyadri",
        "customer_care": "1800 5000 111 (toll-free, fictional)", "email_domain": "sahyadribank.example.in",
        "branches": ["Kothrud", "Baner", "Aundh", "Shivajinagar", "Hadapsar", "Viman Nagar", "Pimpri", "Andheri East",
                     "Thane West", "Nashik Road", "Dharampeth Nagpur", "Koramangala", "Banjara Hills", "Connaught Place",
                     "Malviya Nagar Jaipur", "Hazratganj", "Vijay Nagar Indore", "Navrangpura"],
    },
    "bank_policy_facts": {
        "card_hotlisting": "immediately on request, via app, IVR or agent",
        "dispute_id_format": "DSP-2026-##### (5 digits)",
        "shadow_credit_or_decision_tat": "10 working days from the complaint for reported unauthorised electronic transactions",
        "zero_liability_window": "customer reports within 3 working days of being informed of the transaction (fraud not due to customer negligence)",
        "limited_liability_window": "4 to 7 working days - liability capped as per the bank's board-approved policy",
        "cyber_helpline": "1930 (national cyber-crime helpline) and cybercrime.gov.in",
        "beneficiary_lien": "bank requests a lien/freeze on the beneficiary account via the beneficiary's bank",
        "senior_citizen_priority": "callback within 4 working hours; case handled by the senior-citizen desk",
        "failed_upi_auto_reversal": "T+1 working day; compensation of Rs 100 per day of delay beyond that",
        "atm_cash_not_dispensed": "auto-reversal within 5 working days; Rs 100 per day compensation beyond that",
    },
    "demo_customer": {
        "customer": anita,
        "story": ("61-year-old retired teacher in Kothrud, Pune. Writes in Hinglish, prefers replies in Hindi. On demo day "
                  "she reports the R1 scam LIVE - her fraud complaint must NOT exist in the data. Her two fraudulent "
                  "UPI payments this morning DO exist in the transaction records."),
        "prior_interactions": [{
            "ts": iso((TODAY - timedelta(days=6)).replace(hour=11, minute=5, second=22)),
            "channel": "app_chat",
            "summary": ("Forwarded the 'KYC EXPIRED' SMS from sender VK-SHYKYC and asked if it was genuine. The agent said "
                        "the bank never asks for KYC through SMS links or phone calls and told her not to call the number. "
                        "No case opened; chat closed as 'Query - resolved'."),
            "forwarded_sms_text": r1_sms["sample_text"],
        }],
        "fraud_payments_today": anita_payments,
        "fraud_session_today": {"start": iso(TODAY.replace(hour=10, minute=38, second=5)),
                                "remote_access_app_detected": "AnyDesk", "device": "her usual phone"},
        "belongs_to_ring": "R1",
    },
    "fraud_rings": rings,
    "general_complainants": general,
    "special_customers": special_customers,
    "counts": {
        "special_customers": len(special_customers),
        "ring_victims_incl_anita": sum(len(r["victims"]) for r in rings) + 1,
        "near_miss_reporters": sum(len(r["near_miss_reporters"]) for r in rings),
        "general_complainants": len(general),
        "fraud_payments_incl_anita": sum(len(v["fraud_payments"]) for r in rings for v in r["victims"]) + len(anita_payments),
        "mule_transfers": sum(len(r["mule_transfers"]) for r in rings),
    },
}

OUT.write_text(json.dumps(scenario, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(scenario["counts"], indent=2))
print("wrote", OUT)
