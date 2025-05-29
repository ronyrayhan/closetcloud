import aiohttp
import asyncio
from bs4 import BeautifulSoup
import sqlite3
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('image_rescraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database configuration
DB_FILE = "scraped_data.db"
PLACEHOLDER_STRING = "woocommerce-placeholder"

# User-Agent header
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

def get_products_with_placeholder():
    """Retrieve products with placeholder images from the database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    query = """
    SELECT id, url, image_url, title 
    FROM products 
    WHERE image_url LIKE ? OR image_url = 'N/A'
    """
    cursor.execute(query, (f"%{PLACEHOLDER_STRING}%",))
    
    products = []
    for row in cursor.fetchall():
        products.append({
            "id": row[0],
            "url": row[1],
            "old_image_url": row[2],
            "title": row[3]
        })
    
    conn.close()
    return products

async def fetch_new_image_url(session, product_url):
    """Fetch new image URL from product page"""
    try:
        async with session.get(product_url, headers=HEADERS, timeout=30) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "lxml")

                # First try to find the zoom image
                img_tag = soup.find("img", class_="zoomImg")
                if img_tag and "src" in img_tag.attrs:
                    return img_tag["src"]

                # If not found, search through all images for a product image
                all_images = soup.find_all("img")
                for img in all_images:
                    src = img.get("src", "")
                    if src and "uploads" in src and "logo" not in src:
                        return src

                logger.warning(f"No suitable image found for {product_url}")
                return None

            logger.error(f"Failed to fetch {product_url} (Status: {response.status})")
            return None

    except Exception as e:
        logger.error(f"Error fetching {product_url}: {str(e)}")
        return None

def update_product_image(product_id, new_image_url):
    """Update product image URL in the database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE products 
        SET image_url = ? 
        WHERE id = ?
    """, (new_image_url, product_id))
    
    conn.commit()
    conn.close()

async def process_product(session, product):
    """Process a single product to update its image"""
    logger.info(f"Processing product: {product['title']}")
    logger.info(f"Old image URL: {product['old_image_url']}")
    
    new_image_url = await fetch_new_image_url(session, product["url"])
    
    if new_image_url and new_image_url != product["old_image_url"]:
        update_product_image(product["id"], new_image_url)
        logger.info(f"Updated image URL: {new_image_url}")
        return True
    else:
        logger.warning("No new image URL found or image URL unchanged")
        return False

async def main():
    """Main function to rescrape images"""
    logger.info("Starting image rescraping process")
    
    # Get products with placeholder images
    products = get_products_with_placeholder()
    
    if not products:
        logger.info("No products with placeholder images found")
        return
    
    logger.info(f"Found {len(products)} products with placeholder images")
    
    # Process products in batches
    async with aiohttp.ClientSession() as session:
        batch_size = 20
        updated_count = 0
        
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(products)-1)//batch_size + 1}")
            
            tasks = [process_product(session, product) for product in batch]
            results = await asyncio.gather(*tasks)
            updated_count += sum(results)
            
            # Add delay between batches to be polite
            if i + batch_size < len(products):
                await asyncio.sleep(5)
    
    logger.info(f"Process completed. Updated {updated_count} out of {len(products)} products")

if __name__ == "__main__":
    start_time = datetime.now()
    logger.info(f"Script started at {start_time}")
    
    asyncio.run(main())
    
    end_time = datetime.now()
    duration = end_time - start_time
    logger.info(f"Script completed at {end_time}")
    logger.info(f"Total execution time: {duration}")