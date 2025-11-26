import sqlite3
import json

def init_db():
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()
    
    # DROP the old table so we can recreate it with new columns
    cursor.execute("DROP TABLE IF EXISTS products")
    
    # Create table with ALL fields needed for rules
    cursor.execute("""
    CREATE TABLE products (
        id INTEGER PRIMARY KEY,
        name TEXT,
        category TEXT,
        brand TEXT,
        price REAL,
        rating REAL,
        stock INTEGER,
        tags TEXT, 
        description TEXT,
        discount INTEGER,
        reviews INTEGER,
        shipping_time_days INTEGER
    )
    """)
    
    try:
        with open("products.json", "r") as f:
            data = json.load(f)
            
        count = 0
        for p in data:
            tags_str = ",".join(p.get("tags", []))
            # Default missing values to 0 to prevent errors
            discount = p.get("discount", 0)
            reviews = p.get("reviews", 0)
            shipping = p.get("shipping_time_days", 7)
            
            cursor.execute("""
            INSERT INTO products 
            (id, name, category, brand, price, rating, stock, tags, description, discount, reviews, shipping_time_days)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (p['id'], p['name'], p['category'], p['brand'], p['price'], p['rating'], p['stock'], tags_str, p['description'], discount, reviews, shipping))
            count += 1
            
        conn.commit()
        print(f"✅ Success! Database updated with {count} products and all columns.")
    except Exception as e:
        print(f"Error loading data: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()