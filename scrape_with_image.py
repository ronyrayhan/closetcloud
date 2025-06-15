import aiohttp
import asyncio
from bs4 import BeautifulSoup
import os
import re
import json
import datetime
import sqlite3
from urllib.parse import urljoin
import traceback

# Get the current date and time
scraped_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# File paths
urls_file = "url.txt"  # File containing URLs to scrape
db_file = "scraped_img_data.db"  # SQLite database file
images_folder = "product_images"  # Folder to store images

# Create image folder if not exists
os.makedirs(images_folder, exist_ok=True)

# User-Agent header to avoid getting blocked
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

# Set to keep track of already scraped URLs
scraped_urls = set()


# Initialize SQLite database
def initialize_db():
    conn = sqlite3.connect(db_file)
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


# Load already scraped URLs
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


# Insert product into database
def insert_product(product_data):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    categories_json = json.dumps(product_data["categories"])
    cursor.execute('''
        INSERT INTO products (title, sku, price, image_url, url, categories, scraped_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_data["title"],
        product_data["sku"],
        product_data["price"],
        product_data["image_url"],
        product_data["url"],
        categories_json,
        scraped_date
    ))
    conn.commit()
    conn.close()


# Download image and save locally
async def download_image(session, image_url, sku):
    try:
        if not image_url.startswith("http"):
            return None

        async with session.get(image_url, headers=headers, timeout=30) as response:
            if response.status == 200:
                ext = os.path.splitext(image_url)[-1].split("?")[0]
                if not ext or len(ext) > 5:
                    ext = ".jpg"
                file_name = f"{sku}{ext}"
                file_path = os.path.join(images_folder, file_name)

                with open(file_path, "wb") as f:
                    f.write(await response.read())

                return file_path
    except Exception as e:
        print(f"⚠️ Failed to download image {image_url}: {e}")
    return None


# Scrape a single product page
async def fetch_product(session, url):
    if url in scraped_urls:
        print(f"⏩ Skipping already scraped URL: {url}")
        return

    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "lxml")

                # Title
                title_tag = soup.find("h1", class_="product_title")
                title = title_tag.text.strip() if title_tag else "N/A"

                # SKU
                sku_tag = soup.find("span", class_="sku")
                sku = sku_tag.text.strip() if sku_tag else "N/A"

                # Out-of-stock check
                out_of_stock = soup.find(text="This product is currently out of stock and unavailable.")
                if out_of_stock:
                    price = "Out of Stock"
                else:
                    price_tag = soup.select_one(".price bdi")
                    price = price_tag.text.strip() if price_tag else "N/A"
                    price = re.sub(r'[^\d.]', '', price)

                # Image URL
                image_url = "N/A"
                img_tag = soup.find("img", class_="zoomImg")
                if img_tag and img_tag.get("src"):
                    image_url = img_tag["src"]
                else:
                    for img in soup.find_all("img"):
                        if "uploads" in img.get("src", "") and "logo" not in img.get("src", ""):
                            image_url = img["src"]
                            break

                # Ensure absolute image URL
                image_url = urljoin(url, image_url)

                # Download image
                local_image_path = await download_image(session, image_url, sku)

                # Categories
                categories = []
                cat_span = soup.find("span", class_="posted_in")
                if cat_span:
                    for a in cat_span.find_all("a", href=True):
                        categories.append({"name": a.text.strip(), "url": a["href"]})

                # Build product data
                product_data = {
                    "title": title,
                    "sku": sku,
                    "price": f"{price}TK",
                    "image_url": local_image_path if local_image_path else image_url,
                    "url": url,
                    "categories": categories,
                }

                # Insert and mark as scraped
                insert_product(product_data)
                scraped_urls.add(url)
                print(f"✅ Scraped: {title}")

            else:
                print(f"❌ Failed to fetch {url} (Status: {response.status})")

    except Exception as e:
        print(f"❌ Error fetching {url}:\n{traceback.format_exc()}")


# Main function
async def main():
    initialize_db()
    load_existing_urls()

    with open(urls_file, "r") as file:
        urls = [line.strip() for line in file.readlines()]

    async with aiohttp.ClientSession() as session:
        batch_size = 70
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            print(f"🔄 Processing batch {i // batch_size + 1} of {(len(urls) + batch_size - 1) // batch_size}")

            new_urls = [url for url in batch if url not in scraped_urls]
            tasks = [fetch_product(session, url) for url in new_urls]
            await asyncio.gather(*tasks)

            if new_urls and i + batch_size < len(urls):
                print("🕒 Waiting for 5 seconds before the next batch...")
                await asyncio.sleep(5)


# Run script
if __name__ == "__main__":
    asyncio.run(main())
    print("\n🎉 Scraping complete! Data saved to the database.")
