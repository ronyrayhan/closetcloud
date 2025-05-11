import sqlite3

# Path to the SQLite database
db_file = "scraped_data.db"
# Path to the log file where deleted URLs will be saved
log_file = "log.txt"

def remove_out_of_stock_products():
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Select all "Out of Stock" product URLs
    cursor.execute("SELECT url FROM products WHERE price LIKE 'Out of Stock%'")
    out_of_stock_urls = [row[0] for row in cursor.fetchall()]

    # Save the URLs to a log file
    if out_of_stock_urls:
        with open(log_file, "w") as f:
            for url in out_of_stock_urls:
                f.write(url + "\n")
        print(f"📝 Saved {len(out_of_stock_urls)} 'Out of Stock' URLs to '{log_file}'.")

    # Delete the "Out of Stock" products from the database
    cursor.execute("DELETE FROM products WHERE price LIKE 'Out of Stock%'")
    conn.commit()
    print(f"🗑️ Removed {cursor.rowcount} 'Out of Stock' products from the database.")

    conn.close()

if __name__ == "__main__":
    remove_out_of_stock_products()
