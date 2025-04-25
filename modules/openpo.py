import os
import subprocess
import re
import time
from mysql.connector import connect, Error
from discord_webhook import DiscordWebhook

# Config
CONFIG = {
    "scope_files": ["yourscope.txt"],
    "mysql_host": "localhost",
    "mysql_user": "root",
    "mysql_password": "yourpassword",
    "mysql_database": "port_monitor_db",
    "discord_webhook": "yourwebhook",
    "check_interval": 600,
    "scan_ports": "1-65535",  # Customize if needed
    "verbose": True
}

def print_verbose(msg):
    if CONFIG["verbose"]:
        print(msg)

def load_domains_from_files(file_paths):
    domains = set()
    for file in file_paths:
        try:
            with open(file, 'r') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):
                        domain = re.sub(r'^https?://(www\.)?', '', url).split('/')[0]
                        domains.add(domain)
        except Exception as e:
            print(f"Error loading from {file}: {e}")
    return list(domains)

def setup_database():
    try:
        conn = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"]
        )
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {CONFIG['mysql_database']}")
        cur.execute(f"USE {CONFIG['mysql_database']}")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS open_ports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            domain VARCHAR(255),
            port INT,
            protocol VARCHAR(10) DEFAULT 'tcp',
            scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_entry (domain, port)
        )
        """)
        conn.commit()
        print_verbose("Database setup complete")
        return True
    except Error as e:
        print(f"Database setup error: {e}")
        return False
    finally:
        if 'conn' in locals() and conn.is_connected():
            cur.close()
            conn.close()

def scan_with_nmap(domain):
    try:
        cmd = ["nmap", "-p", CONFIG["scan_ports"], "-sV", domain]
        result = subprocess.run(cmd, capture_output=True, text=True)
        ports = []

        for line in result.stdout.splitlines():
            match = re.match(r'^(\d+)/tcp\s+open\s+([^\s]+)\s*(.*)', line)
            if match:
                port = int(match.group(1))
                service = match.group(2)
                version = match.group(3).strip()
                ports.append((port, service, version))  # Store as tuple

        return ports
    except Exception as e:
        print(f"Scan error for {domain}: {e}")
        return []

def get_existing_ports(domain):
    try:
        conn = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cur = conn.cursor()
        cur.execute("SELECT port FROM open_ports WHERE domain = %s", (domain,))
        return {row[0] for row in cur.fetchall()}
    finally:
        if 'conn' in locals() and conn.is_connected():
            cur.close()
            conn.close()

def save_new_ports(domain, ports):
    try:
        conn = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cur = conn.cursor()
        data = [(domain, port) for port in ports]
        cur.executemany("""
            INSERT IGNORE INTO open_ports (domain, port)
            VALUES (%s, %s)
        """, data)
        conn.commit()
        return cur.rowcount
    finally:
        if 'conn' in locals() and conn.is_connected():
            cur.close()
            conn.close()

def send_discord_notification(domain, ports):
    if not ports:
        return

    message = f"🚨 **New open ports on {domain}** 🚨\n```\n"
    for port, service, version in ports:
        version_info = f" - {version}" if version else ""
        message += f"{port}/tcp OPEN - {service}{version_info}\n"
    message += "```"

    try:
        webhook = DiscordWebhook(
            url=CONFIG["discord_webhook"],
            content=message,
            rate_limit_retry=True
        )
        response = webhook.execute()
        if response.status_code != 200:
            print(f"Discord error: {response.status_code}")
    except Exception as e:
        print(f"Discord send error: {e}")

def monitor():
    if not setup_database():
        print("Database setup failed. Exiting.")
        return

    while True:
        try:
            domains = load_domains_from_files(CONFIG["scope_files"])
            total_new = 0

            for domain in domains:
                print_verbose(f"Scanning {domain}...")
                current_ports = scan_with_nmap(domain)
                existing_ports = get_existing_ports(domain)
                new_ports = [p for p in current_ports if p not in existing_ports]

                if new_ports:
                    print(f"New ports on {domain}: {new_ports}")
                    saved = save_new_ports(domain, new_ports)
                    send_discord_notification(domain, new_ports)
                    total_new += saved

            print_verbose(f"\nScan complete. {total_new} new ports saved.")
            time.sleep(CONFIG["check_interval"])
        except KeyboardInterrupt:
            print("Stopped by user.")
            break
        except Exception as e:
            print(f"Monitor error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    monitor()
