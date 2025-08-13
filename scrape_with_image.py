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
from dateutil.parser import parse

# Configuration
CONFIG = {
    "SITEMAP_DB": "products.db",  # Database containing URLs with last_modified dates
    "SCRAPED_DB": "scraped_img_data.db",  # Database for storing scraped product data
    "IMAGES_FOLDER": "product_images",  # Folder to store downloaded images
    "BATCH_SIZE": 70,  # Number of concurrent requests
    "DELAY_BETWEEN_BATCHES": 5,  # Seconds to wait between batches
    "HEADERS": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }
}

# Create image folder if not exists
os.makedirs(CONFIG["IMAGES_FOLDER"], exist_ok=True)

def initialize_databases():
    """Initialize both databases with proper schema"""
    # Initialize sitemap database (products.db)
    with sqlite3.connect(CONFIG["SITEMAP_DB"]) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS products (
                url TEXT PRIMARY KEY,
                last_modified TEXT
            )
        ''')
    
    # Initialize scraped data database
    with sqlite3.connect(CONFIG["SCRAPED_DB"]) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS scraped_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                sku TEXT NOT NULL,
                price TEXT NOT NULL,
                image_url TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                categories TEXT,
                scraped_date TEXT NOT NULL,
                last_modified TEXT
            )
        ''')
        # Create index for faster lookups
        conn.execute('CREATE INDEX IF NOT EXISTS idx_url ON scraped_products(url)')

def normalize_datetime(dt_str):
    """Convert either ISO or SQL datetime string to a datetime object"""
    if not dt_str or dt_str == 'N/A':
        return None
    try:
        dt_str = dt_str.replace('T', ' ').split('+')[0].strip()
        return parse(dt_str)
    except (ValueError, TypeError):
        return None

def get_urls_to_scrape():
    """Get URLs that need to be scraped based on last_modified comparison"""
    urls_to_scrape = []
    
    with sqlite3.connect(CONFIG["SITEMAP_DB"]) as conn_sitemap, \
         sqlite3.connect(CONFIG["SCRAPED_DB"]) as conn_scraped:
        
        # Get all products from sitemap
        sitemap_products = conn_sitemap.execute(
            "SELECT url, last_modified FROM products"
        ).fetchall()
        
        for url, last_modified in sitemap_products:
            # Check if URL exists in scraped data
            scraped_data = conn_scraped.execute(
                "SELECT scraped_date, last_modified FROM scraped_products WHERE url = ?",
                (url,)
            ).fetchone()
            
            # Normalize datetimes
            sitemap_last_modified = normalize_datetime(last_modified)
            scraped_last_modified = normalize_datetime(scraped_data[1]) if scraped_data else None
            
            # Decision logic:
            # 1. If never scraped before
            # 2. Or if sitemap date is newer than scraped date
            # 3. Or if date comparison fails (safety check)
            if (not scraped_data or 
                (sitemap_last_modified and scraped_last_modified and 
                 sitemap_last_modified > scraped_last_modified) or
                (sitemap_last_modified and not scraped_last_modified)):
                urls_to_scrape.append((url, last_modified))
    
    print(f"Found {len(urls_to_scrape)} URLs needing update")
    return urls_to_scrape

async def download_image(session, image_url, sku):
    """Download product image and save locally"""
    try:
        if not image_url.startswith("http"):
            return None

        async with session.get(image_url, headers=CONFIG["HEADERS"], timeout=30) as response:
            if response.status == 200:
                ext = os.path.splitext(image_url)[-1].split("?")[0]
                if not ext or len(ext) > 5:
                    ext = ".jpg"
                file_name = f"{sku}{ext}"
                file_path = os.path.join(CONFIG["IMAGES_FOLDER"], file_name)

                with open(file_path, "wb") as f:
                    f.write(await response.read())

                return file_path
    except Exception as e:
        print(f"⚠️ Failed to download image {image_url}: {e}")
    return None

def insert_or_update_product(product_data, last_modified):
    """Insert new product or update existing one in the database"""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    categories_json = json.dumps(product_data["categories"])
    
    with sqlite3.connect(CONFIG["SCRAPED_DB"]) as conn:
        cursor = conn.cursor()
        
        # Try to update first
        cursor.execute('''
            UPDATE scraped_products SET
                title = ?,
                sku = ?,
                price = ?,
                image_url = ?,
                categories = ?,
                scraped_date = ?,
                last_modified = ?
            WHERE url = ?
        ''', (
            product_data["title"],
            product_data["sku"],
            product_data["price"],
            product_data["image_url"],
            categories_json,
            current_time,
            last_modified,
            product_data["url"]
        ))
        
        # If no rows were updated, insert new
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO scraped_products (
                    title, sku, price, image_url, url, 
                    categories, scraped_date, last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                product_data["title"],
                product_data["sku"],
                product_data["price"],
                product_data["image_url"],
                product_data["url"],
                categories_json,
                current_time,
                last_modified
            ))
        
        conn.commit()

async def fetch_product(session, url, last_modified):
    """Scrape individual product page"""
    try:
        async with session.get(url, headers=CONFIG["HEADERS"], timeout=30) as response:
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
                
                # Ensure absolute URL
                image_url = urljoin(url, image_url)
                
                # Download image
                local_image_path = await download_image(session, image_url, sku)

                # Categories
                categories = []
                categories_span = soup.find("span", class_="posted_in")
                if categories_span:
                    categories = [{
                        "name": a.text.strip(),
                        "url": a["href"]
                    } for a in categories_span.find_all("a", href=True)]

                # Package product data
                product_data = {
                    "title": title,
                    "sku": sku,
                    "price": price,
                    "image_url": local_image_path if local_image_path else image_url,
                    "url": url,
                    "categories": categories
                }
                
                insert_or_update_product(product_data, last_modified)
                print(f"✅ Updated: {title[:50]}...")

            else:
                print(f"❌ Failed to fetch {url} (Status: {response.status})")

    except Exception as e:
        print(f"❌ Error fetching {url}: {str(e)}")

async def scrape_products():
    """Main scraping workflow"""
    initialize_databases()
    urls_with_dates = get_urls_to_scrape()
    
    if not urls_with_dates:
        print("✅ All products are up-to-date!")
        return

    print(f"🚀 Starting to scrape {len(urls_with_dates)} products...")
    
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(urls_with_dates), CONFIG["BATCH_SIZE"]):
            batch = urls_with_dates[i:i + CONFIG["BATCH_SIZE"]]
            print(f"🔄 Processing batch {i//CONFIG["BATCH_SIZE"] + 1}/{(len(urls_with_dates)-1)//CONFIG["BATCH_SIZE"] + 1}")
            
            tasks = [fetch_product(session, url, last_modified) for url, last_modified in batch]
            await asyncio.gather(*tasks)
            
            if i + CONFIG["BATCH_SIZE"] < len(urls_with_dates):
                print(f"⏳ Waiting {CONFIG["DELAY_BETWEEN_BATCHES"]} seconds...")
                await asyncio.sleep(CONFIG["DELAY_BETWEEN_BATCHES"])
    
    print("🎉 Scraping completed successfully!")

if __name__ == "__main__":
    asyncio.run(scrape_products())