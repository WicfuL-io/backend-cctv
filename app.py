from flask import Flask, jsonify
import mysql.connector
import datetime
import subprocess
import platform
import requests
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)

# Simpan IP yang pernah error
error_logged_ips = set()

# Koneksi ke database
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="cctv_db"
    )

# Cek status CCTV
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

# Ambil suhu dari API CCTV dengan anti-spam logging
def get_temperature(ip):
    global error_logged_ips
    try:
        url = f"http://{ip}/api/temperature"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if ip in error_logged_ips:
                error_logged_ips.remove(ip)  # normal kembali → hapus dari daftar error
            return round(float(data.get("temperature", 0)), 2)
        else:
            if ip not in error_logged_ips:
                print(f"⚠️ API suhu error dari {ip}: Status {response.status_code}")
                error_logged_ips.add(ip)
        return 0
    except Exception as e:
        if ip not in error_logged_ips:
            print(f"⚠️ Tidak bisa ambil suhu dari {ip}: {e}")
            error_logged_ips.add(ip)
        return 0

# Update status dan suhu CCTV
def update_status():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM cctv")
    cctvs = cursor.fetchall()

    for cctv in cctvs:
        status = check_cctv_status(cctv["ip_address"])

        if status == "ONLINE":
            temperature = get_temperature(cctv["ip_address"])
        else:
            temperature = 0

        last_checked = datetime.datetime.now()

        # Cek apakah sudah ada status untuk CCTV ini
        cursor.execute("""
            SELECT id FROM cctv_status
            WHERE cctv_id = %s
            ORDER BY last_checked DESC
            LIMIT 1
        """, (cctv["id"],))
        result = cursor.fetchone()

        if result:
            cursor.execute("""
                UPDATE cctv_status
                SET status = %s, temperature = %s, last_checked = %s
                WHERE id = %s
            """, (status, temperature, last_checked, result['id']))
        else:
            cursor.execute("""
                INSERT INTO cctv_status (cctv_id, status, temperature, last_checked)
                VALUES (%s, %s, %s, %s)
            """, (cctv["id"], status, temperature, last_checked))

    conn.commit()
    cursor.close()
    conn.close()
    print(f"[{datetime.datetime.now()}] Status updated success.")

# Update berkala setiap 2 menit
def update_status_periodically():
    while True:
        try:
            update_status()
        except Exception as e:
            print(f"Error during update_status: {e}")
        time.sleep(120)  # delay 2 menit

# API route utama
@app.route("/")
def home():
    return jsonify({"message": "Welcome to CCTV API"})

# API untuk ambil data CCTV
@app.route("/cctv_data", methods=["GET"])
def get_cctv_data():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.id, c.title, c.category, s.status, 
               COALESCE(s.temperature, 0) AS temperature, s.last_checked
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
    # Jalankan update otomatis di background
    threading.Thread(target=update_status_periodically, daemon=True).start()

    # Jalankan Flask
    app.run(debug=True)
