from flask import Flask, render_template, request, jsonify, send_from_directory
import datetime
import sqlite3
import json
import re
from bs4 import BeautifulSoup
import aiohttp
import asyncio

app = Flask(__name__)

DATABASE = 'scraped_data.db'
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

def initialize_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            sku TEXT NOT NULL,
            price TEXT NOT NULL,
            image_url TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            categories TEXT,
            scraped_date TEXT NOT NULL,
            is_out_of_stock INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_url ON products(url)')
    conn.commit()
    conn.close()

def get_all_products():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products ORDER BY id')
    products = cursor.fetchall()
    conn.close()
    return [dict(product) for product in products]

def get_product(product_id):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return dict(product) if product else None

def get_product_by_url(url):
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE url = ?', (url,))
    product = cursor.fetchone()
    conn.close()
    return dict(product) if product else None

def add_product(product_data):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (
            title, sku, price, image_url, url, categories, 
            scraped_date, is_out_of_stock
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_data['title'],
        product_data['sku'],
        product_data['price'],
        product_data['image_url'],
        product_data['url'],
        json.dumps(product_data['categories']),
        product_data.get('scraped_date', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        product_data.get('is_out_of_stock', 0)
    ))
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id

def update_product(product_id, product_data):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Build the update query dynamically
    update_fields = []
    update_values = []
    
    if 'title' in product_data:
        update_fields.append("title = ?")
        update_values.append(product_data['title'])
    
    if 'sku' in product_data:
        update_fields.append("sku = ?")
        update_values.append(product_data['sku'])
    
    if 'price' in product_data:
        update_fields.append("price = ?")
        update_values.append(product_data['price'])
    
    if 'image_url' in product_data:
        update_fields.append("image_url = ?")
        update_values.append(product_data['image_url'])
    
    if 'url' in product_data:
        update_fields.append("url = ?")
        update_values.append(product_data['url'])
    
    if 'categories' in product_data:
        update_fields.append("categories = ?")
        update_values.append(json.dumps(product_data['categories']))
    
    if 'is_out_of_stock' in product_data:
        update_fields.append("is_out_of_stock = ?")
        update_values.append(product_data['is_out_of_stock'])
    
    # Always update the scraped_date
    update_fields.append("scraped_date = ?")
    update_values.append(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    if not update_fields:
        conn.close()
        return 0
    
    update_values.append(product_id)
    
    query = f'''
        UPDATE products 
        SET {', '.join(update_fields)}
        WHERE id = ?
    '''
    
    cursor.execute(query, update_values)
    conn.commit()
    affected_rows = cursor.rowcount
    conn.close()
    return affected_rows

def delete_product(product_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    affected_rows = cursor.rowcount
    conn.close()
    return affected_rows

async def scrape_product(url):
    """Scrape individual product page with price handling logic"""
    try:
        existing_product = get_product_by_url(url)
        
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")

                    # Extract product data
                    title = soup.find("h1", class_="product_title").text.strip() if soup.find("h1", class_="product_title") else "N/A"
                    sku = soup.find("span", class_="sku").text.strip() if soup.find("span", class_="sku") else "N/A"
                    
                    # Determine stock status
                    out_of_stock = bool(soup.find(text="This product is currently out of stock and unavailable."))
                    
                    # Price handling logic
                    if out_of_stock:
                        if existing_product:
                            # Keep existing price for OOS products
                            price = existing_product['price']
                            title = f"{title} (Out of Stock)"
                        else:
                            price = "Out of Stock"
                    else:
                        # Get current price for in-stock items
                        price_element = soup.select_one(".price bdi")
                        price = re.sub(r'[^\d.]', '', price_element.text.strip()) if price_element else "N/A"
                        price = f"{price}TK"

                    # Image handling
                    img_tag = soup.find("img", class_="zoomImg")
                    image_url = img_tag["src"] if img_tag and "src" in img_tag.attrs else "N/A"
                    if image_url == "N/A":
                        for img in soup.find_all("img"):
                            if "uploads" in img.get("src", "") and "logo" not in img.get("src", ""):
                                image_url = img["src"]
                                break

                    # Categories
                    categories = []
                    categories_span = soup.find("span", class_="posted_in")
                    if categories_span:
                        categories = [{
                            "name": a.text.strip(),
                            "url": a["href"]
                        } for a in categories_span.find_all("a", href=True)]

                    # Prepare product data
                    product_data = {
                        "title": title,
                        "sku": sku,
                        "price": price,
                        "image_url": image_url,
                        "url": url,
                        "categories": categories,
                        "is_out_of_stock": 1 if out_of_stock else 0
                    }

                    if existing_product:
                        update_product(existing_product['id'], product_data)
                        return {"status": "updated", "product_id": existing_product['id']}
                    else:
                        product_id = add_product(product_data)
                        return {"status": "added", "product_id": product_id}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/products', methods=['GET'])
def api_get_products():
    products = get_all_products()
    return jsonify(products)

@app.route('/api/products/<int:product_id>', methods=['GET'])
def api_get_product(product_id):
    product = get_product(product_id)
    if product:
        return jsonify(product)
    return jsonify({'error': 'Product not found'}), 404

@app.route('/api/products', methods=['POST'])
def api_add_product():
    data = request.get_json()
    required_fields = ['title', 'sku', 'price', 'image_url', 'url', 'categories']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    data['scraped_date'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    product_id = add_product(data)
    return jsonify({'id': product_id}), 201

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def api_update_product(product_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    affected_rows = update_product(product_id, data)
    if affected_rows:
        return jsonify({'success': True})
    return jsonify({'error': 'Product not found or no changes made'}), 404

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def api_delete_product(product_id):
    affected_rows = delete_product(product_id)
    if affected_rows:
        return jsonify({'success': True})
    return jsonify({'error': 'Product not found'}), 404

@app.route('/api/scrape', methods=['POST'])
async def api_scrape_product():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
    
    result = await scrape_product(data['url'])
    if result['status'] == 'error':
        return jsonify({'error': result['message']}), 500
    
    return jsonify(result), 200 if result['status'] == 'updated' else 201

if __name__ == '__main__':
    initialize_db()
    app.run(debug=True, port=5001)