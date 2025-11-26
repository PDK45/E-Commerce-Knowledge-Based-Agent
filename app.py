import streamlit as st
import json
import math
import ai_engine 
from pathlib import Path

BASE = Path(__file__).parent
PREFS_FILE = BASE / "prefs.json"
RULES_FILE = BASE / "rules.json"

st.set_page_config(page_title="Neuro-Symbolic Supply Chain Twin", layout="wide")

def load_products():
    """
    Loads products from the SQLite database via the AI Engine.
    Also handles data type conversion (SQL stores lists as strings).
    """
    try:
        raw_products = ai_engine.get_db_products()
        for p in raw_products:
            if isinstance(p.get("tags"), str):
                p["tags"] = p["tags"].split(",")
        return raw_products
    except Exception as e:
        st.error(f"Error loading database: {e}. Did you run 'python database.py'?")
        return []

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

def parse_query(q):
    qlow = q.lower()
    slots = {"max_price":None}
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
    return slots

def apply_dynamic_rules(p, user, prefs, ruleset):
    fired = []
    total_weight = 0.0

    for rule in ruleset:
        name = rule.get("name")
        condition = rule.get("condition", "")
        weight = float(rule.get("weight", 1.0))
        reason = rule.get("reason", rule.get("description", name))

        try:
            context = {
                "p": p,
                "product": p,  
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
            }
            ok = eval(condition, {}, context)
        except Exception as e:
            ok = False

        if ok:
            fired.append(reason) 
            total_weight += weight

    return fired, total_weight

def apply_rules(products, user, prefs, filters):
    ruleset = load_rules()
    results = []

    for p in products:
        fired, total_weight = apply_dynamic_rules(p, user, prefs, ruleset)

        score = Rating(p) * prefs.get("rating_weight",1.0) + total_weight

        bw = prefs.get("brand_weights",{}).get(p.get("brand"),1.0)
        score *= (1 + 0.1*(bw-1)) * prefs.get("brand_loyalty",1.0)

        if filters.get("category") and p.get("category") != filters.get("category"):
            score -= 30
        if filters.get("brand") and p.get("brand") != filters.get("brand"):
            score -= 25

        budget = user.get("budget")
        if budget is not None:
            eff = EffectivePrice(p)
            if eff > 1.1 * budget:
                score -= 40
        
        if "match_score" in p:
            score += (p["match_score"] * 20)  

        results.append({"product":p, "score":score, "fired":fired})

    results = sorted(results, key=lambda x: x["score"], reverse=True)
    return results

def add_to_cart(item, qty=1):
    cart = st.session_state.get("cart", {})
    pid = str(item["id"])
    if pid in cart:
        cart[pid]["qty"] += qty
    else:
        cart[pid] = {"item":item, "qty":qty}
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

st.markdown("<style> .big{font-size:20px;font-weight:700} .muted{color:gray} .ai-badge{background-color:#e6f3ff; padding:2px 6px; border-radius:4px; font-size:0.8em; color:#0066cc;}</style>", unsafe_allow_html=True)

left, right = st.columns([3,1])
with left:
    st.title("Neuro-Symbolic Supply Chain Twin 🧠")
    st.markdown("<div class='muted'>Powered by Hybrid AI: <b>Vector Embeddings (NLP)</b> + <b>Rule Engine</b></div>", unsafe_allow_html=True)
with right:
    if st.button("Reset Settings"):
        prefs = {"brand_weights":{}, "category_weights":{}, "price_sensitivity":1.0, "rating_weight":1.0, "brand_loyalty":1.0, "loyalty_points":0}
        save_prefs(prefs)
        st.rerun()

all_products = load_products() 
prefs = load_prefs()

with st.sidebar:
    st.header("Control Panel")
    
    q = st.text_input("Search (Natural Language)", value="device for coding under 100000")
    
    budget_input = st.number_input("Budget Override (₹)", min_value=0, value=0)
    
    if all_products:
        cat_options = ["Any"] + sorted(list(set([p.get("category", "Uncategorized") for p in all_products])))
    else:
        cat_options = ["Any"]
        
    interest_category = st.selectbox("Category Filter", options=cat_options)
    if interest_category=="Any": interest_category = None
    
    min_rating = st.slider("Min Rating", 3.0, 5.0, 4.0, step=0.1)
    
    st.markdown("---")
    st.subheader("Agent Tuning")
    price_sens = st.slider("Price Sensitivity", 0.5, 2.0, value=prefs.get("price_sensitivity",1.0))
    rating_w = st.slider("Rating Weight", 0.5, 2.0, value=prefs.get("rating_weight",1.0))

    if st.button("Save Tuning"):
        prefs["price_sensitivity"] = price_sens
        prefs["rating_weight"] = rating_w
        save_prefs(prefs)
        st.success("Saved!")

    st.markdown("---")
    st.subheader("Cart")
    cart = st.session_state.get("cart", {})
    if cart:
        for pid,entry in cart.items():
            st.write(f"{entry['item']['name']} (x{entry['qty']})")
        totals = cart_totals()
        st.write(f"**Total: ₹{int(totals['total'])}**")
        if st.button("Checkout"):
            st.session_state["cart"] = {}
            st.success("Order Placed!")
            st.rerun()
    else:
        st.write("_Empty_")


slots = parse_query(q)
final_budget = slots.get("max_price") if slots.get("max_price") else (budget_input if budget_input > 0 else None)

products_to_consider = []
ai_search_active = False

if len(q.strip()) > 3 and not q.strip().isdigit():
    ai_results = ai_engine.semantic_search(q, top_k=15)
    
    for p in ai_results:
        if isinstance(p.get("tags"), str):
            p["tags"] = p["tags"].split(",")
            
    products_to_consider = ai_results
    ai_search_active = True
else:
    products_to_consider = all_products

user_context = {
    "budget": final_budget,
    "preferred_brand": prefs.get("preferred_brand_temp"),
    "min_rating": min_rating,
    "interest_category": interest_category
}
filters = {"category": interest_category, "brand": None}

results = apply_rules(products_to_consider, user_context, prefs, filters)

st.divider()

if ai_search_active:
    st.info(f"🤖 AI analyzed meaning: '{q}'. Found {len(results)} relevant items.")
else:
    st.write("Showing all items (No semantic search active).")

count = 0
for r in results:
    p = r["product"]
    score = r["score"]
    
    if Rating(p) < min_rating: continue
    
    eff_price = int(EffectivePrice(p))
    
    with st.container():
        c1, c2, c3 = st.columns([2, 4, 2])
        
        with c1:
            st.markdown(f"### {p['name']}")
            if "match_score" in p:
                confidence = int(p["match_score"] * 100)
                st.markdown(f"<span class='ai-badge'>Match Confidence: {confidence}%</span>", unsafe_allow_html=True)
            st.caption(f"{p['brand']} | {p['category']}")
            
        with c2:
            st.write(p.get("description", "No description"))
            st.write(f"**₹{eff_price}** _({p.get('discount')}% off)_ | ⭐ {p['rating']} | Stock: {p['stock']}")
            
            if st.button(f"Why {p['id']}?", key=f"why_{p['id']}"):
                explanations = []
                
                if "match_score" in p:
                    score_pct = int(p['match_score'] * 100)
                    if score_pct > 30:
                        explanations.append(f"🤖 **AI Match ({score_pct}%):** The product description is semantically similar to your search.")

                if r["fired"]:
                    for rule_desc in r["fired"]:
                        explanations.append(f"✅ **Rule:** {rule_desc}")
                
                eff_price = int(EffectivePrice(p))
                if p.get('discount', 0) > 15:
                     explanations.append(f"💰 **Savings:** High discount of {p['discount']}% applied.")
                if p.get('rating', 0) >= 4.5:
                     explanations.append(f"⭐ **Quality:** Excellent user rating ({p['rating']}/5).")
                if p.get('shipping_time_days', 7) <= 3:
                     explanations.append(f"🚚 **Speed:** Fast shipping available ({p['shipping_time_days']} days).")
                
                if explanations:
                    for exp in explanations:
                        st.write(exp)
                else:
                    st.info("Standard recommendation based on category match.")
                    
        with c3:
            if st.button(f"Add to Cart", key=f"add_{p['id']}"):
                add_to_cart(p)
                st.toast(f"Added {p['name']}")
                
        st.divider()
        
    count += 1
    if count >= 10: break

st.caption("System Architecture: SQLite Database → SentenceTransformers (NLP) → Rule Engine → Streamlit UI")