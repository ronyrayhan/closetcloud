import requests
import xml.etree.ElementTree as ET
import sqlite3

# List of sitemap URLs
urls = [
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-1.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-2.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-3.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-4.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-5.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-6.xml",
    "https://www.closetcloud.xyz/wp-sitemap-posts-product-7.xml"
]

# Namespace for WordPress sitemaps
ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

conn = ("sitemap_data.txt")

with open("url.txt", "w", encoding="utf-8") as txt_file:

# Process each sitemap and insert data
    for sitemap_url in urls:
        print(f"Fetching: {sitemap_url}")
        response = requests.get(sitemap_url)
        root = ET.fromstring(response.content)

        for url_tag in root.findall('ns:url', ns):
            loc = url_tag.find('ns:loc', ns).text
            lastmod = url_tag.find('ns:lastmod', ns).text if url_tag.find('ns:lastmod', ns) is not None else 'No date'
            
            # Insert into database
            txt_file.write(f"{loc}\n")
        print(f"Inserted  URLs from {sitemap_url}")



print("Data has been saved to sitemap_data.txt")
