import requests
import xml.etree.ElementTree as ET
import sqlite3

# List of sitemap URLs (unchanged)
urls = [
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-1.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-2.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-3.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-4.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-5.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-6.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-7.xml"
]

# Namespace for WordPress sitemaps (unchanged)
ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

# Create/connect to SQLite database
conn = sqlite3.connect('closetcloud/products.db')
cursor = conn.cursor()

# Create table (only if it doesn't exist)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        url TEXT PRIMARY KEY,
        last_modified TEXT
    )
''')

# Process each sitemap (unchanged scraping logic)
for sitemap_url in urls:
    print(f"Fetching: {sitemap_url}")
    try:
        response = requests.get(sitemap_url)
        root = ET.fromstring(response.content)

        for url_tag in root.findall('ns:url', ns):
            loc = url_tag.find('ns:loc', ns).text
            lastmod = url_tag.find('ns:lastmod', ns).text if url_tag.find('ns:lastmod', ns) is not None else 'N/A'
            
            # Insert into SQLite DB (instead of writing to a text file)
            cursor.execute('''
                INSERT OR REPLACE INTO products (url, last_modified)
                VALUES (?, ?)
            ''', (loc, lastmod))
        
        conn.commit()  # Save changes to DB
        print(f"Inserted URLs from {sitemap_url} into database")
    
    except Exception as e:
        print(f"Error processing {sitemap_url}: {e}")

# Close the database connection
conn.close()
print("Data has been saved to products.db")