from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import json
from flask_cors import CORS
import os
import time

app = Flask(__name__)
CORS(app)

# Database file path
DATABASE = "cat.db"

# Folder to store uploaded images
UPLOAD_FOLDER = "closetcloud/uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Function to get a database connection
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Create the catalogues table if it doesn't exist
def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS catalogues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                liveArtist TEXT NOT NULL,
                brandName TEXT NOT NULL,
                liveDate TEXT NOT NULL,
                primaryImages TEXT NOT NULL,  -- Store multiple primary images as JSON
                secondaryImages TEXT NOT NULL
            )
        ''')
        conn.commit()

# Route to serve the frontend (index.html)
@app.route("/")
def index():
    return send_from_directory(".", "admin.html")

# Route to serve uploaded images
@app.route("/closetcloud/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Route to handle image uploads
@app.route("/upload_image", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # Generate a unique filename
    timestamp = int(time.time())
    filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    # Return the file URL to the frontend
    file_url = f"/closetcloud/uploads/{filename}"
    return jsonify({"fileUrl": file_url})

# Route to delete an individual image
@app.route("/delete_image/<filename>", methods=["DELETE"])
def delete_image(filename):
    try:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({"message": "Image deleted successfully"}), 200
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to add a new catalogue
@app.route("/add_catalogue", methods=["POST"])
def add_catalogue():
    data = request.json
    name = data.get("name")
    live_artist = data.get("liveArtist")
    brand_name = data.get("brandName")
    live_date = data.get("liveDate")
    primary_images = json.dumps(data.get("primaryImages"))  # Store multiple primary images as JSON
    secondary_images = json.dumps(data.get("secondaryImages"))

    if not all([name, live_artist, brand_name, live_date, primary_images, secondary_images]):
        return jsonify({"error": "All fields are required"}), 400

    with get_db() as conn:
        conn.execute('''
            INSERT INTO catalogues (name, liveArtist, brandName, liveDate, primaryImages, secondaryImages)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, live_artist, brand_name, live_date, primary_images, secondary_images))
        conn.commit()

    return jsonify({"message": "Catalogue added successfully"}), 201

# Route to edit a catalogue
@app.route("/edit_catalogue/<int:id>", methods=["PUT"])
def edit_catalogue(id):
    data = request.json
    name = data.get("name")
    live_artist = data.get("liveArtist")
    brand_name = data.get("brandName")
    live_date = data.get("liveDate")
    primary_images = json.dumps(data.get("primaryImages"))  # Store multiple primary images as JSON
    secondary_images = json.dumps(data.get("secondaryImages"))

    if not all([name, live_artist, brand_name, live_date, primary_images, secondary_images]):
        return jsonify({"error": "All fields are required"}), 400

    with get_db() as conn:
        conn.execute('''
            UPDATE catalogues
            SET name = ?, liveArtist = ?, brandName = ?, liveDate = ?, primaryImages = ?, secondaryImages = ?
            WHERE id = ?
        ''', (name, live_artist, brand_name, live_date, primary_images, secondary_images, id))
        conn.commit()

    return jsonify({"message": "Catalogue updated successfully"}), 200

# Route to delete a catalogue
@app.route("/delete_catalogue/<int:id>", methods=["DELETE"])
def delete_catalogue(id):
    with get_db() as conn:
        # Fetch the catalogue to delete its images
        cursor = conn.cursor()
        cursor.execute("SELECT primaryImages, secondaryImages FROM catalogues WHERE id = ?", (id,))
        catalogue = cursor.fetchone()

        if catalogue:
            # Delete primary images
            primary_images = json.loads(catalogue["primaryImages"])
            for image_url in primary_images:
                filename = image_url.split("/")[-1]
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)

            # Delete secondary images
            secondary_images = json.loads(catalogue["secondaryImages"])
            for image_url in secondary_images:
                filename = image_url.split("/")[-1]
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)

        # Delete the catalogue from the database
        conn.execute("DELETE FROM catalogues WHERE id = ?", (id,))
        conn.commit()

    return jsonify({"message": "Catalogue deleted successfully"}), 200

# Route to fetch all catalogues
@app.route("/get_catalogues", methods=["GET"])
def get_catalogues():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM catalogues")
        catalogues = cursor.fetchall()

    # Convert rows to a list of dictionaries
    catalogues_list = []
    for row in catalogues:
        catalogues_list.append({
            "id": row["id"],
            "name": row["name"],
            "liveArtist": row["liveArtist"],
            "brandName": row["brandName"],
            "liveDate": row["liveDate"],
            "primaryImages": json.loads(row["primaryImages"]),  # Parse JSON for primary images
            "secondaryImages": json.loads(row["secondaryImages"])  # Parse JSON for secondary images
        })

    return jsonify(catalogues_list)

# Run the Flask app
if __name__ == "__main__":
    init_db()
    app.run(host='0.0.0.0', port=80)