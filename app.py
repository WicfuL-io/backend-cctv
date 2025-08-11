from flask import Flask, jsonify
import mysql.connector
import datetime
import random
import subprocess
import platform
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="cctv_db"
    )

def check_cctv_status(ip):
    try:
        param = "-n" if platform.system().lower() == "windows" else "-c"
        result = subprocess.run(
            ["ping", param, "1", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return "ONLINE" if result.returncode == 0 else "OFFLINE"
    except:
        return "OFFLINE"

@app.route("/")
def home():
    return jsonify({"message": "Welcome to CCTV API"})

@app.route("/update_status", methods=["GET"])
def update_status():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM cctv")
    cctvs = cursor.fetchall()

    for cctv in cctvs:
        status = check_cctv_status(cctv["ip_address"])
        temperature = round(random.uniform(20, 90), 2)
        last_checked = datetime.datetime.now()

        cursor.execute("""
            INSERT INTO cctv_status (cctv_id, status, temperature, last_checked)
            VALUES (%s, %s, %s, %s)
        """, (cctv["id"], status, temperature, last_checked))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Status updated successfully"})

@app.route("/cctv_data", methods=["GET"])
def get_cctv_data():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.id, c.title, c.category, s.status, s.temperature, s.last_checked
        FROM cctv c
        LEFT JOIN (
            SELECT cctv_id, status, temperature, last_checked
            FROM cctv_status
            WHERE (cctv_id, last_checked) IN (
                SELECT cctv_id, MAX(last_checked)
                FROM cctv_status
                GROUP BY cctv_id
            )
        ) s ON c.id = s.cctv_id
    """)
    data = cursor.fetchall()

    cursor.close()
    conn.close()
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)
