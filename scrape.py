import aiohttp
import asyncio
from bs4 import BeautifulSoup
import os
import re
import json
import datetime
import sqlite3
from dateutil.parser import parse

# Configuration
SITEMAP_DB = "closetcloud/products.db"  # Contains URLs with last_modified in ISO format
SCRAPED_DB = "closetcloud/scraped_data.db"  # Contains product data with SQL format datetimes
BATCH_SIZE = 70  # Number of concurrent requests
DELAY_BETWEEN_BATCHES = 5  # Seconds to wait between batches

# Headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

def initialize_databases():
    """Ensure both databases and tables exist with proper structure"""
    with sqlite3.connect(SCRAPED_DB) as conn:
        conn.execute('''
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

def normalize_datetime(dt_str):
    """Convert either ISO or SQL datetime string to a datetime object."""
    if not dt_str or dt_str == 'N/A':
        return None
    try:
        # Remove 'T' and timezone part if present
        dt_str = dt_str.replace('T', ' ').split('+')[0].strip()
        return parse(dt_str)
    except (ValueError, TypeError):
        return None

def get_urls_to_scrape():
    """Identify URLs that need to be scraped based on last_modified dates"""
    urls_to_scrape = []
    
    with sqlite3.connect(SITEMAP_DB) as conn_sitemap, \
         sqlite3.connect(SCRAPED_DB) as conn_scraped:
        
        # Get all products from sitemap
        sitemap_products = conn_sitemap.execute(
            "SELECT url, last_modified FROM products"
        ).fetchall()
        
        for url, last_modified in sitemap_products:
            # Get scraped date if exists
            scraped_date = conn_scraped.execute(
                "SELECT scraped_date FROM products WHERE url = ?", 
                (url,)
            ).fetchone()
            
            # Normalize both datetimes
            last_modified_norm = normalize_datetime(last_modified)
            scraped_date_norm = normalize_datetime(scraped_date[0]) if scraped_date else None
            
            # Decision logic:
            # 1. If never scraped before
            # 2. Or if sitemap date is newer than scraped date
            # 3. Or if date comparison fails (safety check)
            if (not scraped_date or 
                (last_modified_norm and scraped_date_norm and last_modified_norm > scraped_date_norm) or
                (last_modified_norm and not scraped_date_norm)):
                urls_to_scrape.append(url)
    
    print(f"Found {len(urls_to_scrape)} URLs needing update")
    return urls_to_scrape

def insert_or_update_product(product_data):
    """Insert new product or update existing one"""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    categories_json = json.dumps(product_data["categories"])
    
    with sqlite3.connect(SCRAPED_DB) as conn:
        cursor = conn.cursor()
        
        # Try to update first
        cursor.execute('''
            UPDATE products SET
                title = ?,
                sku = ?,
                price = ?,
                image_url = ?,
                categories = ?,
                scraped_date = ?
            WHERE url = ?
        ''', (
            product_data["title"],
            product_data["sku"],
            product_data["price"],
            product_data["image_url"],
            categories_json,
            current_time,
            product_data["url"]
        ))
        
        # If no rows were updated, insert new
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO products (
                    title, sku, price, image_url, url, categories, scraped_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                product_data["title"],
                product_data["sku"],
                product_data["price"],
                product_data["image_url"],
                product_data["url"],
                categories_json,
                current_time
            ))
        
        conn.commit()

async def fetch_product(session, url):
    """Scrape individual product page"""
    try:
        async with session.get(url, headers=HEADERS, timeout=30) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "lxml")

                # Extract product data
                title = soup.find("h1", class_="product_title").text.strip() if soup.find("h1", class_="product_title") else "N/A"
                sku = soup.find("span", class_="sku").text.strip() if soup.find("span", class_="sku") else "N/A"
                
                # Price handling
                if soup.find(text="This product is currently out of stock and unavailable."):
                    price = "Out of Stock"
                else:
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

                # Package and save data
                product_data = {
                    "title": title,
                    "sku": sku,
                    "price": price,
                    "image_url": image_url,
                    "url": url,
                    "categories": categories
                }
                
                insert_or_update_product(product_data)
                print(f"✅ Updated: {title[:50]}...")

            else:
                print(f"❌ Failed to fetch {url} (Status: {response.status})")

    except Exception as e:
        print(f"❌ Error fetching {url}: {str(e)}")

async def scrape_products():
    """Main scraping workflow"""
    initialize_databases()
    urls = get_urls_to_scrape()
    
    if not urls:
        print("✅ All products are up-to-date!")
        return

    print(f"🚀 Starting to scrape {len(urls)} products...")
    
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(urls), BATCH_SIZE):
            batch = urls[i:i + BATCH_SIZE]
            print(f"🔄 Processing batch {i//BATCH_SIZE + 1}/{(len(urls)-1)//BATCH_SIZE + 1}")
            
            await asyncio.gather(*[fetch_product(session, url) for url in batch])
            
            if i + BATCH_SIZE < len(urls):
                print(f"⏳ Waiting {DELAY_BETWEEN_BATCHES} seconds...")
                await asyncio.sleep(DELAY_BETWEEN_BATCHES)
    
    print("🎉 Scraping completed successfully!")

if __name__ == "__main__":
    asyncio.run(scrape_products())