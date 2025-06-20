from flask import Flask, render_template, request, jsonify, send_from_directory
import datetime

app = Flask(__name__)

DATABASE = 'scraped_data.db'
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}
import sqlite3
import json

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
            scraped_date TEXT NOT NULL
        )
    ''')
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

def add_product(product_data):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (title, sku, price, image_url, url, categories, scraped_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_data['title'],
        product_data['sku'],
        product_data['price'],
        product_data['image_url'],
        product_data['url'],
        json.dumps(product_data['categories']),
        product_data['scraped_date']
    ))
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id

def update_product(product_id, product_data):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE products 
        SET title = ?, sku = ?, price = ?, image_url = ?, url = ?, categories = ?, scraped_date = ?
        WHERE id = ?
    ''', (
        product_data['title'],
        product_data['sku'],
        product_data['price'],
        product_data['image_url'],
        product_data['url'],
        json.dumps(product_data['categories']),
        product_data['scraped_date'],
        product_id
    ))
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
    data['scraped_date'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    product_id = add_product(data)
    return jsonify({'id': product_id}), 201

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def api_update_product(product_id):
    data = request.get_json()
    data['scraped_date'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    affected_rows = update_product(product_id, data)
    if affected_rows:
        return jsonify({'success': True})
    return jsonify({'error': 'Product not found'}), 404

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def api_delete_product(product_id):
    affected_rows = delete_product(product_id)
    if affected_rows:
        return jsonify({'success': True})
    return jsonify({'error': 'Product not found'}), 404

if __name__ == '__main__':
    initialize_db()
    app.run(debug=True)