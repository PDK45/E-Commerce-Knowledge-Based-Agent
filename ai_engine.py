import sqlite3
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

print("⏳ Loading AI Model... (this happens only once)")
model = SentenceTransformer('all-MiniLM-L6-v2') 

def get_db_products():
    conn = sqlite3.connect("inventory.db")
    conn.row_factory = sqlite3.Row 
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return [dict(p) for p in products]

products = get_db_products()
descriptions = [f"{p['name']} {p['description']} {p['category']}" for p in products]
product_embeddings = model.encode(descriptions)

def semantic_search(user_query, top_k=5):
    """
    Finds products based on MEANING, not just keywords.
    """
    query_embedding = model.encode([user_query])
    
    scores = cosine_similarity(query_embedding, product_embeddings)[0]
    
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    results = []
    for idx in top_indices:
        item = products[idx]
        item['match_score'] = round(float(scores[idx]), 2)
        if item['match_score'] > 0.25: 
            results.append(item)
            
    return results