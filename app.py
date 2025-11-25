import streamlit as st, json, math, datetime
from pathlib import Path

BASE = Path(__file__).parent
PRODUCTS_FILE = BASE / "products.json"
PREFS_FILE = BASE / "prefs.json"
RULES_FILE = BASE / "rules.json"

st.set_page_config(page_title="Mini E-Commerce KBA - RealWorld Rules", layout="wide")

# --- Load / Save ---
def load_products():
    with open(PRODUCTS_FILE, "r") as f:
        return json.load(f)

def load_prefs():
    if PREFS_FILE.exists():
        with open(PREFS_FILE, "r") as f:
            return json.load(f)
    return {"brand_weights":{}, "category_weights":{}, "price_sensitivity":1.0, "rating_weight":1.0, "brand_loyalty":1.0, "loyalty_points":0}

def save_prefs(prefs):
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)

def load_rules():
    with open(RULES_FILE, "r") as f:
        return json.load(f)

# --- Predicates ---
def Category(p,c): return p.get("category","").lower() == c.lower()
def Brand(p,b): return p.get("brand","").lower() == b.lower()
def Price(p): return p.get("price",0)
def EffectivePrice(p): return Price(p) * (1 - p.get("discount",0)/100)
def Rating(p): return p.get("rating",0)
def Reviews(p): return p.get("reviews",0)
def HasFeature(p,f): return any(f.lower() == t.lower() for t in p.get("tags",[]))
def Stock(p): return p.get("stock",0)
def StockAvailable(p): return Stock(p) > 0
def Discount(p): return p.get("discount",0)
def ShippingTime(p): return p.get("shipping_time_days", 7)

# --- Parse query ---
def parse_query(q):
    qlow = q.lower()
    slots = {"keywords":[], "max_price":None}
    words = [w.strip().replace("₹","").replace(",","") for w in qlow.split()]
    for i,w in enumerate(words):
        if w in ("under","below","less","upto","up","to") and i+1 < len(words):
            try:
                slots["max_price"] = float(words[i+1])
            except:
                pass
    for w in words:
        if w.isdigit() and int(w) > 100:
            slots["max_price"] = float(w)
    slots["keywords"] = [w for w in words if len(w)>2]
    return slots

# --- JSON-based Rule Engine ---
def apply_dynamic_rules(p, user, prefs, ruleset):
    fired = []
    total_weight = 0.0

    for rule in ruleset:
        name = rule.get("name")
        condition = rule.get("condition", "")
        weight = float(rule.get("weight", 1.0))
        desc = rule.get("description", name)

        try:
            # Evaluate condition in a safe context
            ok = eval(condition, {}, {
                "p": p,
                "user": user,
                "prefs": prefs,
                "Category": Category,
                "Brand": Brand,
                "Price": Price,
                "EffectivePrice": EffectivePrice,
                "Rating": Rating,
                "Reviews": Reviews,
                "HasFeature": HasFeature,
                "Stock": Stock,
                "StockAvailable": StockAvailable,
                "Discount": Discount,
                "ShippingTime": ShippingTime,
                "math": math
            })
        except Exception as e:
            ok = False

        if ok:
            fired.append(desc)
            total_weight += weight

    return fired, total_weight

# --- Rule engine (aggregator) ---
def apply_rules(products, user, prefs, filters):
    ruleset = load_rules()
    results = []

    for p in products:
        fired, total_weight = apply_dynamic_rules(p, user, prefs, ruleset)

        # base score
        score = Rating(p) * prefs.get("rating_weight",1.0) + total_weight

        # brand learned boost
        bw = prefs.get("brand_weights",{}).get(p.get("brand"),1.0)
        score *= (1 + 0.1*(bw-1)) * prefs.get("brand_loyalty",1.0)

        # filter penalties
        if filters.get("category") and p.get("category") != filters.get("category"):
            score -= 30
        if filters.get("brand") and p.get("brand") != filters.get("brand"):
            score -= 25

        # budget penalty
        budget = user.get("budget")
        if budget is not None:
            eff = EffectivePrice(p)
            if eff > 1.1 * budget:
                score -= 40

        results.append({"product":p, "score":score, "fired":fired})

    results = sorted(results, key=lambda x: x["score"], reverse=True)
    return results

# --- Cart utils ---
def add_to_cart(item, qty=1):
    cart = st.session_state.get("cart", {})
    pid = str(item["id"])
    if pid in cart:
        cart[pid]["qty"] += qty
    else:
        cart[pid] = {"item":item, "qty":qty}
    st.session_state["cart"] = cart

def remove_from_cart(pid):
    cart = st.session_state.get("cart", {})
    if pid in cart:
        del cart[pid]
    st.session_state["cart"] = cart

def cart_totals():
    cart = st.session_state.get("cart", {})
    subtotal = 0.0
    for v in cart.values():
        price = v["item"]["price"] * (1 - v["item"].get("discount",0)/100)
        subtotal += price * v["qty"]
    tax = subtotal * 0.18
    shipping = 99 if subtotal < 2000 and subtotal>0 else 0
    total = subtotal + tax + shipping
    return {"subtotal":subtotal, "tax":tax, "shipping":shipping, "total":total}

# --- UI ---
st.markdown("<style> .big{font-size:20px;font-weight:700} .muted{color:gray}</style>", unsafe_allow_html=True)
left, right = st.columns([3,1])
with left:
    st.title("Mini E-Commerce KBA — Real-World Rule Engine")
    st.markdown("<div class='muted'>Now powered by JSON-defined rules — editable and explainable.</div>", unsafe_allow_html=True)
with right:
    if st.button("Reset Learned Preferences"):
        prefs = {"brand_weights":{}, "category_weights":{}, "price_sensitivity":1.0, "rating_weight":1.0, "brand_loyalty":1.0, "loyalty_points":0}
        save_prefs(prefs)
        st.success("Preferences reset")

products = load_products()
prefs = load_prefs()

# Sidebar
with st.sidebar:
    st.header("User Inputs & Agent Settings")
    q = st.text_input("What are you looking for?", value="gaming laptop under 100000")
    budget = st.number_input("Budget (₹, 0 for none)", min_value=0, value=0)
    budget = None if budget==0 else float(budget)
    preferred_brand = st.text_input("Preferred brand (optional)", value="")
    interest_category = st.selectbox("Interest category (optional)", options=["Any"] + sorted(list(set([p["category"] for p in products]))))
    if interest_category=="Any": interest_category = None
    min_rating = st.slider("Minimum rating", 3.5, 5.0, 4.0, step=0.1)
    loyalty_points = st.number_input("Your loyalty points", min_value=0, value=prefs.get("loyalty_points",0))

    st.markdown("---")
    st.subheader("Agent Tuning")
    price_sens = st.slider("Price sensitivity", 0.5, 2.0, value=prefs.get("price_sensitivity",1.0))
    rating_w = st.slider("Rating weight", 0.5, 2.0, value=prefs.get("rating_weight",1.0))
    brand_loyal = st.slider("Brand loyalty multiplier", 0.5, 2.0, value=prefs.get("brand_loyalty",1.0))

    if st.button("Save Settings"):
        prefs["price_sensitivity"] = price_sens
        prefs["rating_weight"] = rating_w
        prefs["brand_loyalty"] = brand_loyal
        prefs["loyalty_points"] = int(loyalty_points)
        prefs["preferred_brand_temp"] = preferred_brand
        save_prefs(prefs)
        st.success("Agent settings saved")

    st.markdown("---")
    st.subheader("Cart Summary")
    cart = st.session_state.get("cart", {})
    if cart:
        for pid,entry in cart.items():
            st.write(f"{entry['item']['name']} x {entry['qty']} — ₹{int(entry['item']['price']*(1-entry['item'].get('discount',0)/100))*entry['qty']}")
        totals = cart_totals()
        st.write(f"Subtotal: ₹{int(totals['subtotal'])}")
        if st.button("Checkout"):
            st.success("Simulated checkout complete — thank you!")
            st.session_state["cart"] = {}
    else:
        st.write("_Cart is empty_")
    st.markdown("---")
    st.write("Note: This is an academic demo of a rule-based KB agent. No payment integration.")

# Prepare user and filters
slots = parse_query(q)
user = {
    "budget": budget,
    "preferred_brand": preferred_brand or prefs.get("preferred_brand_temp"),
    "keywords": slots.get("keywords",[]),
    "min_rating": min_rating,
    "interest_category": interest_category
}

filters = {"category": None, "brand": None}
ql = q.lower()
for p in products:
    if p["category"].lower() in ql:
        filters["category"] = p["category"]; break
for p in products:
    if p["brand"].lower() in ql:
        filters["brand"] = p["brand"]; break

# Apply rules
results = apply_rules(products, user, prefs, filters)

# Display Recommendations
st.subheader("Recommended For You (based on rules)")
count = 0
for r in results:
    p = r["product"]
    eff = int(EffectivePrice(p))
    if Rating(p) < user.get("min_rating", 0): continue
    st.markdown(f"### {p['name']} — ₹{eff} {'('+str(p.get('discount'))+'% off)' if p.get('discount') else ''}")
    st.write(f"**Brand:** {p['brand']} | **Category:** {p['category']} | **Rating:** {p['rating']} ({p.get('reviews',0)} reviews) | **Stock:** {p['stock']} | **Ship:** {p.get('shipping_time_days')} days")
    st.write(p.get("description",""))
    cols = st.columns([1,2,1])
    with cols[0]:
        qty = st.number_input(f"qty_{p['id']}", min_value=1, max_value=10, value=1, key=f"qty_{p['id']}")
        if st.button(f"Add to cart {p['id']}", key=f"add_{p['id']}"):
            add_to_cart(p, qty); st.success(f"Added {qty} x {p['name']} to cart")
    with cols[1]:
        if st.button(f"Why {p['id']}?", key=f"why_{p['id']}"):
            fired = r.get("fired",[])
            if fired:
                st.info("Rules fired:\n" + "\n".join(["- " + f for f in fired]))
            else:
                st.info("No specific rule fired; recommended by base scoring.")
            st.write(f"Effective price: ₹{eff}")
    with cols[2]:
        if st.button(f"Like {p['id']}", key=f"like_{p['id']}"):
            bw = prefs.get("brand_weights",{})
            bw[p['brand']] = bw.get(p['brand'],1.0) + 0.4
            prefs["brand_weights"] = bw
            save_prefs(prefs)
            st.success("Preference saved")
    st.markdown("---")
    count += 1
    if count >= 15: break

st.caption("This agent applies multiple realistic rules loaded from rules.json; each product lists which rules fired for explainability.")
