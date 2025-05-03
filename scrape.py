import aiohttp
import asyncio
from bs4 import BeautifulSoup
import os
import re
import json
import datetime
import sqlite3
from urllib.parse import urlparse

# Get the current date and time
scraped_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# File paths
urls_file = "url.txt"  # File containing URLs to scrape
db_file = "scraped_data.db"  # SQLite database file
images_dir = "product_images"  # Directory to store downloaded images

# Create images directory if it doesn't exist
os.makedirs(images_dir, exist_ok=True)

# User-Agent header to avoid getting blocked
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

# Set to keep track of already scraped URLs
scraped_urls = set()

# Function to initialize the SQLite database
def initialize_db():
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # Create a table to store product data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            sku TEXT NOT NULL,
            price TEXT NOT NULL,
            image_url TEXT NOT NULL,
            local_image_path TEXT,
            url TEXT NOT NULL UNIQUE,
            categories TEXT,
            scraped_date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Function to load existing scraped URLs from the database
def load_existing_urls():
    if os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM products")
        rows = cursor.fetchall()
        for row in rows:
            scraped_urls.add(row[0])
        conn.close()
    print(f"Loaded {len(scraped_urls)} existing URLs from the database")

# Function to download and save an image
async def download_image(session, image_url, sku):
    if not image_url or image_url == "N/A":
        return None
        
    try:
        # Clean the SKU to create a valid filename
        clean_sku = re.sub(r'[^\w\-_]', '_', sku)
        
        # Get the file extension from the URL
        parsed_url = urlparse(image_url)
        path = parsed_url.path
        ext = os.path.splitext(path)[1]
        
        # If no extension or query parameters, try to get content type
        if not ext or '?' in ext:
            ext = '.jpg'  # default to jpg if we can't determine
        
        filename = f"{clean_sku}{ext}"
        filepath = os.path.join(images_dir, filename)
        
        # Skip if file already exists
        if os.path.exists(filepath):
            return filepath
            
        async with session.get(image_url, headers=headers) as response:
            if response.status == 200:
                with open(filepath, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)
                return filepath
    except Exception as e:
        print(f"❌ Error downloading image {image_url}: {e}")
        return None

# Function to insert new product data into the database
def insert_product(product_data):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # Convert categories list to a JSON string
    categories_json = json.dumps(product_data["categories"])
    # Insert the product data into the database
    cursor.execute('''
        INSERT INTO products (title, sku, price, image_url, local_image_path, url, categories, scraped_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_data["title"],
        product_data["sku"],
        product_data["price"],
        product_data["image_url"],
        product_data["local_image_path"],
        product_data["url"],
        categories_json,
        scraped_date
    ))
    conn.commit()
    conn.close()

# Function to scrape a single product page
async def fetch_product(session, url):
    if url in scraped_urls:
        print(f"⏩ Skipping already scraped URL: {url}")
        return

    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "lxml")  # Use lxml for faster parsing

                # Extract Product Title
                title = soup.find("h1", class_="product_title")
                title = title.text.strip() if title else "N/A"

                # Extract SKU
                sku = soup.find("span", class_="sku")
                sku = sku.text.strip() if sku else "N/A"

                # Check if the product is out of stock
                out_of_stock_message = soup.find(text="This product is currently out of stock and unavailable.")
                if out_of_stock_message:
                    price = "Out of Stock"
                else:
                    # Extract Price if the product is in stock
                    price = soup.select_one(".price bdi")
                    price = price.text.strip() if price else "N/A"
                    price = re.sub(r'[^\d.]', '', price)  # Clean price (remove currency symbols)

                # Extract Product Image URL
                image_url = "N/A"
                img_tag = soup.find("img", class_="zoomImg")
                if img_tag and "src" in img_tag.attrs:
                    image_url = img_tag["src"]

                if image_url == "N/A":
                    all_images = soup.find_all("img")
                    for img in all_images:
                        if "uploads" in img.get("src", "") and "logo" not in img.get("src", ""):
                            image_url = img["src"]
                            break

                # Download the image
                local_image_path = await download_image(session, image_url, sku) if image_url != "N/A" else None

                # Extract Categories
                categories = []
                categories_span = soup.find("span", class_="posted_in")
                if categories_span:
                    for a_tag in categories_span.find_all("a", href=True):
                        categories.append({
                            "name": a_tag.text.strip(),
                            "url": a_tag["href"]
                        })

                # Generate product data
                product_data = {
                    "title": title,
                    "sku": sku,
                    "price": f"{price}TK",
                    "image_url": image_url,
                    "local_image_path": local_image_path,
                    "url": url,
                    "categories": categories,  # Always include categories, even if empty
                }

                # Insert the product data into the database
                insert_product(product_data)

                # Add the URL to the scraped set
                scraped_urls.add(url)
                print(f"✅ Scraped: {title}")

            else:
                print(f"❌ Failed to fetch {url} (Status: {response.status})")

    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")

# Main function to scrape all URLs
async def main():
    # Initialize the database
    initialize_db()

    # Load existing URLs from the database
    load_existing_urls()

    # Load URLs from the input file
    with open(urls_file, "r") as file:
        urls = [line.strip() for line in file.readlines()]

    # Scrape URLs in batches of 20
    async with aiohttp.ClientSession() as session:
        batch_size = 70
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            print(f"🔄 Processing batch {i // batch_size + 1} of {len(urls) // batch_size + 1}")

            # Filter out already scraped URLs from the batch
            new_urls = [url for url in batch if url not in scraped_urls]

            # Scrape all new URLs in the current batch concurrently
            tasks = [fetch_product(session, url) for url in new_urls]
            await asyncio.gather(*tasks)

            # Wait for 3 seconds only if there were new URLs in the batch
            if new_urls and i + batch_size < len(urls):
                print("🕒 Waiting for 3 seconds before the next batch...")
                await asyncio.sleep(5)

# Run the script
if __name__ == "__main__":
    asyncio.run(main())
    print("\n🎉 Scraping complete! Data saved to the database.")