import subprocess
import re
import time
from mysql.connector import connect, Error
from discord_webhook import DiscordWebhook

CONFIG = {
    "nmap_path": "nmap",
    "mysql_host": "localhost",
    "mysql_user": "root",
    "mysql_password": "your password",
    "mysql_database": "subdomain_watch",
    "discord_webhook": "your web hook",
    "check_interval": 600,
    "top_ports": 100,  # Scan top 100 ports
    "verbose": True
}

def print_verbose(msg):
    if CONFIG["verbose"]:
        print(msg)

def get_ips_from_database():
    """Fetch valid IPs from database"""
    try:
        conn = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ip, domain
            FROM ips
            WHERE
                domain NOT LIKE '%*%' AND
                ip REGEXP '^[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}$'
        """)
        return cur.fetchall()
    except Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        if 'conn' in locals() and conn.is_connected():
            cur.close()
            conn.close()

def setup_database():
    """Create port tracking table"""
    try:
        conn = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS open_ports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ip VARCHAR(15) NOT NULL,
            domain VARCHAR(255) NOT NULL,
            port INT NOT NULL,
            service VARCHAR(50),
            version VARCHAR(100),
            protocol VARCHAR(3) DEFAULT 'tcp',
            scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_port (ip, port, service)
        )
        """)
        conn.commit()
        print_verbose("Database setup complete")
        return True
    except Error as e:
        print(f"Database error: {e}")
        return False

def scan_with_nmap(ip):
    """Nmap top ports scanning with service detection"""
    try:
        cmd = [
            CONFIG["nmap_path"],
            "-n",
            "--top-ports", str(CONFIG["top_ports"]),
            "-sV",
            "--open",
            "-oN", "-",  # Output to stdout
            ip
        ]
        result = subprocess.run(cmd,
                              capture_output=True,
                              text=True,
                              timeout=600)

        ports = []
        for line in result.stdout.splitlines():
            match = re.match(r'^(\d+)/tcp\s+open\s+([^\s]+)\s*(.*)', line)
            if match:
                port = int(match.group(1))
                service = match.group(2)
                version = match.group(3).strip()
                ports.append((port, service, version))

        return ports
    except subprocess.TimeoutExpired:
        print(f"Timeout scanning {ip}")
        return []
    except Exception as e:
        print(f"Scan error: {e}")
        return []

def get_existing_ports(ip):
    """Get known ports for IP"""
    try:
        conn = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT port, service
            FROM open_ports
            WHERE ip = %s
        """, (ip,))
        return {(row[0], row[1]) for row in cur.fetchall()}
    except Error as e:
        print(f"Database error: {e}")
        return set()

def save_new_ports(ip, domain, ports):
    """Store new ports with service info"""
    try:
        conn = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cur = conn.cursor()
        data = [(ip, domain, p[0], p[1], p[2]) for p in ports]

        cur.executemany("""
            INSERT IGNORE INTO open_ports
                (ip, domain, port, service, version)
            VALUES (%s, %s, %s, %s, %s)
        """, data)

        conn.commit()
        return cur.rowcount
    except Error as e:
        print(f"Database error: {e}")
        return 0

def send_discord_alert(ip, domain, ports):
    """Detailed port alerts with service info"""
    message = f"🚨 **New ports on {domain} ({ip})** 🚨\n```\n"
    for port, service, version in ports:
        message += f"• {port}/tcp - {service}"
        if version:
            message += f" ({version})"
        message += "\n"
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
        print(f"Notification error: {e}")

def monitor():
    if not setup_database():
        return

    while True:
        try:
            targets = get_ips_from_database()
            total_new = 0

            for ip, domain in targets:
                print_verbose(f"Scanning {domain} ({ip})...")
                found_ports = scan_with_nmap(ip)
                known_ports = get_existing_ports(ip)
                new_ports = [p for p in found_ports
                            if (p[0], p[1]) not in known_ports]

                if new_ports:
                    print(f"New ports on {ip}: {new_ports}")
                    saved = save_new_ports(ip, domain, new_ports)
                    send_discord_alert(ip, domain, new_ports)
                    total_new += saved

            print_verbose(f"Scan complete. New ports: {total_new}")
            time.sleep(CONFIG["check_interval"])

        except KeyboardInterrupt:
            print("Stopped by user")
            break
        except Exception as e:
            print(f"Monitor error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    monitor()