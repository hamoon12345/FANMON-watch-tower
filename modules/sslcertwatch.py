import requests
import mysql.connector
from mysql.connector import Error
import time

# Discord Webhook
DISCORD_WEBHOOK_URL = 'your web hook'

# MySQL config
DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = 'your password'
DB_DATABASE = 'ssl_certificates'

def get_cert_common_names(domain):
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) YourApp/1.0',
        'Accept': 'application/json'
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200:
            data = response.json()
            common_names = set()
            for cert in data:
                name = cert.get("common_name") or cert.get("name_value")
                if name:

                    for cn in name.split('\n'):
                        if cn.endswith(domain):
                            common_names.add(cn.strip())
            return list(common_names)
        else:
            print(f"Failed to fetch from crt.sh for {domain}: {response.status_code}")
    except Exception as e:
        print(f"Error requesting crt.sh for {domain}: {e}")
    return []

def send_to_discord(domain, cn):
    payload = {
        "content": f"🔐 **New SSL Certificate Detected**\nDomain: `{domain}`\nCN: `{cn}`"
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code == 204:
            print("✅ Notification sent to Discord.")
        else:
            print(f"❌ Failed to send to Discord. Status: {response.status_code}")
    except Exception as e:
        print(f"Discord error: {e}")

def is_new_cn(cn, domain):
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE
        )
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ssl_certificates WHERE domain = %s AND cn = %s", (domain, cn))
        result = cursor.fetchone()
        conn.close()
        return result is None
    except Error as e:
        print(f"MySQL error: {e}")
        return False

def log_to_mysql(domain, cn):
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE
        )
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ssl_certificates (domain, cn) VALUES (%s, %s)", (domain, cn))
        conn.commit()
        conn.close()
        print(f"✅ Logged to MySQL: {domain} - {cn}")
    except Error as e:
        print(f"MySQL error: {e}")

def monitor_domains(domain_list):
    while True:
        for domain in domain_list:
            print(f"🔍 Checking {domain}")
            cns = get_cert_common_names(domain)
            for cn in cns:
                if is_new_cn(cn, domain):
                    send_to_discord(domain, cn)
                    log_to_mysql(domain, cn)
                else:
                    print(f"🟡 Already logged: {cn}")
            time.sleep(10)
        time.sleep(14400)

def read_domains_from_file(filename):
    try:
        with open(filename, 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        print(f"❌ File {filename} not found.")
        return []

# MAIN
domains = read_domains_from_file("your scope.txt")
monitor_domains(domains)