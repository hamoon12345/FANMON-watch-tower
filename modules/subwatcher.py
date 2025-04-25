import os
import subprocess
import requests
import json
import time
import sys
import re
from mysql.connector import connect, Error
from discord_webhook import DiscordWebhook

# Configuration
CONFIG = {
    "scope_files": ["yourscope.txt"], 
    "subfinder_path": "subfinder",
    "assetfinder_path": "assetfinder",
    "sublist3r_path": "/root/Sublist3r/sublist3r.py",  
    "mysql_host": "localhost",
    "mysql_user": "root",
    "mysql_password": "yourpassword",
    "mysql_database": "subdomain_watch",
    "discord_webhook": "yourwebhook",
    "check_interval": 600  # 10 minutes in seconds
}

def load_domains_from_files(file_paths):
    """Load domains from scope files"""
    domains = set()
    
    for file_path in file_paths:
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    domain = line.strip()
                    if domain and not domain.startswith('#'):  
                        domains.add(domain)
        except FileNotFoundError:
            print(f"Scope file not found: {file_path}")
        except Exception as e:
            print(f"Error reading scope file {file_path}: {e}")
    
    return list(domains)

def setup_database():
    """Create database and table if they don't exist"""
    try:
        connection = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"]
        )
        cursor = connection.cursor()
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {CONFIG['mysql_database']}")
        cursor.execute(f"USE {CONFIG['mysql_database']}")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subdomains (
            id INT AUTO_INCREMENT PRIMARY KEY,
            domain VARCHAR(255) NOT NULL,
            subdomain VARCHAR(255) NOT NULL,
            discovery_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_subdomain (domain, subdomain)
        )
        """)
        
        connection.commit()
        cursor.close()
        connection.close()
        print("Database setup complete")
    except Error as e:
        print(f"Database setup error: {e}")

def run_subfinder(domain):
    """Run subfinder tool"""
    try:
        result = subprocess.run(
            [CONFIG["subfinder_path"], "-d", domain, "-silent"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"Subfinder error for {domain}: {e}")
        return []

def run_assetfinder(domain):
    """Run assetfinder tool"""
    try:
        result = subprocess.run(
            [CONFIG["assetfinder_path"], "--subs-only", domain],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"Assetfinder error for {domain}: {e}")
        return []

def run_sublist3r(domain):
    """Run Sublist3r tool with improved output handling"""
    try:
        # Run Sublist3r with Python and capture output
        result = subprocess.run(
            [sys.executable, CONFIG["sublist3r_path"], "-d", domain, "-n"],
            capture_output=True,
            text=True,
            check=True
        )
        

        clean_output = []
        for line in result.stdout.splitlines():

            if not re.search(r'[\\/_*#-]{3,}|\[\*\]|\[\-\]|\[\+\]|\[\!\]|\[\~\]', line):
                clean_line = line.strip()
                if clean_line and domain in clean_line:
                    clean_output.append(clean_line)
        
        return clean_output
    except subprocess.CalledProcessError as e:
        print(f"Sublist3r error for {domain}: {e}")
        return []

def query_crtsh(domain):
    """Query crt.sh for subdomains"""
    try:
        url = f"https://crt.sh/?q=%.{domain}&output=json"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            subdomains = set()
            for entry in data:
                name = entry["name_value"].lower()
                if name.startswith("*."):
                    name = name[2:]
                if domain in name:
                    subdomains.add(name)
            return list(subdomains)
        return []
    except Exception as e:
        print(f"crt.sh query error for {domain}: {e}")
        return []

def get_existing_subdomains(domain):
    """Get existing subdomains from database"""
    try:
        connection = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cursor = connection.cursor()
        cursor.execute("""
            SELECT subdomain FROM subdomains WHERE domain = %s
        """, (domain,))
        results = cursor.fetchall()
        return {result[0] for result in results}
    except Error as e:
        print(f"Database query error: {e}")
        return set()
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def save_new_subdomains(domain, subdomains):
    """Save new subdomains to database"""
    if not subdomains:
        return 0
    
    try:
        connection = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cursor = connection.cursor()
        
        new_count = 0
        for subdomain in subdomains:
            try:
                cursor.execute("""
                    INSERT INTO subdomains (domain, subdomain)
                    VALUES (%s, %s)
                """, (domain, subdomain))
                new_count += 1
            except Error as e:
                if "Duplicate entry" not in str(e):
                    print(f"Error saving subdomain {subdomain}: {e}")
        
        connection.commit()
        return new_count
    except Error as e:
        print(f"Database save error: {e}")
        return 0
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def send_discord_notification(domain, new_subdomains):
    """Send notification to Discord"""
    if not new_subdomains:
        return
    
    message = f"🚨 **New subdomains found for {domain}** 🚨\n\n"
    message += "\n".join(f"- `{sub}`" for sub in new_subdomains)
    
    try:
        webhook = DiscordWebhook(
            url=CONFIG["discord_webhook"],
            content=message,
            rate_limit_retry=True
        )
        response = webhook.execute()
        if response.status_code != 200:
            print(f"Discord notification failed: {response.status_code}")
    except Exception as e:
        print(f"Error sending Discord notification: {e}")

def monitor_domains():
    """Main monitoring function"""
    setup_database()
    
    while True:
        domains = load_domains_from_files(CONFIG["scope_files"])
        
        if not domains:
            print("No domains found in scope files. Waiting for next check...")
            time.sleep(CONFIG["check_interval"])
            continue
            
        for domain in domains:
            print(f"\nChecking subdomains for {domain}...")
            
            existing = get_existing_subdomains(domain)
            

            subfinder_results = run_subfinder(domain)
            assetfinder_results = run_assetfinder(domain)
            sublist3r_results = run_sublist3r(domain)
            crtsh_results = query_crtsh(domain)
            

            all_subdomains = set(subfinder_results + assetfinder_results + 
                               sublist3r_results + crtsh_results)
            new_subdomains = [sub for sub in all_subdomains if sub not in existing]
            
            if new_subdomains:
                print(f"Found {len(new_subdomains)} new subdomains for {domain}")
                saved_count = save_new_subdomains(domain, new_subdomains)
                print(f"Saved {saved_count} new subdomains to database")
                send_discord_notification(domain, new_subdomains)
            else:
                print(f"No new subdomains found for {domain}")
        
        print(f"\nWaiting {CONFIG['check_interval']} seconds for next check...")
        time.sleep(CONFIG["check_interval"])

if __name__ == "__main__":
    try:
        monitor_domains()
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)