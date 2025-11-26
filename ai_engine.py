import sqlite3
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')
    nltk.download('punkt_tab')

STOP_WORDS = set(stopwords.words('english'))

print("AI Engine is being initialized...")
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

def preprocess_query(text):
    """
    CLASSICAL NLP: Cleans noise using NLTK to improve AI focus.
    """
    tokens = word_tokenize(text.lower())
    
    filtered_tokens = [w for w in tokens if w.isalnum() and w not in STOP_WORDS]
    
    return " ".join(filtered_tokens)

def semantic_search(user_query, top_k=5):
    """
    Hybrid NLP: Uses NLTK for cleaning + Transformers for meaning.
    """
    cleaned_query = preprocess_query(user_query)
    final_query = cleaned_query if len(cleaned_query) > 2 else user_query
    
    query_embedding = model.encode([final_query])
    
    scores = cosine_similarity(query_embedding, product_embeddings)[0]
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    results = []
    for idx in top_indices:
        item = products[idx]
        item['match_score'] = round(float(scores[idx]), 2)
        if item['match_score'] > 0.25: 
            results.append(item)
            
    return results