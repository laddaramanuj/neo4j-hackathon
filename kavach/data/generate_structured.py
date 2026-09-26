#!/usr/bin/env python
"""Structured core-banking export for the fictional Sahyadri Bank (Kavach dataset).

Reads data/_spec/scenario.json (the ground truth) and writes CSVs plus a README
data dictionary to data/structured/.  Standard library only, seeded, deterministic:

    python data/generate_structured.py
"""
import csv
import json
import math
import os
import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "_spec", "scenario.json")
OUT = os.path.join(HERE, "structured")
IST = timezone(timedelta(hours=5, minutes=30))
rng = random.Random(20260926)

RAW = open(SPEC, encoding="utf-8").read()
S = json.loads(RAW)
LATEST = datetime.fromisoformat(S["latest_allowed_timestamp"])
TODAY = date.fromisoformat(S["today"])
W0 = date.fromisoformat(S["data_window"]["start"])
W1 = date.fromisoformat(S["data_window"]["end"])
DAYS = [W0 + timedelta(days=i) for i in range((W1 - W0).days + 1)]
W0_DT = datetime(W0.year, W0.month, W0.day, tzinfo=IST)

# tuning knobs
N_CUSTOMERS = 2000
P_SECOND_ACCT = 0.15
P_UPI_VIA_APP = 0.17      # share of app users who pay UPI from the Sahyadri app (rest use 3rd-party UPI apps)
P_BBPS_VIA_APP = 0.30
BROWSE_MEAN = 0.35
DISC_SCALE = 0.52

# ----------------------------------------------------------------------------- helpers
USED = set(re.findall(r"\+91 5\d{4} \d{5}", RAW))


def _walk(o):
    if isinstance(o, dict):
        for v in o.values():
            _walk(v)
    elif isinstance(o, list):
        for v in o:
            _walk(v)
    elif isinstance(o, str):
        USED.add(o)


_walk(S)  # every id / number / upi / email in the answer key is reserved


def digits(k):
    return "".join(str(rng.randint(0, 9)) for _ in range(k))


def uniq(make):
    while True:
        v = make()
        if v and v not in USED:
            USED.add(v)
            return v


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S+05:30")


def at(d, h0, h1):
    t = datetime(d.year, d.month, d.day, tzinfo=IST) + timedelta(seconds=rng.randint(int(h0 * 3600), int(h1 * 3600) - 1))
    if t > LATEST:
        t = LATEST - timedelta(seconds=rng.randint(600, 4 * 3600))
    return t


def rand_date(lo, hi):
    if hi <= lo:
        return lo
    return lo + timedelta(days=rng.randint(0, (hi - lo).days))


def poisson(lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < L:
            return k
        k += 1


def pick(pairs):
    items, w = zip(*pairs)
    return rng.choices(items, w)[0]


def fmt_amt(x):
    x = round(float(x), 2)
    return str(int(x)) if abs(x - round(x)) < 1e-9 else f"{x:.2f}"


def monthly(dom_lo, dom_hi=None, months=(6, 7, 8, 9)):
    out = []
    for m in months:
        dd = rng.randint(dom_lo, dom_hi if dom_hi else dom_lo)
        dd = min(dd, 30 if m in (6, 9) else 31)
        d = date(2026, m, dd)
        if W0 <= d <= W1:
            out.append(d)
    return out


MON = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# ----------------------------------------------------------------------------- reference lists
FIRST_F = ["Anita", "Priya", "Sneha", "Kavita", "Sunita", "Meena", "Pooja", "Neha", "Rekha", "Asha",
           "Shalini", "Deepa", "Swati", "Anjali", "Madhuri", "Vandana", "Nisha", "Jyoti", "Lata", "Rohini",
           "Sarita", "Geeta", "Manisha", "Aarti", "Smita", "Radha", "Usha", "Bhavana", "Tejaswini", "Farah",
           "Zoya", "Sana", "Gurpreet", "Harleen", "Lakshmi", "Divya", "Keerthi", "Ananya", "Ishita", "Mrunal",
           "Shweta", "Pallavi", "Vaishali", "Rupali", "Seema", "Archana", "Nandini", "Revati", "Sayali", "Komal"]
FIRST_M = ["Rajesh", "Suresh", "Amit", "Vikram", "Sanjay", "Rahul", "Anil", "Prakash", "Nitin", "Deepak",
           "Ramesh", "Mahesh", "Sachin", "Ajay", "Vijay", "Manoj", "Arun", "Sunil", "Ashok", "Ganesh",
           "Omkar", "Rohit", "Aniket", "Harish", "Yogesh", "Pranav", "Siddharth", "Kunal", "Tushar", "Imran",
           "Faisal", "Gurdeep", "Harpreet", "Karthik", "Srinivas", "Venkat", "Joseph", "Anthony", "Aditya", "Chinmay",
           "Mangesh", "Sagar", "Abhijit", "Swapnil", "Hemant", "Dinesh", "Girish", "Parag", "Vinayak", "Akshay"]
LAST = ["Deshpande", "Kulkarni", "Patil", "Joshi", "Sharma", "Gupta", "Verma", "Iyer", "Nair", "Reddy",
        "Rao", "Shinde", "Pawar", "Jadhav", "More", "Gaikwad", "Bhosale", "Chavan", "Kale", "Mehta",
        "Shah", "Agarwal", "Mishra", "Pandey", "Singh", "Yadav", "Das", "Banerjee", "Menon", "Pillai",
        "Naidu", "Choudhary", "Thakur", "Saxena", "Bhatt", "Desai", "Kamat", "Naik", "Salunkhe", "Khan",
        "Deshmukh", "Wagh", "Mane", "Sawant", "Apte", "Gokhale", "Kadam", "Dixit", "Tiwari", "Sheikh"]

CITIES = [  # city, state, pincode prefix, languages, weight, branches
    ("Pune", "Maharashtra", "411", ["mr", "hinglish", "en", "hi"], 30,
     ["Kothrud", "Baner", "Aundh", "Shivajinagar", "Hadapsar", "Viman Nagar", "Pimpri"]),
    ("Mumbai", "Maharashtra", "400", ["hinglish", "en", "mr", "hi"], 16, ["Andheri East"]),
    ("Thane", "Maharashtra", "400", ["mr", "hinglish", "en"], 7, ["Thane West"]),
    ("Nashik", "Maharashtra", "422", ["mr", "hi"], 6, ["Nashik Road"]),
    ("Nagpur", "Maharashtra", "440", ["mr", "hi", "en"], 6, ["Dharampeth Nagpur"]),
    ("Bengaluru", "Karnataka", "560", ["en", "hinglish"], 8, ["Koramangala"]),
    ("Hyderabad", "Telangana", "500", ["en", "hinglish"], 6, ["Banjara Hills"]),
    ("Delhi", "Delhi", "110", ["hi", "hinglish", "en"], 7, ["Connaught Place"]),
    ("Jaipur", "Rajasthan", "302", ["hi", "hinglish"], 3, ["Malviya Nagar Jaipur"]),
    ("Lucknow", "Uttar Pradesh", "226", ["hi", "hinglish"], 3, ["Hazratganj"]),
    ("Indore", "Madhya Pradesh", "452", ["hi", "hinglish"], 4, ["Vijay Nagar Indore"]),
    ("Ahmedabad", "Gujarat", "380", ["en", "hinglish"], 4, ["Navrangpura"]),
]
CITY = {c[0]: c for c in CITIES}
BRANCHES = S["bank"]["branches"]
assert sorted(BRANCHES) == sorted(b for c in CITIES for b in c[5]), "branch list mismatch"
_codes = rng.sample(range(1100, 9900), len(BRANCHES))
IFSC = {b: f"{S['bank']['ifsc_prefix']}{_codes[i]:06d}" for i, b in enumerate(BRANCHES)}
BRANCH_CITY = {b: c[0] for c in CITIES for b in c[5]}

FAKE_BANKS = [("Konkan Mercantile Bank", "KMBL", "konkanpay"), ("Indus Valley Bank", "IVBK", "ivbupi"),
              ("Ganga Gramin Bank", "GGBN", "gangaupi"), ("Western Ghats Co-operative Bank", "WGCB", "wgcbupi"),
              ("Narmada Small Finance Bank", "NSFB", "narmadapay")]
PSPS = ["sahyadri", "sahyadri", "sahyadri", "konkanpay", "ivbupi", "gangaupi", "wgcbupi", "narmadapay"]

PHONES = [("Redmi Note 13", "Android 14", 12), ("Redmi Note 12", "Android 13", 8), ("Redmi 13C", "Android 13", 6),
          ("Galaxy M34", "Android 14", 8), ("Galaxy A15", "Android 14", 8), ("Galaxy A54", "Android 14", 4),
          ("Galaxy M14", "Android 13", 4), ("Galaxy S23", "Android 15", 2), ("vivo T3", "Android 14", 6),
          ("vivo Y28", "Android 14", 5), ("iPhone 13", "iOS 17.6", 5), ("iPhone 14", "iOS 18.1", 3),
          ("iPhone 15", "iOS 18.5", 3), ("iPhone 11", "iOS 17.5", 2), ("OnePlus Nord CE4", "Android 14", 6),
          ("OnePlus 11R", "Android 15", 2), ("realme 12 Pro", "Android 14", 5), ("realme narzo 60", "Android 13", 3),
          ("moto g84", "Android 14", 4), ("moto g54", "Android 14", 3), ("OPPO A79", "Android 14", 3),
          ("POCO X6", "Android 14", 3), ("iQOO Z9", "Android 14", 2), ("Nokia G42", "Android 13", 1)]
APP_VERSIONS = [("5.16.1", 40), ("5.15.2", 30), ("5.14.0", 15), ("5.12.3", 10), ("5.9.8", 5)]

# ----------------------------------------------------------------------------- merchants
LOCAL_CATS = {
    "GROCERY": ("5411", "Grocery & Kirana", 7, ["Shree Ganesh Kirana Stores", "Balaji Provision Stores", "Om Sai General Stores",
                "Mahalaxmi Super Mart", "Jai Bhavani Kirana", "Fresh Basket Mart", "Gokul Dairy & Kirana", "Annapurna Supermarket",
                "Laxmi Kirana & General", "Sai Krupa Provision", "New Bharat Kirana", "Swami Samarth Stores", "Royal Fruits & Vegetables",
                "Krishna Dairy Farm", "Janata Kirana Bhandar", "Hari Om Provisions", "Ambika Grocery Centre", "Daily Needs Mart",
                "Patel Provision Stores", "Mauli Kirana"]),
    "PHARMACY": ("5912", "Pharmacy", 3, ["Sanjivani Medical & General", "Shri Datta Medicals", "Apna Chemist", "Care Plus Pharmacy",
                 "Arogya Medicose", "Jeevan Medical Stores", "Wellness Chemist", "Dhanvantari Pharmacy", "Seva Medicals", "Life Line Medicos"]),
    "FUEL": ("5541", "Fuel Station", 2, ["Sai Auto Fuels", "Highway Fuel Station", "Om Fuel Point", "Ganesh Fuel Station",
             "City Fuel Centre", "Janata Fuel Pump", "Sahyog Fuels", "Motorway Fuel Point"]),
    "RESTAURANT": ("5812", "Restaurant", 4, ["Hotel Shreyas Veg", "Annapurna Pure Veg", "Punjabi Tadka Dhaba", "Cafe Monsoon",
                   "Udupi Krishna Bhavan", "Biryani Junction", "Misal Corner", "Chai Tapri Adda", "Spice Route Family Restaurant",
                   "Vada Pav Express", "Hotel Swad Thali", "Momos Hub", "Mumbai Sandwich Corner", "Tandoor Nights"]),
    "EDUCATION": ("8299", "Education", 1, ["Saraswati Vidya Mandir", "Little Stars Play School", "Bright Future Coaching Classes",
                  "Gyan Deep Tutorials", "Excel Academy", "Vidya Coaching Centre"]),
    "GYM": ("7997", "Gym & Fitness", 1, ["FitZone Gym", "Iron Temple Fitness", "Shakti Yoga Studio", "Muscle Factory Gym", "Pulse Fitness Club"]),
    "SALON": ("7230", "Salon & Spa", 1, ["Style Point Unisex Salon", "Glamour Beauty Parlour", "Classic Men's Salon", "Mirror Image Salon", "Radiance Spa"]),
    "APPAREL": ("5651", "Apparel", 1, ["Kalyani Saree Kendra", "Trendz Fashion Hub", "Om Collection", "Fashion Point", "Vastralaya Textiles", "Kids Corner Garments"]),
    "ELECTRONICS": ("5732", "Electronics", 1, ["Digital World Electronics", "Sai Mobile Gallery", "Star Electronics", "Metro Mobiles & Accessories", "Galaxy Computers"]),
    "CLINIC": ("8011", "Healthcare", 1, ["Shree Clinic & Diagnostics", "Aarogya Polyclinic", "City Dental Care", "Sparsh Physiotherapy", "Nirmal Eye Care", "Family Health Clinic"]),
}
NATIONAL = [  # name, mcc, category label, hq city, internal cat
    ("QuickCart", "5399", "E-commerce", "Bengaluru", "ECOM"),
    ("QuickCart Fresh", "5411", "Online Grocery", "Bengaluru", "ECOM_GROCERY"),
    ("FoodDash", "5814", "Food Delivery", "Bengaluru", "FOOD_DELIVERY"),
    ("ShopMitra Online", "5399", "E-commerce", "Mumbai", "ECOM"),
    ("Vastra Online Fashion", "5651", "E-commerce", "Mumbai", "ECOM"),
    ("Rangmanch Cinemas", "7832", "Entertainment", "Mumbai", "MOVIES"),
    ("Safar Tours & Travels", "4722", "Travel", "Pune", "TRAVEL"),
    ("Sahaj Rail & Bus Tickets", "4112", "Travel", "Delhi", "TRAVEL"),
    ("Vayu Mobile Prepaid", "4814", "Telecom - Mobile", "Mumbai", "MOBILE_PRE"),
    ("Tarang Telecom Prepaid", "4814", "Telecom - Mobile", "Delhi", "MOBILE_PRE"),
    ("Vayu Mobile Postpaid", "4814", "Telecom - Mobile", "Mumbai", "MOBILE_POST"),
    ("Tarang Telecom Postpaid", "4814", "Telecom - Mobile", "Delhi", "MOBILE_POST"),
    ("Nexa Fibernet Broadband", "4899", "Telecom - Broadband", "Pune", "BROADBAND"),
    ("Sampark Broadband", "4899", "Telecom - Broadband", "Hyderabad", "BROADBAND"),
    ("Akash DTH Services", "4899", "DTH / Cable", "Mumbai", "DTH"),
    ("Metro Piped Gas Ltd", "4900", "Utility - Gas", "Mumbai", "GAS"),
]
ELEC = {"Maharashtra": ("Deccan Power Distribution Ltd", "Pune"), "Karnataka": ("Namma Vidyut Supply Co", "Bengaluru"),
        "Telangana": ("Golconda Power Distribution Ltd", "Hyderabad"), "Delhi": ("Capital City Power Ltd", "Delhi"),
        "Rajasthan": ("Marudhar Vidyut Vitaran Ltd", "Jaipur"), "Uttar Pradesh": ("Awadh Power Distribution Ltd", "Lucknow"),
        "Madhya Pradesh": ("Malwa Vidyut Vitaran Ltd", "Indore"), "Gujarat": ("Sabarmati Power Supply Ltd", "Ahmedabad")}

MERCHANTS = []
M_LOCAL = defaultdict(list)
M_NAT = defaultdict(list)
M_ELEC = {}


def slug(name, n=14):
    return re.sub(r"[^a-z0-9]", "", name.lower())[:n]


def add_merchant(name, mcc, label, city, cat):
    m = {"merchant_id": uniq(lambda: f"MER{rng.randint(10000, 99999)}"), "merchant_name": name, "mcc": mcc,
         "category": label, "city": city,
         "upi_id": uniq(lambda: f"{slug(name)}{rng.randint(1, 999)}@{rng.choice(PSPS)}"), "_cat": cat}
    MERCHANTS.append(m)
    return m


for c in CITIES:
    for cat, (mcc, label, n, names) in LOCAL_CATS.items():
        k = n * (2 if c[0] == "Pune" else 1)
        for nm in rng.sample(names, min(k, len(names))):
            M_LOCAL[(c[0], cat)].append(add_merchant(nm, mcc, label, c[0], cat))
for nm, mcc, label, city, cat in NATIONAL:
    M_NAT[cat].append(add_merchant(nm, mcc, label, city, cat))
for st, (nm, city) in ELEC.items():
    M_ELEC[st] = add_merchant(nm, "4900", "Utility - Electricity", city, "ELECTRICITY")

# ----------------------------------------------------------------------------- counterparties
CPTY = {}
MULE_NAMES = set()
for r in S["fraud_rings"]:
    for m in r["mule_accounts"]:
        CPTY[m["ext_id"]] = dict(m, first_seen_in_our_data="", _kind="scenario")
        MULE_NAMES.add(m["holder_name"])


def new_cpty(name, htype, opened_lo, opened_hi, upi=True, kind="legit", recurring=False):
    bank, code, psp = rng.choices(FAKE_BANKS, [30, 25, 20, 15, 10])[0]
    row = {"ext_id": uniq(lambda: f"EXT{rng.randint(10000, 99999)}"), "holder_name": name, "holder_type": htype,
           "bank": bank, "ifsc": f"{code}0{rng.randint(1000, 999999):06d}",
           "account_number": uniq(lambda: digits(rng.choice([11, 12, 12, 13, 14, 15, 16]))),
           "upi_id": uniq(lambda: f"{slug(name)}{rng.randint(10, 9999)}@{psp}") if upi else "",
           "account_opened_on": rand_date(opened_lo, opened_hi).isoformat(), "first_seen_in_our_data": "",
           "_kind": kind, "_recurring": recurring}
    CPTY[row["ext_id"]] = row
    return row


def person_name(last=None, gender=None):
    g = gender or rng.choice("FM")
    return f"{rng.choice(FIRST_F if g == 'F' else FIRST_M)} {last or rng.choice(LAST)}"


CO_PRE = ["Deccan", "Konkan", "Vidarbha", "Trident", "Pinnacle", "Silverline", "Bluestone", "Greenfield", "Apex", "Navbharat",
          "Suvidha", "Orbit", "Crescent", "Evergreen", "Sunrise", "Lotus", "Vertex", "Zenith", "Indrayani", "Panchganga",
          "Godavari", "Kaveri", "Nilgiri", "Aravali", "Satpura", "Unity", "Pragati", "Sanmati"]
CO_SUF = ["Infotech Pvt Ltd", "Auto Components Ltd", "Pharma Pvt Ltd", "Logistics Pvt Ltd", "Engg Works Ltd", "Textiles Pvt Ltd",
          "Software Services LLP", "Hospitals Pvt Ltd", "Foods Pvt Ltd", "Retail Pvt Ltd", "Constructions Pvt Ltd", "Polymers Ltd",
          "Electricals Pvt Ltd", "Consultancy Services Pvt Ltd", "Packaging Ltd", "Agro Industries Ltd", "Fintech Solutions Pvt Ltd",
          "Education Society"]
_co_names = set()
EMPLOYERS = []
while len(EMPLOYERS) < 60:
    nm = f"{rng.choice(CO_PRE)} {rng.choice(CO_SUF)}"
    if nm in _co_names:
        continue
    _co_names.add(nm)
    EMPLOYERS.append(new_cpty(nm, "company", date(1988, 1, 1), date(2019, 12, 31), upi=False, recurring=True))
PENSIONERS = [new_cpty(n, "company", date(1985, 1, 1), date(2005, 1, 1), upi=False, recurring=True) for n in
              ["Maharashtra Teachers Pension Trust", "Retired Employees Pension Fund", "Deccan Mills Staff Pension Trust"]]
LENDERS = [new_cpty(n, "company", date(1995, 1, 1), date(2015, 1, 1), upi=False, recurring=True) for n in
           ["Kesari Housing Finance Ltd", "Pragati Consumer Finance Ltd", "Suvidha Auto Loans Ltd", "Sahyog Micro Finance Ltd",
            "Navbharat Home Loans Ltd", "Trident Two Wheeler Finance Ltd"]]
AMCS = [new_cpty(n, "company", date(1995, 1, 1), date(2012, 1, 1), upi=False, recurring=True) for n in
        ["Navbharat Mutual Fund", "Lotus Mutual Fund", "Evergreen Asset Management Co", "Unity Mutual Fund"]]
INSURERS = [new_cpty(n, "company", date(1995, 1, 1), date(2010, 1, 1), upi=False, recurring=True) for n in
            ["Raksha General Insurance Ltd", "Jeevan Suraksha Life Insurance Ltd"]]
BIZ_NAMES = ["Om Sai Enterprises", "Shree Balaji Traders", "Ganesh Electricals", "Jai Malhar Transport", "Siddhivinayak Hardware",
             "Mahalaxmi Textiles", "Patil Brothers Suppliers", "Royal Packaging Works", "Kiran Steel Traders", "Sai Tiffin Services",
             "Om Tailors", "Deshmukh Agencies", "Shivneri Plywood", "Mauli Transport Co", "Kamdhenu Dairy Products", "Vighnaharta Agencies",
             "Samarth Printers", "Tulja Bhavani Caterers", "Shreeji Plastics", "Anand Hardware Mart", "Navkar Distributors",
             "Sahyadri Cold Storage", "Ekvira Enterprises", "Bhairavnath Motors", "Omkar Furniture", "Venkatesh Agro Traders",
             "Kuber Wholesale", "Sagar Stationers", "Krishna Tiles & Sanitary", "Swami Travels", "Pawar Auto Works",
             "Mehta Chemicals", "Jain Cloth Emporium", "Rathi Commodities", "Chintamani Supplies", "Parvati Paper Products",
             "Gajanan Fabricators", "Mangalmurti Traders", "Dattaguru Enterprises", "Yashwant Agencies"]
BIZ = []
for nm in BIZ_NAMES:
    if nm in MULE_NAMES:
        continue
    BIZ.append(new_cpty(nm, rng.choice(["proprietorship", "proprietorship", "company"]), date(2004, 1, 1), date(2024, 6, 1),
                        upi=rng.random() < 0.7, recurring=True))
TUTORS = {}  # city -> list of shared tutors
for c in CITIES:
    TUTORS[c[0]] = [new_cpty(f"{person_name()}" + rng.choice(["", " Classes", ""]), "individual", date(2008, 1, 1), date(2023, 1, 1),
                             recurring=True) for _ in range(2 if c[0] != "Pune" else 4)]

# ----------------------------------------------------------------------------- customers
SPECIAL = {c["customer_id"]: c for c in S["special_customers"]}
SPECIAL.setdefault(S["demo_customer"]["customer"]["customer_id"], S["demo_customer"]["customer"])
DEMO_ID = S["demo_customer"]["customer"]["customer_id"]
GENERAL = defaultdict(list)
for g in S["general_complainants"]:
    GENERAL[g["customer"]["customer_id"]].append(g)

CUST_COLS = ["customer_id", "full_name", "gender", "dob", "age", "phone", "email", "city", "state", "pincode",
             "preferred_language", "segment", "customer_since", "kyc_status", "risk_rating"]


def segment_for(age, gender):
    if age >= 60:
        return "senior_citizen"
    if age < 25:
        return rng.choices(["student", "salaried"], [55, 45])[0]
    seg = rng.choices(["salaried", "self_employed", "homemaker", "business"], [55, 20, 15, 10])[0]
    if seg == "homemaker" and gender == "M" and rng.random() < 0.85:
        seg = "salaried"
    return seg


def age_on(dob):
    return TODAY.year - dob.year - ((TODAY.month, TODAY.day) < (dob.month, dob.day))


CUSTOMERS = []
CUST = {}
for n in range(1, N_CUSTOMERS + 1):
    cid = f"C{n:06d}"
    if cid in SPECIAL:
        sc = SPECIAL[cid]
        c = {k: sc[k] for k in CUST_COLS if k in sc}
        c["kyc_status"] = "FULL" if (cid == DEMO_ID or rng.random() < 0.9) else "RE_KYC_DUE"
        c["risk_rating"] = "LOW" if rng.random() < 0.8 else "MEDIUM"
        c["_special"] = True
        c["_handle"] = sc["upi_id"].split("@")[0]
    else:
        gender = rng.choice("FM")
        age = rng.choices([rng.randint(18, 24), rng.randint(25, 39), rng.randint(40, 59), rng.randint(60, 84)], [10, 38, 32, 20])[0]
        dob = TODAY - timedelta(days=age * 365 + rng.randint(0, 364))
        age = age_on(dob)
        city = rng.choices(CITIES, [x[4] for x in CITIES])[0]
        first = rng.choice(FIRST_F if gender == "F" else FIRST_M)
        last = rng.choice(LAST)
        f, l = first.lower(), last.lower()

        def mk_handle():
            return rng.choice([f"{f}.{l[:5]}{rng.randint(10, 99)}", f"{f}{l}{rng.randint(1, 999)}", f"{f}.{l}{rng.randint(10, 99)}",
                               f"{f[0]}{l}{rng.randint(10, 9999)}", f"{f}_{l[:4]}{rng.randint(10, 99)}"])
        while True:
            h = mk_handle()
            if f"{h}@example.com" not in USED and f"{h}@sahyadri" not in USED:
                break
        USED.add(f"{h}@example.com")
        USED.add(f"{h}@sahyadri")
        adult = dob + timedelta(days=18 * 366)
        since = TODAY - timedelta(days=rng.randint(200, 15 * 365))
        if since < adult:
            since = rand_date(adult, TODAY - timedelta(days=150)) if adult < TODAY - timedelta(days=150) else TODAY - timedelta(days=rng.randint(120, 150))
        seg = segment_for(age, gender)
        c = {"customer_id": cid, "full_name": f"{first} {last}", "gender": gender, "dob": dob.isoformat(), "age": age,
             "phone": uniq(lambda: (lambda x: f"+91 {x[:5]} {x[5:]}")("5" + digits(9))),
             "email": f"{h}@example.com", "city": city[0], "state": city[1],
             "pincode": city[2] + f"{rng.randint(1, 999):03d}", "preferred_language": rng.choice(city[3]),
             "segment": seg, "customer_since": since.isoformat()}
        r = rng.random()
        if since > TODAY - timedelta(days=500) and r < 0.12:
            c["kyc_status"] = "MIN_KYC"
        elif since < TODAY - timedelta(days=8 * 365) and r < 0.18:
            c["kyc_status"] = "RE_KYC_DUE"
        else:
            c["kyc_status"] = "FULL" if rng.random() < 0.96 else "RE_KYC_DUE"
        if seg == "business":
            c["risk_rating"] = rng.choices(["LOW", "MEDIUM", "HIGH"], [55, 37, 8])[0]
        else:
            c["risk_rating"] = rng.choices(["LOW", "MEDIUM", "HIGH"], [80, 17, 3])[0]
        c["_special"] = False
        c["_handle"] = h
    CUSTOMERS.append(c)
    CUST[cid] = c

# ----------------------------------------------------------------------------- accounts
ACCOUNTS = []
ACCT = {}
ACCTS_OF = defaultdict(list)


def branch_for(c):
    if c["customer_id"] == DEMO_ID:
        return "Kothrud"
    br = CITY.get(c["city"], CITIES[0])[5]
    return br[int(c["customer_id"][1:]) * 7 % len(br)]


for c in CUSTOMERS:
    sc = SPECIAL.get(c["customer_id"])
    br = branch_for(c)
    age = int(c["age"])
    seg = c["segment"]
    if sc:
        num, typ, upi = sc["account_number"], sc["account_type"], sc["upi_id"]
        status = "ACTIVE"
    else:
        num = uniq(lambda: "6021" + digits(10))
        if age >= 60:
            typ = "SENIOR_SAVINGS"
        elif seg == "salaried":
            typ = rng.choices(["SALARY", "SAVINGS"], [55, 45])[0]
        elif seg == "business":
            typ = rng.choices(["CURRENT", "SAVINGS"], [60, 40])[0]
        elif seg == "self_employed":
            typ = rng.choices(["SAVINGS", "CURRENT"], [70, 30])[0]
        else:
            typ = "SAVINGS"
        upi = f"{c['_handle']}@sahyadri"
        status = rng.choices(["ACTIVE", "DORMANT", "FROZEN"], [96.5, 3, 0.5])[0]
    if age >= 60:
        lim = rng.choices([25000, 50000, 100000], [30, 40, 30])[0]
    elif seg == "student":
        lim = rng.choice([10000, 25000, 50000])
    elif typ == "CURRENT":
        lim = rng.choice([100000, 200000])
    else:
        lim = rng.choices([50000, 100000], [30, 70])[0]
    a = {"account_number": num, "customer_id": c["customer_id"], "account_type": typ, "branch": br, "ifsc": IFSC[br],
         "opened_on": c["customer_since"], "status": status, "current_balance_inr": 0, "upi_id": upi,
         "daily_upi_limit_inr": lim, "_primary": True}
    ACCOUNTS.append(a)
    ACCT[num] = a
    ACCTS_OF[c["customer_id"]].append(a)
    if rng.random() < P_SECOND_ACCT:
        if age >= 60:
            t2 = "SAVINGS"
        elif seg in ("business", "self_employed"):
            t2 = "CURRENT" if typ != "CURRENT" else "SAVINGS"
        else:
            t2 = "SAVINGS"
        since = date.fromisoformat(c["customer_since"])
        st2 = rng.choices(["ACTIVE", "DORMANT", "FROZEN"], [75, 22, 3])[0]
        num2 = uniq(lambda: "6021" + digits(10))
        upi2 = ""
        if st2 == "ACTIVE" and rng.random() < 0.3:
            upi2 = uniq(lambda: c["phone"].replace("+91", "").replace(" ", "") + "@sahyadri")
        a2 = {"account_number": num2, "customer_id": c["customer_id"], "account_type": t2, "branch": br, "ifsc": IFSC[br],
              "opened_on": rand_date(since, TODAY - timedelta(days=120)).isoformat(), "status": st2, "current_balance_inr": 0,
              "upi_id": upi2, "daily_upi_limit_inr": 25000 if upi2 else "", "_primary": False}
        ACCOUNTS.append(a2)
        ACCT[num2] = a2
        ACCTS_OF[c["customer_id"]].append(a2)

# ----------------------------------------------------------------------------- cards
CARDS = []
NETWORKS = {"RuPay": ["6522", "6521", "6070", "6081"], "Visa": ["4214", "4591", "4390", "4166"], "Mastercard": ["5241", "5318", "5470", "5176"]}


def add_card(acct, ctype, last4=None, status="ACTIVE", issued=None, network=None, intl=None):
    network = network or rng.choices(list(NETWORKS), [55, 25, 20] if ctype == "DEBIT" else [20, 45, 35])[0]
    last4 = last4 or digits(4)
    issued = issued or rand_date(max(date.fromisoformat(acct["opened_on"]), TODAY - timedelta(days=5 * 365 - 90)), TODAY - timedelta(days=45))
    exp_year = issued.year + 5
    card = {"card_id": uniq(lambda: "CRD" + digits(9)), "account_number": acct["account_number"], "card_type": ctype,
            "network": network, "masked_pan": f"{rng.choice(NETWORKS[network])} XXXX XXXX {last4}", "status": status,
            "issued_on": issued.isoformat(), "expiry_mm_yy": f"{issued.month:02d}/{exp_year % 100:02d}",
            "international_enabled": str(intl if intl is not None else (rng.random() < (0.1 if ctype == "DEBIT" else 0.6))).lower()}
    CARDS.append(card)
    return card


for c in CUSTOMERS:
    prim = ACCTS_OF[c["customer_id"]][0]
    sc = SPECIAL.get(c["customer_id"])
    cats = {g["category"]: g for g in GENERAL.get(c["customer_id"], [])}
    since = date.fromisoformat(prim["opened_on"])
    if since < TODAY - timedelta(days=5 * 365) and rng.random() < 0.35:  # an older card that expired / was replaced
        old_iss = rand_date(since, TODAY - timedelta(days=5 * 365 + 30))
        add_card(prim, "DEBIT", status=rng.choice(["EXPIRED", "REISSUED"]), issued=old_iss)
    last4 = sc["debit_card_last4"] if sc else None
    if "lost_or_stolen_card" in cats:
        inc = date.fromisoformat(cats["lost_or_stolen_card"]["incident_date"])
        add_card(prim, "DEBIT", last4=last4, status="HOTLISTED", issued=rand_date(since, inc - timedelta(days=200)))
        if inc + timedelta(days=1) <= TODAY:
            add_card(prim, "DEBIT", status="ACTIVE", issued=min(TODAY, inc + timedelta(days=rng.randint(1, 3))))
    elif "debit_card_not_received" in cats:
        inc = date.fromisoformat(cats["debit_card_not_received"]["incident_date"])
        add_card(prim, "DEBIT", status="REISSUED", issued=rand_date(since, inc - timedelta(days=400)))
        add_card(prim, "DEBIT", last4=last4, status="ACTIVE", issued=max(since, inc - timedelta(days=rng.randint(8, 20))))
    else:
        add_card(prim, "DEBIT", last4=last4, status="ACTIVE" if prim["status"] != "FROZEN" else "HOTLISTED")
    for a in ACCTS_OF[c["customer_id"]][1:]:
        if a["status"] == "ACTIVE" and rng.random() < 0.4:
            add_card(a, "DEBIT")
    wants_cc = "credit_card_billing_dispute" in cats or (
        c["segment"] in ("salaried", "business", "self_employed") and 25 <= int(c["age"]) <= 60 and rng.random() < 0.2)
    if wants_cc and prim["status"] == "ACTIVE":
        add_card(prim, "CREDIT")

# ----------------------------------------------------------------------------- per-customer profile
for c in CUSTOMERS:
    prim = ACCTS_OF[c["customer_id"]][0]
    seg, age = c["segment"], int(c["age"])
    active = prim["status"] == "ACTIVE"
    c["_active"] = active
    if c["_special"]:
        c["_app"], c["_upi_app"] = True, True
    else:
        c["_app"] = active and rng.random() < (0.62 if age >= 60 else 0.88)
        c["_upi_app"] = c["_app"] and rng.random() < P_UPI_VIA_APP
    c["_bbps_app"] = c["_app"] and (c["_special"] or rng.random() < P_BBPS_VIA_APP)
    c["_ips"] = [f"{rng.choice(['192.0.2', '198.51.100', '203.0.113'])}.{rng.randint(1, 254)}" for _ in range(2)]
    c["_fav"] = {}

# ----------------------------------------------------------------------------- transactions
TX = []


def make_utr(channel, ts, code="SAHY"):
    if channel in ("UPI", "IMPS", "CARD_POS", "CARD_ECOM", "ATM", "BBPS"):
        return uniq(lambda: str(rng.randint(1, 9)) + digits(11))
    if channel == "NEFT":
        return uniq(lambda: f"{code}N{ts:%y}{ts.timetuple().tm_yday:03d}{digits(8)}")
    if channel == "RTGS":
        return uniq(lambda: f"{code}R{ts:%Y%m%d}{digits(8)}")
    if channel == "NACH":
        return uniq(lambda: f"NACH{ts:%y%m%d}{digits(6)}")
    return ""


def tx(ts, c, a, direction, channel, cptype, cpid, cpupi, amount, status="SUCCESS", remarks="", app=False,
       hold=False, txn_id=None, utr=None, fixed=False, code="SAHY"):
    if ts > LATEST or ts < W0_DT:
        return None
    row = {"txn_id": txn_id or uniq(lambda: "TXN" + digits(12)),
           "utr": utr if utr is not None else make_utr(channel, ts, code), "ts": ts,
           "customer_id": c["customer_id"], "account_number": a["account_number"], "direction": direction,
           "channel": channel, "counterparty_type": cptype, "counterparty_id": cpid, "counterparty_upi": cpupi or "",
           "amount_inr": round(float(amount), 2), "balance_after_inr": None, "status": status, "remarks": remarks,
           "device_id": "", "session_id": "", "_app": bool(app) and direction == "DEBIT", "_hold": hold, "_fixed": fixed,
           "_pair": None}
    TX.append(row)
    return row


def fav_merchant(c, cat):
    if cat in LOCAL_CATS:
        pool = M_LOCAL[(c["city"], cat)] or M_LOCAL[("Pune", cat)]
    else:
        pool = M_NAT[cat]
    if cat not in c["_fav"]:
        c["_fav"][cat] = rng.sample(pool, min(len(pool), rng.randint(1, 3)))
    favs = c["_fav"][cat]
    return rng.choice(favs) if rng.random() < 0.85 else rng.choice(pool)


def atm_id(c):
    if rng.random() < 0.55:
        bi = BRANCHES.index(branch_for(c))
        return f"SHY{bi + 1:02d}A{rng.randint(1, 4):02d}", False
    code = rng.choice(FAKE_BANKS)[1]
    return f"{code}{c['city'][:3].upper()}{rng.randint(1000, 9999)}", True


UPI_NOTES = {
    "GROCERY": ["", "", "", "", "groceries", "milk", "sabzi", "kirana", "monthly saman", "Paid"],
    "RESTAURANT": ["", "", "", "lunch", "dinner", "bill", "chai nashta"],
    "FUEL": ["", "", "", "petrol", "fuel"],
    "PHARMACY": ["", "", "", "medicines", "dawai", "tablets"],
    "ECOM": ["", "", "order"], "ECOM_GROCERY": ["", "", "order"], "FOOD_DELIVERY": ["", ""],
    "APPAREL": ["", "", "kapde", "shopping"], "ELECTRONICS": ["", "", "mobile cover", "charger"],
    "SALON": ["", "", "haircut"], "CLINIC": ["", "", "consultation", "doctor fees"], "MOVIES": ["", ""],
    "TRAVEL": ["", "", "tickets", "bus ticket"], "EDUCATION": ["fees", "school fees", "", "term fees"],
    "GYM": ["gym fees", "", "membership"],
}
DISC = [("GROCERY", 30, 26, 14), ("RESTAURANT", 10, 4, 14), ("FUEL", 9, 3, 5), ("ECOM", 8, 4, 12),
        ("FOOD_DELIVERY", 7, 2, 16), ("PHARMACY", 5, 16, 2), ("ATM", 9, 16, 6), ("ECOM_GROCERY", 4, 3, 3),
        ("APPAREL", 3, 2, 4), ("ELECTRONICS", 1, 1, 2), ("SALON", 3, 2, 4), ("CLINIC", 2, 6, 1), ("MOVIES", 2, 1, 5),
        ("TRAVEL", 1, 1, 1), ("P2P_OUT", 5, 3, 6)]
SEG_RATE = {"salaried": 1.05, "business": 1.2, "self_employed": 1.0, "homemaker": 0.8, "student": 1.0, "senior_citizen": 0.55}


def spend_amount(cat, senior=False):
    if cat == "GROCERY":
        return int(min(4500, max(20, rng.lognormvariate(5.7, 0.8))))
    if cat == "RESTAURANT":
        return int(min(4000, max(80, rng.lognormvariate(6.3, 0.6))))
    if cat == "FUEL":
        return rng.choice([200, 300, 500, 500, 1000, 1000, 1500, 2000, 2500, 3000]) if rng.random() < 0.7 else round(rng.uniform(300, 3500), 2)
    if cat == "ECOM":
        return rng.choice([199, 249, 299, 349, 399, 449, 499, 599, 699, 799, 899, 999, 1199, 1299, 1499, 1799, 1999, 2499, 2999, 3499, 4999, 7999, 12999])
    if cat == "FOOD_DELIVERY":
        return int(min(1800, max(99, rng.lognormvariate(5.9, 0.45))))
    if cat == "PHARMACY":
        return int(min(4000, max(40, rng.lognormvariate(6.0 if not senior else 6.6, 0.8))))
    if cat == "ATM":
        return rng.choice([500, 1000, 1500, 2000, 2000, 3000, 4000, 5000, 5000, 10000] if not senior else [2000, 3000, 5000, 5000, 10000])
    if cat == "ECOM_GROCERY":
        return int(rng.uniform(250, 3500))
    if cat == "APPAREL":
        return int(rng.uniform(400, 8000))
    if cat == "ELECTRONICS":
        return rng.choice([299, 499, 799, 1299, 2499, 8999, 14999, 23999])
    if cat == "SALON":
        return rng.choice([150, 200, 250, 300, 450, 600, 900, 1500, 2500])
    if cat == "CLINIC":
        return rng.choice([300, 400, 500, 500, 600, 800, 1000, 1500])
    if cat == "MOVIES":
        return rng.choice([250, 320, 480, 560, 640, 900, 1200])
    if cat == "TRAVEL":
        return int(rng.uniform(450, 9000))
    return 500


def spend_hours(cat):
    if cat in ("RESTAURANT", "FOOD_DELIVERY"):
        return (12, 15) if rng.random() < 0.4 else (19, 23.5)
    if cat == "ECOM":
        return (8, 23.9)
    if cat == "GROCERY":
        return (7.5, 21.5)
    return (9, 22)


def merchant_spend(c, a, d, cat, amount=None, channel=None, status="SUCCESS", hold=False, h=None):
    m = fav_merchant(c, cat)
    amt = amount if amount is not None else spend_amount(cat, c["segment"] == "senior_citizen")
    if channel is None:
        if cat in ("ECOM", "FOOD_DELIVERY", "ECOM_GROCERY", "MOVIES", "TRAVEL"):
            channel = "CARD_ECOM" if rng.random() < 0.4 else "UPI"
        elif cat in ("GROCERY", "PHARMACY", "SALON", "CLINIC"):
            channel = "UPI" if rng.random() < 0.85 else "CARD_POS"
        elif cat == "ELECTRONICS":
            channel = "CARD_POS" if rng.random() < 0.6 else "UPI"
        else:
            channel = "UPI" if rng.random() < 0.6 else "CARD_POS"
    hh = h or spend_hours(cat)
    ts = at(d, *hh)
    if channel == "UPI":
        rem = rng.choice(UPI_NOTES.get(cat, [""]))
        return tx(ts, c, a, "DEBIT", "UPI", "MERCHANT", m["merchant_id"], m["upi_id"], amt, status, rem, app=c["_upi_app"], hold=hold)
    if channel == "CARD_POS":
        if isinstance(amt, int) and cat == "FUEL" and rng.random() < 0.5:
            amt = amt + round(rng.random(), 2)
        return tx(ts, c, a, "DEBIT", "CARD_POS", "MERCHANT", m["merchant_id"], "", amt, status,
                  f"POS {m['merchant_name'].upper()[:24]} {m['city'].upper()}", hold=hold)
    return tx(ts, c, a, "DEBIT", "CARD_ECOM", "MERCHANT", m["merchant_id"], "", amt, status,
              f"ECOM {m['merchant_name'].upper()}", hold=hold)


def atm_wdl(c, a, d, amt=None, h=(8, 22)):
    aid, nfs = atm_id(c)
    amt = amt or spend_amount("ATM", c["segment"] == "senior_citizen")
    return tx(at(d, *h), c, a, "DEBIT", "ATM", "ATM", aid, "", amt, "SUCCESS",
              f"{'NFS ' if nfs else ''}ATM WDL/{aid}/{c['city'].upper()}"), aid


def family_of(c, direction):
    key = "_fam_" + direction
    if key not in c:
        last = c["full_name"].split()[-1]
        c[key] = new_cpty(person_name(last), "individual", date(2008, 1, 1), date(2024, 1, 1), recurring=True)
    return c[key]


def p2p(c, a, ts, cp, amt, direction, remarks=None, channel=None):
    channel = channel or ("UPI" if rng.random() < 0.8 else "IMPS")
    if channel == "UPI":
        rem = remarks if remarks is not None else rng.choice(["", "", "Sent", "ghar kharcha", "for mummy", "papa", "medicine", "pocket money", "chhota kharcha"])
        return tx(ts, c, a, direction, "UPI", "EXTERNAL", cp["ext_id"], cp["upi_id"], amt, "SUCCESS", rem,
                  app=c["_upi_app"] and direction == "DEBIT")
    rem = f"IMPS/P2A/{cp['holder_name'].upper()[:20]}" + (f"/{remarks}" if remarks else "")
    return tx(ts, c, a, direction, "IMPS", "EXTERNAL", cp["ext_id"], "", amt, "SUCCESS", rem, app=c["_app"] and direction == "DEBIT")


CHARGES = [("DEBIT CARD ANNUAL FEE 2026 INCL GST", 590.00), ("MIN AVG BAL NON-MAINT CHGS JUL-26 INCL GST", 413.00),
           ("SMS ALERT CHGS JUL-SEP 26", 17.70), ("ATM TXN CHGS EXCESS FREE LIMIT", 23.60), ("DC REPLACEMENT CHGS INCL GST", 236.00),
           ("CHQ BOOK ISSUE CHGS INCL GST", 118.00), ("IMPS CHGS INCL GST", 5.90)]
GL_INT, GL_CHG = "SAHY-GL-INTEREST", "SAHY-GL-CHARGES"


def gen_customer(c):
    accts = ACCTS_OF[c["customer_id"]]
    prim = accts[0]
    seg, age = c["segment"], int(c["age"])
    senior = seg == "senior_citizen"
    cats = defaultdict(list)
    for g in GENERAL.get(c["customer_id"], []):
        cats[g["category"]].append(date.fromisoformat(g["incident_date"]))
    # interest for every savings-type account (incl. dormant)
    for a in accts:
        if a["account_type"] != "CURRENT":
            tx(datetime(2026, 6, 30, 23, rng.randint(30, 58), rng.randint(0, 59), tzinfo=IST), c, a, "CREDIT", "INTERNAL", "INTERNAL",
               GL_INT, "", round(rng.uniform(8, 2800 if not senior else 5200), 2), "SUCCESS", "INT.PD:01-04-2026 TO 30-06-2026")
    if not c["_active"]:
        return
    if rng.random() < 0.5:
        tx(at(date(2026, 7, rng.randint(2, 6)), 1, 4), c, prim, "DEBIT", "INTERNAL", "INTERNAL", GL_CHG, "", 17.70, "SUCCESS",
           "SMS ALERT CHGS APR-JUN 26")
    # income
    if seg == "salaried":
        emp = c.setdefault("_emp", rng.choice(EMPLOYERS))
        pay = emp.setdefault("_payday", rng.choice(["EOM", "EOM", "1ST", "7TH"]))
        base = int(min(250000, max(15000, rng.lognormvariate(10.7, 0.5))))
        days = {"EOM": [date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31)], "1ST": [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)],
                "7TH": [date(2026, 7, 7), date(2026, 8, 7), date(2026, 9, 7)]}[pay]
        for d in days:
            mon = d.month if pay == "EOM" else d.month - 1
            amt = base + (rng.randint(-1500, 2500) if rng.random() < 0.4 else 0)
            code = next(b[1] for b in FAKE_BANKS if b[0] == emp["bank"])
            tx(at(d, 9, 18), c, prim, "CREDIT", "NEFT", "EMPLOYER", emp["ext_id"], "", amt, "SUCCESS",
               f"NEFT-SALARY {MON[mon]} 2026-{emp['holder_name'].upper()[:26]}", code=code)
    elif senior and rng.random() < 0.72:
        pen = rng.choice(PENSIONERS)
        amt = int(rng.uniform(11000, 62000))
        code = next(b[1] for b in FAKE_BANKS if b[0] == pen["bank"])
        for d in monthly(1, 1, (7, 8, 9)):
            tx(at(d, 7, 12), c, prim, "CREDIT", "NEFT", "EMPLOYER", pen["ext_id"], "", amt, "SUCCESS",
               f"PENSION {MON[d.month - 1]} 2026 {pen['holder_name'].upper()[:24]}", code=code)
    elif seg in ("business", "self_employed"):
        clients = rng.sample(BIZ, rng.randint(2, 5))
        n = poisson((1.0 if seg == "business" else 0.5) * 13)
        for _ in range(n):
            cp = rng.choice(clients)
            d = rng.choice(DAYS)
            amt = int(rng.lognormvariate(9.6 if seg == "business" else 9.0, 0.7))
            ch = rng.choices(["NEFT", "IMPS", "UPI"], [45, 35, 20])[0]
            if ch == "UPI" and not cp["upi_id"]:
                ch = "IMPS"
            if amt >= 200000:
                ch = "RTGS"
            code = next(b[1] for b in FAKE_BANKS if b[0] == cp["bank"])
            rem = {"NEFT": f"NEFT-{cp['holder_name'].upper()[:22]}-INV {rng.randint(100, 9999)}",
                   "RTGS": f"RTGS-{cp['holder_name'].upper()[:22]}", "IMPS": f"IMPS/P2A/{cp['holder_name'].upper()[:20]}/bill {rng.randint(10, 999)}",
                   "UPI": rng.choice(["", "payment", "bill"])}[ch]
            tx(at(d, 9.5, 19.5), c, prim, "CREDIT", ch, "EXTERNAL", cp["ext_id"], cp["upi_id"] if ch == "UPI" else "", amt, "SUCCESS", rem, code=code)
        if seg == "business":
            for _ in range(poisson(0.4 * 13)):
                cp = rng.choice(BIZ)
                amt = int(rng.lognormvariate(9.8, 0.8))
                ch = "RTGS" if amt >= 200000 else rng.choice(["NEFT", "IMPS"])
                tx(at(rng.choice(DAYS), 10, 18), c, prim, "DEBIT", ch, "EXTERNAL", cp["ext_id"], "", amt, "SUCCESS",
                   f"{ch} TO {cp['holder_name'].upper()[:22]} PMT", app=c["_app"])
    elif seg in ("homemaker", "student") and rng.random() < 0.25:
        fam = family_of(c, "in")
        amt = rng.choice([3000, 5000, 5000, 8000, 10000, 15000, 20000, 25000])
        for d in monthly(1, 10, (7, 8, 9)):
            p2p(c, prim, at(d, 8, 22), fam, amt, "CREDIT", remarks=rng.choice(["", "ghar kharcha", "pocket money", "for you", "monthly"]))
    # recurring outflows
    if seg in ("salaried", "self_employed") and age < 45 and rng.random() < 0.12:
        ll = new_cpty(person_name(), "individual", date(2006, 1, 1), date(2022, 1, 1), recurring=True)
        rent = rng.choice([8000, 9500, 11000, 12000, 14000, 15000, 18000, 21000, 25000, 28000, 35000])
        ch = rng.choices(["UPI", "IMPS", "NEFT"], [60, 30, 10])[0]
        for d in monthly(1, 5, (7, 8, 9)):
            ts = at(d, 8, 22)
            if ch == "UPI":
                tx(ts, c, prim, "DEBIT", "UPI", "EXTERNAL", ll["ext_id"], ll["upi_id"], rent, "SUCCESS",
                   rng.choice(["rent", f"rent {MON[d.month].lower()}", "house rent", f"Rent {MON[d.month].title()} 2026", ""]), app=c["_upi_app"])
            else:
                tx(ts, c, prim, "DEBIT", ch, "EXTERNAL", ll["ext_id"], "", rent, "SUCCESS",
                   f"{ch}/RENT {MON[d.month]}/{ll['holder_name'].upper()[:20]}", app=c["_app"])
    if rng.random() < 0.05 and seg != "student":
        maid = new_cpty(person_name(gender="F"), "individual", date(2012, 1, 1), date(2024, 6, 1), recurring=True)
        amt = rng.choice([1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000])
        for d in monthly(1, 7, (7, 8, 9)):
            tx(at(d, 8, 21), c, prim, "DEBIT", "UPI", "EXTERNAL", maid["ext_id"], maid["upi_id"], amt, "SUCCESS",
               rng.choice(["maid salary", "bai pagar", "cook", "kaamwali", ""]), app=c["_upi_app"])
    if 30 <= age <= 50 and rng.random() < 0.06:
        tut = rng.choice(TUTORS.get(c["city"], TUTORS["Pune"]))
        tut["_used"] = True
        amt = rng.choice([1500, 2000, 2500, 3000, 4000, 5000])
        for d in monthly(1, 10, (7, 8, 9)):
            tx(at(d, 9, 21), c, prim, "DEBIT", "UPI", "EXTERNAL", tut["ext_id"], tut["upi_id"], amt, "SUCCESS",
               rng.choice(["tuition fees", "classes fees", "tuition", ""]), app=c["_upi_app"])
    if seg in ("salaried", "self_employed", "business") and rng.random() < 0.08:
        fam = family_of(c, "out")
        amt = rng.choice([2000, 3000, 5000, 5000, 7000, 10000, 15000])
        for d in monthly(1, 10, (7, 8, 9)):
            p2p(c, prim, at(d, 8, 22), fam, amt, "DEBIT", remarks=rng.choice(["", "ghar", "for mummy papa", "monthly", "gharkharcha"]))
    # bills
    if rng.random() < 0.5:
        b = M_ELEC[c["state"]]
        ca = digits(12)
        for d in monthly(8, 20, (7, 8, 9)):
            amt = round(rng.uniform(380, 4200 if not senior else 2600), 2) if rng.random() < 0.6 else int(rng.uniform(380, 4200))
            tx(at(d, 8, 22), c, prim, "DEBIT", "BBPS", "BILLER", b["merchant_id"], "", amt, "SUCCESS",
               f"BBPS/{b['merchant_name'].upper()}/CA {ca}", app=c["_bbps_app"])
    if rng.random() < 0.55:
        post = rng.random() < 0.35
        telco = rng.choice(M_NAT["MOBILE_POST" if post else "MOBILE_PRE"])
        if post:
            amt = rng.choice([399, 499, 599, 749, 999, 1199])
            for d in monthly(10, 22, (7, 8, 9)):
                tx(at(d, 8, 22), c, prim, "DEBIT", "BBPS", "BILLER", telco["merchant_id"], "", amt, "SUCCESS",
                   f"BBPS/{telco['merchant_name'].upper()}/{c['phone'][4:].replace(' ', '')}", app=c["_bbps_app"])
        else:
            amt = rng.choice([199, 239, 299, 349, 399, 579, 666, 719, 859])
            d = W0 + timedelta(days=rng.randint(0, 27))
            while d <= W1:
                tx(at(d, 7, 23), c, prim, "DEBIT", "UPI", "MERCHANT", telco["merchant_id"], telco["upi_id"], amt, "SUCCESS",
                   rng.choice(["", "recharge", "mobile recharge"]), app=c["_upi_app"])
                d += timedelta(days=28 if amt < 500 else 84)
    if rng.random() < 0.15 and seg != "student":
        bb = rng.choice(M_NAT["BROADBAND"])
        amt = rng.choice([499, 599, 699, 799, 999, 1178, 1499])
        for d in monthly(3, 15, (7, 8, 9)):
            tx(at(d, 8, 22), c, prim, "DEBIT", "BBPS", "BILLER", bb["merchant_id"], "", amt, "SUCCESS",
               f"BBPS/{bb['merchant_name'].upper()}/ACC {digits(9)}", app=c["_bbps_app"])
    if rng.random() < 0.08:
        dth = M_NAT["DTH"][0]
        for d in monthly(1, 28, (7, 8, 9)):
            tx(at(d, 8, 22), c, prim, "DEBIT", "BBPS", "BILLER", dth["merchant_id"], "", rng.choice([253, 299, 350, 420, 499]), "SUCCESS",
               f"BBPS/AKASH DTH/VC {digits(10)}", app=c["_bbps_app"])
    if c["state"] in ("Maharashtra", "Gujarat", "Delhi") and rng.random() < 0.1:
        gas = M_NAT["GAS"][0]
        for d in monthly(10, 25, (7, 9)):
            tx(at(d, 8, 22), c, prim, "DEBIT", "BBPS", "BILLER", gas["merchant_id"], "", round(rng.uniform(350, 1600), 2), "SUCCESS",
               f"BBPS/METRO PIPED GAS/BP {digits(10)}", app=c["_bbps_app"])
    # NACH
    emi_days = cats.get("emi_debited_twice", [])
    if emi_days or (25 <= age <= 62 and rng.random() < 0.18):
        lender = rng.choice(LENDERS)
        amt = rng.choice([2350, 3100, 4250, 5600, 7800, 9999, 12450, 15600, 21300, 28750, 34200])
        loan = f"LN{digits(8)}"
        if emi_days:
            inc = emi_days[0]
            emi_dom = min(inc.day, 28)
        else:
            inc, emi_dom = None, rng.choice([2, 5, 7, 10])
        for m in (7, 8, 9):
            d = date(2026, m, emi_dom)
            if d > W1:
                continue
            ts = at(d, 4, 8)
            rem = f"NACH-DR/{lender['holder_name'].upper()[:22]}/{loan}"
            tx(ts, c, prim, "DEBIT", "NACH", "EXTERNAL", lender["ext_id"], "", amt, "SUCCESS", rem)
            if inc and d == date(2026, inc.month, emi_dom):
                tx(ts + timedelta(minutes=rng.randint(20, 150)), c, prim, "DEBIT", "NACH", "EXTERNAL", lender["ext_id"], "", amt, "SUCCESS", rem)
    if seg != "student" and rng.random() < 0.15:
        amc = rng.choice(AMCS)
        amt = rng.choice([500, 1000, 1000, 2000, 2500, 3000, 5000, 5000, 10000])
        folio = digits(9)
        dom = rng.choice([5, 10, 15, 25])
        for d in monthly(dom, dom, (7, 8, 9)):
            tx(at(d, 4, 9), c, prim, "DEBIT", "NACH", "EXTERNAL", amc["ext_id"], "", amt, "SUCCESS",
               f"NACH-DR/{amc['holder_name'].upper()[:22]}/SIP/{folio}")
    if rng.random() < 0.05:
        ins = rng.choice(INSURERS)
        tx(at(rng.choice(DAYS), 4, 9), c, prim, "DEBIT", "NACH", "EXTERNAL", ins["ext_id"], "", rng.choice([8450, 12600, 18900, 24300, 41750]),
           "SUCCESS", f"NACH-DR/{ins['holder_name'].upper()[:22]}/POL {digits(8)}")
    if 30 <= age <= 50 and rng.random() < 0.08:
        sch = fav_merchant(c, "EDUCATION")
        d = date(2026, 7, rng.randint(1, 20))
        tx(at(d, 9, 20), c, prim, "DEBIT", "UPI", "MERCHANT", sch["merchant_id"], sch["upi_id"], rng.choice([6500, 9800, 12500, 18000, 24500, 32000]),
           "SUCCESS", rng.choice(["term fees", "school fees", "fees Q2"]), app=c["_upi_app"])
    if age < 45 and rng.random() < 0.05:
        gym = fav_merchant(c, "GYM")
        for d in monthly(1, 8, (7, 8, 9)):
            tx(at(d, 6, 21), c, prim, "DEBIT", "UPI", "MERCHANT", gym["merchant_id"], gym["upi_id"], rng.choice([800, 1000, 1200, 1500, 2000]),
               "SUCCESS", "gym fees", app=c["_upi_app"])
    # own-account transfers to an active second account
    for a2 in accts[1:]:
        if a2["status"] == "ACTIVE" and rng.random() < 0.7:
            amt = rng.choice([2000, 3000, 5000, 10000, 15000, 20000, 25000])
            for d in monthly(2, 10, (7, 8, 9)):
                ts = at(d, 9, 22)
                r1 = tx(ts, c, prim, "DEBIT", "INTERNAL", "INTERNAL", a2["account_number"], "", amt, "SUCCESS",
                        f"TRF TO OWN A/C XX{a2['account_number'][-4:]}", app=c["_app"])
                r2 = tx(ts, c, a2, "CREDIT", "INTERNAL", "INTERNAL", prim["account_number"], "", amt, "SUCCESS",
                        f"TRF FROM OWN A/C XX{prim['account_number'][-4:]}")
                if r1 and r2:
                    r1["_pair"], r2["_pair"] = r2, r1
            if rng.random() < 0.5:
                for _ in range(rng.randint(1, 4)):
                    merchant_spend(c, a2, rng.choice(DAYS), rng.choice(["GROCERY", "ECOM", "RESTAURANT"]), channel="UPI" if a2["upi_id"] else "CARD_POS")
    # discretionary
    rate = SEG_RATE[seg] * rng.lognormvariate(0, 0.55) * DISC_SCALE
    col = 2 if senior else (3 if seg == "student" else 1)
    menu = [(d[0], d[col]) for d in DISC]
    for _ in range(poisson(rate * 13)):
        cat = pick(menu)
        d = rng.choice(DAYS)
        if cat == "ATM":
            atm_wdl(c, prim, d)
        elif cat == "P2P_OUT":
            fam = c.get("_fam_out") or c.get("_fam_in")
            if fam:
                p2p(c, prim, at(d, 8, 22), fam, rng.choice([200, 500, 500, 1000, 1500, 2000, 3000, 5000]), "DEBIT")
            else:
                merchant_spend(c, prim, d, "GROCERY")
        else:
            st = "FAILED" if rng.random() < 0.02 else "SUCCESS"
            merchant_spend(c, prim, d, cat, status=st)
    # rare "debited but failed" UPI, reversed the next working day
    if rng.random() < 0.012:
        d = rand_date(W0, TODAY - timedelta(days=5))
        r = merchant_spend(c, prim, d, "GROCERY", amount=int(rng.uniform(150, 2500)), channel="UPI", status="FAILED", hold=True)
        if r:
            rev = r["ts"] + timedelta(days=1, hours=rng.randint(1, 6))
            tx(rev, c, prim, "CREDIT", "UPI", r["counterparty_type"], r["counterparty_id"], r["counterparty_upi"], r["amount_inr"], "REVERSED",
               f"UPI REV/{r['utr']}", utr=r["utr"])
    # ---- general complainant specifics
    for d in cats.get("failed_upi_debited_not_credited", []):
        amt = rng.choice([500, 1200, 1850, 2500, 3000, 4999, 6000, 7500, 10000, 12000])
        fam = c.get("_fam_out") or c.get("_fam_in")
        if fam and rng.random() < 0.5:
            r = tx(at(d, 9, 21), c, prim, "DEBIT", "UPI", "EXTERNAL", fam["ext_id"], fam["upi_id"], amt, "PENDING", "", app=True, hold=True)
        else:
            m = fav_merchant(c, rng.choice(["GROCERY", "PHARMACY", "ELECTRONICS"]))
            r = tx(at(d, 9, 21), c, prim, "DEBIT", "UPI", "MERCHANT", m["merchant_id"], m["upi_id"], amt, "PENDING", "", app=True, hold=True)
        if r and d <= TODAY - timedelta(days=12):
            r["status"] = "FAILED"
            rev = r["ts"] + timedelta(days=rng.randint(3, 8), hours=rng.randint(1, 8))
            if rev <= LATEST:
                tx(rev, c, prim, "CREDIT", "UPI", r["counterparty_type"], r["counterparty_id"], r["counterparty_upi"], amt, "REVERSED",
                   f"UPI REV/{r['utr']}", utr=r["utr"])
    for d in cats.get("atm_cash_not_dispensed", []):
        r, aid = atm_wdl(c, prim, d, amt=rng.choice([2000, 3000, 4000, 5000, 10000]), h=(9, 21))
        if r and d <= TODAY - timedelta(days=10):
            rev = r["ts"] + timedelta(days=rng.randint(6, 9), hours=rng.randint(1, 5))
            if rev <= LATEST:
                tx(rev, c, prim, "CREDIT", "ATM", "ATM", aid, "", r["amount_inr"], "REVERSED", f"ATM REV/{r['utr']}/{aid}", utr=r["utr"])
    for d in cats.get("merchant_refund_not_received", []):
        cat = rng.choice(["ECOM", "ECOM", "FOOD_DELIVERY", "APPAREL"])
        amt = rng.choice([799, 1299, 1899, 2499, 3499, 4999, 6999]) if cat != "FOOD_DELIVERY" else rng.choice([389, 540, 720, 1150])
        merchant_spend(c, prim, d - timedelta(days=rng.randint(0, 3)), cat if cat != "APPAREL" else "ECOM", amount=amt)
    for d in cats.get("unrecognised_charges_fees", []):
        for nm, amt in rng.sample(CHARGES, rng.randint(1, 2)):
            tx(at(d, 0.5, 3), c, prim, "DEBIT", "INTERNAL", "INTERNAL", GL_CHG, "", amt, "SUCCESS", nm)
    for d in cats.get("cheque_bounce_charges", []):
        tx(at(d, 1, 3), c, prim, "DEBIT", "INTERNAL", "INTERNAL", GL_CHG, "", 590.00, "SUCCESS", f"CHQ RTN CHGS INCL GST CHQ {digits(6)}")
    for d in cats.get("card_declined", []):
        merchant_spend(c, prim, d, rng.choice(["GROCERY", "RESTAURANT", "FUEL", "APPAREL"]), channel="CARD_POS", status="FAILED")
    for d in cats.get("neft_imps_delay", []):
        cp = c.get("_fam_out") or family_of(c, "out")
        amt = rng.choice([5000, 10000, 15000, 25000, 40000])
        tx(at(d, 10, 17), c, prim, "DEBIT", "NEFT", "EXTERNAL", cp["ext_id"], "", amt, "SUCCESS",
           f"NEFT/{cp['holder_name'].upper()[:20]}", app=True)


for c in CUSTOMERS:
    gen_customer(c)

# ---- scenario payments (identical to the answer key)
FRAUD = []
for r in S["fraud_rings"]:
    for v in r["victims"]:
        for p in v["fraud_payments"]:
            FRAUD.append((r["ring_id"], v, p))
for p in S["demo_customer"]["fraud_payments_today"]:
    FRAUD.append(("R1", {"customer": S["demo_customer"]["customer"], "recalls_in_complaint": {}, "_demo": True}, p))
_seen = set()
FRAUD = [f for f in FRAUD if not (f[2]["txn_id"] in _seen or _seen.add(f[2]["txn_id"]))]
FRAUD_ROWS = {}
for ring_id, v, p in FRAUD:
    c, a = CUST[p["from_customer_id"]], ACCT[p["from_account"]]
    row = tx(datetime.fromisoformat(p["ts"]), c, a, "DEBIT", p["channel"], "EXTERNAL", p["to_ext_id"], p["to_upi"], p["amount_inr"],
             "SUCCESS", p["upi_remark"], app=True, txn_id=p["txn_id"], utr=p["utr"], fixed=True)
    assert row is not None, p
    row["_grp"] = ring_id
    FRAUD_ROWS[p["txn_id"]] = row

# ----------------------------------------------------------------------------- devices & sessions
DEVICES = []
DEV_OF = defaultdict(list)


def add_device(c, primary, first_seen, model=None):
    m = model or rng.choices(PHONES, [p[2] for p in PHONES])[0]
    ver = rng.choices([v[0] for v in APP_VERSIONS], [v[1] for v in APP_VERSIONS])[0] if primary else rng.choice(["5.9.8", "5.6.2", "5.2.0", "4.9.8"])
    d = {"device_id": uniq(lambda: "DEV" + "".join(rng.choice("0123456789ABCDEF") for _ in range(8))), "customer_id": c["customer_id"],
         "device_model": m[0], "os": m[1], "app_version": ver, "first_seen": first_seen, "last_seen": None,
         "is_primary": primary, "_sessions": []}
    DEVICES.append(d)
    DEV_OF[c["customer_id"]].append(d)
    return d


for c in CUSTOMERS:
    if not c["_app"]:
        continue
    since = date.fromisoformat(c["customer_since"])
    lo = max(since, date(2020, 6, 1))
    if not c["_special"] and rng.random() < 0.2:
        old = add_device(c, False, at(rand_date(lo, TODAY - timedelta(days=200)), 9, 21))
        c["_switch"] = at(rand_date(W0 + timedelta(days=7), TODAY - timedelta(days=10)), 9, 21)
        prim = add_device(c, True, c["_switch"])
        c["_old_dev"] = old
    else:
        if rng.random() < 0.15:
            old = add_device(c, False, at(rand_date(lo, TODAY - timedelta(days=500)), 9, 21))
            old["last_seen"] = at(rand_date(date.fromisoformat(old["first_seen"].date().isoformat()) + timedelta(days=30), W0 - timedelta(days=20)), 9, 21)
        prim = add_device(c, True, at(rand_date(lo, W0 - timedelta(days=15)), 9, 21))
    c["_prim_dev"] = prim


def device_at(c, t):
    if c.get("_switch") and t < c["_switch"]:
        return c["_old_dev"]
    return c["_prim_dev"]


SESS = []


def rand_ip(c):
    return rng.choice(c["_ips"]) if rng.random() < 0.85 else f"{rng.choice(['192.0.2', '198.51.100', '203.0.113'])}.{rng.randint(1, 254)}"


def new_session(c, dev, start, end, auth=None, new_dev=False, remote="", screen=False, ip=None, ip_city=None):
    start = max(start, W0_DT)
    end = min(end, LATEST)
    if ip_city is None:
        ip_city = c["city"] if rng.random() < 0.94 else rng.choice([x[0] for x in CITIES if x[0] != c["city"]])
    s = {"session_id": uniq(lambda: "SES" + digits(10)), "customer_id": c["customer_id"], "device_id": dev["device_id"],
         "started_at": start, "ended_at": end, "ip_address": ip or rand_ip(c), "ip_city": ip_city,
         "auth_method": auth or rng.choices(["BIOMETRIC", "MPIN", "PASSWORD_OTP"], [50, 42, 8])[0],
         "new_device": new_dev, "remote_access_app_detected": remote, "screen_share_detected": screen, "_dev": dev}
    SESS.append(s)
    dev["_sessions"].append(s)
    return s


# fraud sessions first
by_victim = defaultdict(list)
for ring_id, v, p in FRAUD:
    by_victim[p["from_customer_id"]].append((ring_id, v, FRAUD_ROWS[p["txn_id"]]))
R2_TV = {}
for r in S["fraud_rings"]:
    if r["ring_id"] == "R2":
        for v in r["victims"]:
            R2_TV[v["customer"]["customer_id"]] = "teamviewer" in json.dumps(v["recalls_in_complaint"]).lower()
SCAM_IPS = [f"203.0.113.{rng.randint(150, 250)}" for _ in range(2)]
FRAUD_WINDOWS = defaultdict(list)
for cid, items in by_victim.items():
    c = CUST[cid]
    items.sort(key=lambda x: x[2]["ts"])
    clusters, cur = [], [items[0]]
    for it in items[1:]:
        if (it[2]["ts"] - cur[-1][2]["ts"]) <= timedelta(minutes=60):
            cur.append(it)
        else:
            clusters.append(cur)
            cur = [it]
    clusters.append(cur)
    ring_id = items[0][0]
    new_dev_obj = None
    for cl in clusters:
        first, last = cl[0][2]["ts"], cl[-1][2]["ts"]
        demo = cl[0][1].get("_demo")
        if demo:
            start = datetime.fromisoformat(S["demo_customer"]["fraud_session_today"]["start"])
            end = min(last + timedelta(seconds=rng.randint(150, 300)), LATEST - timedelta(seconds=30))
        elif ring_id in ("R1", "R2"):
            start = first - timedelta(seconds=rng.randint(6 * 60, 16 * 60))
            end = last + timedelta(seconds=rng.randint(3 * 60, 9 * 60))
        else:
            start = first - timedelta(seconds=rng.randint(60, 240))
            end = last + timedelta(seconds=rng.randint(60, 240))
        if ring_id == "R1":
            s = new_session(c, c["_prim_dev"], start, end, auth="MPIN", remote=S["demo_customer"]["fraud_session_today"]["remote_access_app_detected"] if demo else "AnyDesk",
                            screen=True, ip_city=c["city"], ip=c["_ips"][0])
        elif ring_id == "R2" and R2_TV.get(cid):
            s = new_session(c, c["_prim_dev"], start, end, auth="MPIN", remote="TeamViewer QuickSupport", screen=True, ip_city=c["city"], ip=c["_ips"][0])
        elif ring_id == "R2":
            if new_dev_obj is None:
                new_dev_obj = add_device(c, False, start, model=rng.choice([p for p in PHONES if p[0] in ("Redmi 13C", "Galaxy M14", "Nokia G42")]))
            s = new_session(c, new_dev_obj, start, end, auth="PASSWORD_OTP", new_dev=True, ip=rng.choice(SCAM_IPS),
                            ip_city=rng.choice([x for x in ("Kolkata", "Delhi", "Lucknow") if x != c["city"]]))
        else:
            s = new_session(c, c["_prim_dev"], start, end, auth=rng.choice(["BIOMETRIC", "MPIN"]), ip_city=c["city"], ip=c["_ips"][0])
        for _, _, row in cl:
            row["session_id"], row["device_id"] = s["session_id"], s["device_id"]
        FRAUD_WINDOWS[cid].append((s["started_at"], s["ended_at"]))

# drop ordinary app activity of those customers that would overlap their scenario sessions
drop = set()
for row in TX:
    if row["_fixed"] or row["customer_id"] not in FRAUD_WINDOWS:
        continue
    for a, b in FRAUD_WINDOWS[row["customer_id"]]:
        if a - timedelta(minutes=45) <= row["ts"] <= b + timedelta(minutes=45):
            drop.add(id(row))
            if row["_pair"] is not None:
                drop.add(id(row["_pair"]))
TX = [r for r in TX if id(r) not in drop]

# ordinary sessions: cluster app-initiated debits
app_tx = defaultdict(list)
for row in TX:
    if row["_app"] and not row["_fixed"] and CUST[row["customer_id"]]["_app"]:
        app_tx[row["customer_id"]].append(row)
for cid, rows in app_tx.items():
    c = CUST[cid]
    rows.sort(key=lambda r: r["ts"])
    clusters, cur = [], [rows[0]]
    for r in rows[1:]:
        if r["ts"] - cur[-1]["ts"] <= timedelta(minutes=15) and device_at(c, r["ts"]) is device_at(c, cur[0]["ts"]):
            cur.append(r)
        else:
            clusters.append(cur)
            cur = [r]
    clusters.append(cur)
    for cl in clusters:
        start = cl[0]["ts"] - timedelta(seconds=rng.randint(15, 240))
        end = cl[-1]["ts"] + timedelta(seconds=rng.randint(20, 300))
        dev = device_at(c, cl[0]["ts"])
        s = new_session(c, dev, start, end)
        for r in cl:
            r["session_id"], r["device_id"] = s["session_id"], dev["device_id"]
for row in TX:  # app flag without an app user -> not app initiated
    if row["_app"] and not row["session_id"]:
        row["_app"] = False


def near_fraud(cid, t, hours=3):
    return any(a - timedelta(hours=hours) <= t <= b + timedelta(hours=hours) for a, b in FRAUD_WINDOWS.get(cid, []))


# browse-only sessions (balance checks, statements, etc.)
for c in CUSTOMERS:
    if not c["_app"]:
        continue
    k = poisson(BROWSE_MEAN * (0.7 if c["segment"] == "senior_citizen" else 1.0))
    if not c["_prim_dev"]["_sessions"]:
        k = max(k, 1)
    made = 0
    tries = 0
    while made < k and tries < 20:
        tries += 1
        t = at(rng.choice(DAYS), 7, 23.5)
        if near_fraud(c["customer_id"], t):
            continue
        dev = device_at(c, t)
        new_session(c, dev, t, t + timedelta(seconds=rng.randint(25, 600)))
        made += 1
    if not c["_prim_dev"]["_sessions"]:
        t = at(rand_date(max(W0, (c.get("_switch") or W0_DT).date()), TODAY - timedelta(days=1)), 8, 22)
        if c.get("_switch") and t < c["_switch"]:
            t = c["_switch"] + timedelta(minutes=5)
        new_session(c, c["_prim_dev"], t, t + timedelta(seconds=rng.randint(25, 400)))

# a handful of harmless remote-support detections on browse sessions of ordinary customers
_plain = [s for s in SESS if not CUST[s["customer_id"]]["_special"] and not s["remote_access_app_detected"]]
_txn_sess = {r["session_id"] for r in TX if r["session_id"]}
for s in rng.sample([s for s in _plain if s["session_id"] not in _txn_sess], 5):
    s["remote_access_app_detected"] = rng.choice(["AnyDesk", "TeamViewer QuickSupport"])

# device switch: first session on the new phone is a new-device login
for c in CUSTOMERS:
    if c.get("_switch"):
        ss = sorted(c["_prim_dev"]["_sessions"], key=lambda s: s["started_at"])
        if ss:
            ss[0]["new_device"], ss[0]["auth_method"] = True, "PASSWORD_OTP"
            c["_prim_dev"]["first_seen"] = min(c["_prim_dev"]["first_seen"], ss[0]["started_at"])
for d in DEVICES:
    if d["_sessions"]:
        d["last_seen"] = max(s["ended_at"] for s in d["_sessions"])
        d["first_seen"] = min(d["first_seen"], min(s["started_at"] for s in d["_sessions"]))
    elif d["last_seen"] is None:
        c = CUST[d["customer_id"]]
        d["last_seen"] = (c["_switch"] - timedelta(hours=rng.randint(2, 72))) if c.get("_switch") else d["first_seen"] + timedelta(days=rng.randint(30, 300))
        d["last_seen"] = max(d["last_seen"], d["first_seen"])

# ----------------------------------------------------------------------------- balances
TX.sort(key=lambda r: (r["ts"], r["txn_id"]))
by_acct = defaultdict(list)
for r in TX:
    by_acct[r["account_number"]].append(r)


def effect(r):
    if r["status"] in ("SUCCESS", "REVERSED", "PENDING") or r["_hold"]:
        return r["amount_inr"] if r["direction"] == "CREDIT" else -r["amount_inr"]
    return 0.0


OPEN_BASE = {"salaried": 9.8, "business": 11.4, "self_employed": 10.4, "homemaker": 9.2, "student": 8.0, "senior_citizen": 11.0}
for a in ACCOUNTS:
    c = CUST[a["customer_id"]]
    rows = by_acct.get(a["account_number"], [])
    run, low = 0.0, 0.0
    for r in rows:
        run += effect(r)
        low = min(low, run)
    base = rng.lognormvariate(OPEN_BASE[c["segment"]] - (1.2 if not a["_primary"] else 0), 0.9)
    bal = round(base + (-low) + rng.uniform(150, 2500), 2)
    for r in rows:
        bal = round(bal + effect(r), 2)
        r["balance_after_inr"] = bal
    a["current_balance_inr"] = bal
    # daily UPI limit must cover the largest UPI day actually seen
    daily = defaultdict(float)
    for r in rows:
        if r["channel"] == "UPI" and r["direction"] == "DEBIT" and effect(r) != 0:
            daily[r["ts"].date()] += r["amount_inr"]
    need = max(daily.values()) if daily else 0
    if a["upi_id"] and (a["daily_upi_limit_inr"] == "" or a["daily_upi_limit_inr"] < need):
        a["daily_upi_limit_inr"] = next(t for t in (10000, 25000, 50000, 100000, 200000) if t >= need)

# ----------------------------------------------------------------------------- fraud intel feed
INTEL = []


def intel_row(source, txn_ts, frm, to="", exit_type="", exit_city="", amount=0):
    lo, hi = txn_ts + timedelta(hours=1), min(txn_ts + timedelta(hours=48), LATEST)
    rep = hi if lo > hi else lo + timedelta(seconds=rng.randint(0, int((hi - lo).total_seconds())))
    INTEL.append({"intel_id": uniq(lambda: f"FRI-{rng.randint(1000000, 9999999)}"), "source": source, "reported_at": rep,
                  "from_ext_id": frm, "to_ext_id": to, "exit_type": exit_type, "exit_city": exit_city, "amount_inr": amount, "txn_ts": txn_ts})


for r in S["fraud_rings"]:
    for t in r["mule_transfers"]:
        intel_row(rng.choice(["NPCI_FRM_ALERT", "NPCI_FRM_ALERT", "PARTNER_BANK_ALERT"]), datetime.fromisoformat(t["ts"]),
                  t["from_ext_id"], to=t["to_ext_id"], amount=t["amount_inr"])
    for e in r["cash_out_events"]:
        intel_row(rng.choice(["PARTNER_BANK_ALERT", "PARTNER_BANK_ALERT", "NCRP_INTIMATION"]), datetime.fromisoformat(e["ts"]),
                  e["from_ext_id"], exit_type=e["exit_type"], exit_city=e["city"], amount=e["amount_inr"])
N_SCEN_INTEL = len(INTEL)
OTHER = []
for i in range(44):
    if rng.random() < 0.6:
        OTHER.append(new_cpty(person_name(), "individual", date(2016, 1, 1), date(2026, 8, 1), kind="intel_only"))
    else:
        OTHER.append(new_cpty(rng.choice(["Star Mobile Point", "Laxmi Enterprises", "New India Traders", "Digital Seva Kendra", "Sunrise Enterprises",
                                          "Metro Traders", "Jai Hind Enterprises", "Bharat Online Services", "Sai Communication", "Excel Trading Co",
                                          "Maruti Enterprises", "Golden Traders"]) + rng.choice(["", " & Co", " Services"]),
                              "proprietorship", date(2018, 1, 1), date(2026, 8, 1), kind="intel_only"))
_used_biz = [b for b in BIZ]
for i in range(80):
    ts = at(rng.choice(DAYS[:-1]), 0, 23.9)
    frm = rng.choice(OTHER)["ext_id"] if (i >= 5) else rng.choice(_used_biz)["ext_id"]
    amt = rng.choice([int(rng.uniform(1500, 95000)), rng.choice([5000, 9999, 10000, 20000, 25000, 49999, 50000])])
    if rng.random() < 0.3:
        intel_row(rng.choice(["PARTNER_BANK_ALERT", "NCRP_INTIMATION"]), ts, frm,
                  exit_type=rng.choice(["ATM_CASH_WITHDRAWAL", "CARDLESS_CASH_WITHDRAWAL", "CRYPTO_EXCHANGE_TRANSFER"]),
                  exit_city=rng.choice(["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Kolkata", "Ahmedabad", "Surat", "Patna"]), amount=amt)
    else:
        to = rng.choice([o for o in OTHER if o["ext_id"] != frm])["ext_id"]
        intel_row(rng.choice(["NPCI_FRM_ALERT", "PARTNER_BANK_ALERT", "NCRP_INTIMATION"]), ts, frm, to=to, amount=amt)
INTEL.sort(key=lambda r: (r["reported_at"], r["intel_id"]))

# ----------------------------------------------------------------------------- counterparty first_seen
seen = {}
for r in TX:
    if r["counterparty_type"] in ("EXTERNAL", "EMPLOYER"):
        d = r["ts"].date()
        seen[r["counterparty_id"]] = min(seen.get(r["counterparty_id"], d), d)
for r in INTEL:
    for k in ("from_ext_id", "to_ext_id"):
        if r[k]:
            d = r["reported_at"].date()
            seen[r[k]] = min(seen.get(r[k], d), d)
for ext, row in list(CPTY.items()):
    if ext not in seen:
        del CPTY[ext]  # never referenced anywhere -> not in our data
        continue
    first = seen[ext]
    opened = date.fromisoformat(row["account_opened_on"])
    if row.get("_recurring") and rng.random() < 0.85:
        lo = opened + timedelta(days=30)
        hi = min(first, W0 - timedelta(days=1))
        first = rand_date(lo, hi) if lo < hi else first
    row["first_seen_in_our_data"] = max(first, opened).isoformat()

# ----------------------------------------------------------------------------- write
os.makedirs(OUT, exist_ok=True)


def write(name, cols, rows, conv=None):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            out = []
            for k in cols:
                v = r.get(k, "")
                if conv and k in conv:
                    v = conv[k](v)
                elif isinstance(v, bool):
                    v = "true" if v else "false"
                elif isinstance(v, datetime):
                    v = iso(v)
                elif v is None:
                    v = ""
                out.append(v)
            w.writerow(out)
    return len(rows)


COUNTS = {}
COUNTS["customers.csv"] = write("customers.csv", CUST_COLS, CUSTOMERS)
ACC_COLS = ["account_number", "customer_id", "account_type", "branch", "ifsc", "opened_on", "status", "current_balance_inr", "upi_id", "daily_upi_limit_inr"]
COUNTS["accounts.csv"] = write("accounts.csv", ACC_COLS, ACCOUNTS, {"current_balance_inr": fmt_amt})
CARD_COLS = ["card_id", "account_number", "card_type", "network", "masked_pan", "status", "issued_on", "expiry_mm_yy", "international_enabled"]
COUNTS["cards.csv"] = write("cards.csv", CARD_COLS, CARDS)
DEV_COLS = ["device_id", "customer_id", "device_model", "os", "app_version", "first_seen", "last_seen", "is_primary"]
COUNTS["devices.csv"] = write("devices.csv", DEV_COLS, DEVICES)
SESS.sort(key=lambda s: (s["started_at"], s["session_id"]))
SESS_COLS = ["session_id", "customer_id", "device_id", "started_at", "ended_at", "ip_address", "ip_city", "auth_method", "new_device",
             "remote_access_app_detected", "screen_share_detected"]
COUNTS["login_sessions.csv"] = write("login_sessions.csv", SESS_COLS, SESS)
MER_COLS = ["merchant_id", "merchant_name", "mcc", "category", "city", "upi_id"]
COUNTS["merchants.csv"] = write("merchants.csv", MER_COLS, MERCHANTS)
CP_COLS = ["ext_id", "holder_name", "holder_type", "bank", "ifsc", "account_number", "upi_id", "account_opened_on", "first_seen_in_our_data"]
cp_rows = list(CPTY.values())
rng.shuffle(cp_rows)
COUNTS["counterparties.csv"] = write("counterparties.csv", CP_COLS, cp_rows)
TX_COLS = ["txn_id", "utr", "ts", "customer_id", "account_number", "direction", "channel", "counterparty_type", "counterparty_id",
           "counterparty_upi", "amount_inr", "balance_after_inr", "status", "remarks", "device_id", "session_id"]
COUNTS["transactions.csv"] = write("transactions.csv", TX_COLS, TX, {"amount_inr": fmt_amt, "balance_after_inr": fmt_amt})
INTEL_COLS = ["intel_id", "source", "reported_at", "from_ext_id", "to_ext_id", "exit_type", "exit_city", "amount_inr", "txn_ts"]
COUNTS["fraud_intel_feed.csv"] = write("fraud_intel_feed.csv", INTEL_COLS, INTEL, {"amount_inr": fmt_amt})

README = f"""# Sahyadri Bank - structured core-banking export

Synthetic, fictional data (generated by `data/generate_structured.py`, seed 20260926). Data window
{W0.isoformat()} to {S['latest_allowed_timestamp']}. All timestamps are ISO 8601 in IST (`+05:30`); dates are `YYYY-MM-DD`.
Amounts are INR (paise shown only where non-zero). Booleans are `true` / `false`. Blank = not applicable / not captured.

| File | Rows | Grain |
|---|---:|---|
""" + "\n".join(f"| `{k}` | {v:,} | " + {
    "customers.csv": "one row per customer (CIF)",
    "accounts.csv": "one row per deposit account",
    "cards.csv": "one row per card ever issued on an account (current and past)",
    "devices.csv": "one row per mobile-banking device binding",
    "login_sessions.csv": "one row per mobile-banking login session",
    "merchants.csv": "one row per merchant / biller in the acquiring & BBPS master",
    "counterparties.csv": "one row per external (other-bank) account seen in payments or intel",
    "transactions.csv": "one row per ledger posting on a Sahyadri Bank account",
    "fraud_intel_feed.csv": "one row per inter-bank / NPCI / NCRP intelligence record about external accounts",
}[k] + " |" for k, v in COUNTS.items()) + """

## customers.csv
| Column | Meaning |
|---|---|
| customer_id | CIF id `C000001`-`C002000` (PK) |
| full_name, gender (F/M), dob, age | KYC demographics; age in completed years as on 2026-09-26 |
| phone | registered mobile `+91 5XXXX XXXXX` (fictional range) |
| email | registered e-mail (`@example.com`) |
| city, state, pincode | communication address |
| preferred_language | `en`, `hi`, `mr` or `hinglish` - language the customer prefers for communication |
| segment | `salaried`, `self_employed`, `business`, `homemaker`, `student`, `senior_citizen` |
| customer_since | CIF creation date |
| kyc_status | `FULL`, `MIN_KYC` (small account, limited KYC), `RE_KYC_DUE` (periodic re-KYC pending) |
| risk_rating | AML customer risk category `LOW` / `MEDIUM` / `HIGH` |

## accounts.csv
| Column | Meaning |
|---|---|
| account_number | 14-digit account number (PK) |
| customer_id | FK -> customers |
| account_type | `SAVINGS`, `SALARY`, `SENIOR_SAVINGS`, `CURRENT` |
| branch, ifsc | home branch and its IFSC (`SAHY0` + 6 digits, one per branch) |
| opened_on | account opening date |
| status | `ACTIVE`, `DORMANT` (no customer-induced activity), `FROZEN` (debit freeze) |
| current_balance_inr | ledger balance after the last posting in transactions.csv |
| upi_id | VPA linked to the account (blank if none) |
| daily_upi_limit_inr | customer-set daily UPI limit (blank if no VPA) |

## cards.csv
| Column | Meaning |
|---|---|
| card_id | PK |
| account_number | FK -> accounts (for CREDIT cards: the linked repayment account) |
| card_type | `DEBIT` / `CREDIT` |
| network | `RuPay`, `Visa`, `Mastercard` |
| masked_pan | first 4 + last 4 digits |
| status | `ACTIVE`, `HOTLISTED` (blocked on request), `EXPIRED`, `REISSUED` (replaced by a newer card) |
| issued_on, expiry_mm_yy | issue date and expiry (MM/YY) |
| international_enabled | international usage switched on |

## devices.csv
| Column | Meaning |
|---|---|
| device_id | device binding id (PK) |
| customer_id | FK -> customers |
| device_model, os, app_version | handset and Sahyadri app build at last login |
| first_seen, last_seen | first / last login timestamp on this device |
| is_primary | the customer's current bound device |

## login_sessions.csv
| Column | Meaning |
|---|---|
| session_id | PK |
| customer_id, device_id | FK -> customers, devices (device belongs to the customer) |
| started_at, ended_at | session start / end |
| ip_address, ip_city | source IP (documentation ranges only) and its geo-IP city |
| auth_method | `MPIN`, `BIOMETRIC`, `PASSWORD_OTP` (password + SMS OTP, used for device binding) |
| new_device | first login from a device not previously bound |
| remote_access_app_detected | name of a screen-sharing / remote-control app found running by the app's RASP check (blank = none) |
| screen_share_detected | the screen was being shared / mirrored during the session |

## merchants.csv
| Column | Meaning |
|---|---|
| merchant_id | PK; referenced by transactions with counterparty_type MERCHANT or BILLER |
| merchant_name, mcc, category, city | merchant master data (fictional businesses and billers) |
| upi_id | merchant VPA |

## counterparties.csv
| Column | Meaning |
|---|---|
| ext_id | PK; referenced by transactions (EXTERNAL / EMPLOYER) and fraud_intel_feed |
| holder_name, holder_type | name as per beneficiary bank; `individual`, `proprietorship`, `company` |
| bank, ifsc, account_number | beneficiary bank details (fictional banks) |
| upi_id | beneficiary VPA if known |
| account_opened_on | account opening date as reported by the beneficiary bank |
| first_seen_in_our_data | date this account first appeared in Sahyadri Bank's records (payments or intel) |

## transactions.csv
| Column | Meaning |
|---|---|
| txn_id | `TXN` + 12 digits (PK) |
| utr | UTR / RRN (12-digit RRN for UPI, IMPS, BBPS, card and ATM; `xxxxN...` for NEFT; `SAHYR...` for RTGS; `NACH...`; blank for internal postings). A reversal carries the utr of the original debit |
| ts | posting timestamp |
| customer_id, account_number | FK -> customers, accounts |
| direction | `DEBIT` / `CREDIT` |
| channel | `UPI`, `IMPS`, `NEFT`, `RTGS`, `CARD_POS`, `CARD_ECOM`, `ATM`, `NACH`, `BBPS`, `INTERNAL` |
| counterparty_type | `MERCHANT`/`BILLER` -> merchants.merchant_id; `EXTERNAL`/`EMPLOYER` -> counterparties.ext_id; `INTERNAL` -> another accounts.account_number or a GL code (`SAHY-GL-INTEREST`, `SAHY-GL-CHARGES`); `ATM` -> ATM terminal id (`SHY..` own ATMs, others via NFS) |
| counterparty_id | see above |
| counterparty_upi | payee / payer VPA for UPI postings |
| amount_inr | amount |
| balance_after_inr | running ledger balance of the account after this posting (never negative) |
| status | `SUCCESS`; `FAILED` (declined - balance unchanged, except where the account was debited despite the failure: then balance_after reflects the debit and a later `REVERSED` credit with the same utr gives it back); `REVERSED` (reversal credit); `PENDING` (debited, awaiting switch confirmation) |
| remarks | UPI note typed by the customer, or the system narration |
| device_id, session_id | FK -> devices, login_sessions for postings initiated in the Sahyadri mobile app (blank otherwise, e.g. third-party UPI apps, cards, NACH, inward credits) |

## fraud_intel_feed.csv
| Column | Meaning |
|---|---|
| intel_id | PK |
| source | `NPCI_FRM_ALERT`, `PARTNER_BANK_ALERT`, `NCRP_INTIMATION` |
| reported_at | when the record reached Sahyadri Bank |
| from_ext_id | FK -> counterparties: account the money moved out of |
| to_ext_id | FK -> counterparties: receiving account (blank for a cash-out record) |
| exit_type, exit_city | for cash-out records: `ATM_CASH_WITHDRAWAL`, `CARDLESS_CASH_WITHDRAWAL`, `CRYPTO_EXCHANGE_TRANSFER` and the city |
| amount_inr, txn_ts | amount and time of the reported movement |
"""
with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as fh:
    fh.write(README)


# ----------------------------------------------------------------------------- validation
def validate():
    problems = []

    def load(name):
        with open(os.path.join(OUT, name), encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    T = {n: load(n) for n in COUNTS}
    pk = {"customers.csv": "customer_id", "accounts.csv": "account_number", "cards.csv": "card_id", "devices.csv": "device_id",
          "login_sessions.csv": "session_id", "merchants.csv": "merchant_id", "counterparties.csv": "ext_id",
          "transactions.csv": "txn_id", "fraud_intel_feed.csv": "intel_id"}
    for n, k in pk.items():
        vals = [r[k] for r in T[n]]
        if len(vals) != len(set(vals)) or "" in vals:
            problems.append(f"{n}: duplicate/blank {k}")
    cust = {r["customer_id"]: r for r in T["customers.csv"]}
    acct = {r["account_number"]: r for r in T["accounts.csv"]}
    dev = {r["device_id"]: r for r in T["devices.csv"]}
    ses = {r["session_id"]: r for r in T["login_sessions.csv"]}
    mer = {r["merchant_id"] for r in T["merchants.csv"]}
    cp = {r["ext_id"]: r for r in T["counterparties.csv"]}
    if len(cust) != 2000 or set(cust) != {f"C{i:06d}" for i in range(1, 2001)}:
        problems.append("customers: id range")
    for a in T["accounts.csv"]:
        if a["customer_id"] not in cust:
            problems.append(f"account FK {a['account_number']}")
        if a["ifsc"] != IFSC.get(a["branch"]):
            problems.append(f"ifsc {a['account_number']}")
    for cd in T["cards.csv"]:
        if cd["account_number"] not in acct:
            problems.append(f"card FK {cd['card_id']}")
    for d in T["devices.csv"]:
        if d["customer_id"] not in cust:
            problems.append(f"device FK {d['device_id']}")
    ip_ok = re.compile(r"^(192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}$")
    for s in T["login_sessions.csv"]:
        if s["device_id"] not in dev or dev[s["device_id"]]["customer_id"] != s["customer_id"]:
            problems.append(f"session device FK {s['session_id']}")
        if not ip_ok.match(s["ip_address"]):
            problems.append(f"ip {s['session_id']}")
        if s["ended_at"] < s["started_at"]:
            problems.append(f"session order {s['session_id']}")
    bal_prev = {}
    for r in T["transactions.csv"]:
        if r["customer_id"] not in cust or acct.get(r["account_number"], {}).get("customer_id") != r["customer_id"]:
            problems.append(f"txn acct/cust FK {r['txn_id']}")
        t, cid = r["counterparty_type"], r["counterparty_id"]
        ok = (t in ("MERCHANT", "BILLER") and cid in mer) or (t in ("EXTERNAL", "EMPLOYER") and cid in cp) or \
             (t == "INTERNAL" and (cid in acct or cid in (GL_INT, GL_CHG))) or (t == "ATM" and cid)
        if not ok:
            problems.append(f"txn counterparty FK {r['txn_id']} {t} {cid}")
        if r["session_id"]:
            s = ses.get(r["session_id"])
            if not s or s["customer_id"] != r["customer_id"] or s["device_id"] != r["device_id"] or not (s["started_at"] <= r["ts"] <= s["ended_at"]):
                problems.append(f"txn session {r['txn_id']}")
        if float(r["balance_after_inr"]) < 0:
            problems.append(f"negative balance {r['txn_id']}")
        bal_prev[r["account_number"]] = r["balance_after_inr"]
    for a, b in bal_prev.items():
        if abs(float(b) - float(acct[a]["current_balance_inr"])) > 0.01:
            problems.append(f"current balance {a}")
    for r in T["fraud_intel_feed.csv"]:
        for k in ("from_ext_id", "to_ext_id"):
            if r[k] and r[k] not in cp:
                problems.append(f"intel FK {r['intel_id']} {r[k]}")
        if r["reported_at"] < r["txn_ts"]:
            problems.append(f"intel order {r['intel_id']}")
    # scenario items identical
    for cid, sc in SPECIAL.items():
        row = cust.get(cid)
        for k in CUST_COLS:
            if k in sc and str(sc[k]) != row[k]:
                problems.append(f"special customer {cid} field {k}")
        a = acct.get(sc["account_number"])
        if not a or a["customer_id"] != cid or a["upi_id"] != sc["upi_id"] or a["account_type"] != sc["account_type"]:
            problems.append(f"special account {cid}")
        if not any(cd["account_number"] == sc["account_number"] and cd["card_type"] == "DEBIT" and cd["masked_pan"].endswith(sc["debit_card_last4"])
                   for cd in T["cards.csv"]):
            problems.append(f"special card {cid}")
    txr = {r["txn_id"]: r for r in T["transactions.csv"]}
    for ring_id, v, p in FRAUD:
        r = txr.get(p["txn_id"])
        if not r:
            problems.append(f"missing payment {p['txn_id']}")
            continue
        exp = {"utr": p["utr"], "ts": p["ts"], "customer_id": p["from_customer_id"], "account_number": p["from_account"],
               "channel": p["channel"], "counterparty_id": p["to_ext_id"], "counterparty_upi": p["to_upi"], "remarks": p["upi_remark"],
               "status": "SUCCESS", "direction": "DEBIT"}
        for k, val in exp.items():
            if r[k] != val:
                problems.append(f"payment {p['txn_id']} {k}: {r[k]!r} != {val!r}")
        if abs(float(r["amount_inr"]) - p["amount_inr"]) > 1e-6:
            problems.append(f"payment amount {p['txn_id']}")
        s = ses.get(r["session_id"])
        if not s:
            problems.append(f"payment without session {p['txn_id']}")
            continue
        if ring_id == "R1" and not (s["remote_access_app_detected"] == "AnyDesk" and s["screen_share_detected"] == "true"):
            problems.append(f"R1 session attrs {p['txn_id']}")
        if ring_id == "R2" and not (s["remote_access_app_detected"] == "TeamViewer QuickSupport" or s["new_device"] == "true"):
            problems.append(f"R2 session attrs {p['txn_id']}")
        if ring_id in ("R3", "R4") and (s["remote_access_app_detected"] or s["new_device"] == "true"):
            problems.append(f"R3/R4 session attrs {p['txn_id']}")
    ds = S["demo_customer"]["fraud_session_today"]
    demo_s = {txr[p["txn_id"]]["session_id"] for p in S["demo_customer"]["fraud_payments_today"]}
    if len(demo_s) != 1 or ses[demo_s.pop()]["started_at"] != ds["start"]:
        problems.append("demo session start")
    for r in S["fraud_rings"]:
        for m in r["mule_accounts"]:
            row = cp.get(m["ext_id"])
            if not row or any(row[k] != str(v) for k, v in m.items()):
                problems.append(f"mule account {m['ext_id']}")
    feed = Counter((r["from_ext_id"], r["to_ext_id"], r["exit_type"], r["exit_city"], float(r["amount_inr"]), r["txn_ts"]) for r in T["fraud_intel_feed.csv"])
    want = Counter()
    for r in S["fraud_rings"]:
        for t in r["mule_transfers"]:
            want[(t["from_ext_id"], t["to_ext_id"], "", "", float(t["amount_inr"]), t["ts"])] += 1
        for e in r["cash_out_events"]:
            want[(e["from_ext_id"], "", e["exit_type"], e["city"], float(e["amount_inr"]), e["ts"])] += 1
    if want - feed:
        problems.append(f"intel missing {sum((want - feed).values())}")
    # timestamps, banned words, phones
    ts_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30$")
    banned = re.compile(r"\b(ring|rings|mule|mules|victim|victims|gang|gangs|R[1-4]|G[12])\b|mule|victim|fraud", re.I)
    ring_sub = 0
    for n, rows in T.items():
        for r in rows:
            for k, v in r.items():
                if ts_re.match(v or "") and v > S["latest_allowed_timestamp"]:
                    problems.append(f"{n} {k} later than allowed: {v}")
                if n != "fraud_intel_feed.csv" or k != "source":
                    if banned.search(v or ""):
                        problems.append(f"{n} banned word in {k}: {v}")
                if "ring" in (v or "").lower():
                    ring_sub += 1
    for r in T["customers.csv"]:
        if not re.match(r"^\+91 5\d{4} \d{5}$", r["phone"]):
            problems.append(f"phone {r['customer_id']}")
        if not r["email"].endswith("@example.com"):
            problems.append(f"email {r['customer_id']}")
    phones = [r["phone"] for r in T["customers.csv"]]
    if len(phones) != len(set(phones)):
        problems.append("duplicate phones")
    print("row counts:", json.dumps(COUNTS))
    fr_sessions = {txr[p["txn_id"]]["session_id"] for _, _, p in FRAUD}
    print(f"scenario payments: {len(FRAUD)} in {len(fr_sessions)} sessions; intel rows from scenario: {N_SCEN_INTEL}, "
          f"reported at the cut-off with <1h lag: {sum(1 for r in INTEL if r['reported_at'] - r['txn_ts'] < timedelta(hours=1))}")
    print("substring 'ring' occurrences:", ring_sub)
    print("status mix:", dict(Counter(r["status"] for r in T["transactions.csv"])))
    print("channel mix:", dict(Counter(r["channel"] for r in T["transactions.csv"])))
    print("PROBLEMS:", len(problems))
    for p in problems[:40]:
        print("  -", p)
    return problems


if __name__ == "__main__":
    validate()
