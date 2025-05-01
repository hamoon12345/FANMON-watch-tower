import requests
from bs4 import BeautifulSoup
import logging
import time
from mysql.connector import connect, Error

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your password",
    "database": "writeup_watcher",
    "table": "bug_bounty_writeups"
}

logging.basicConfig(level=logging.INFO)

def setup_database():
    """Initialize database and table if they don't exist"""
    try:
        connection = connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"]
        )
        cursor = connection.cursor()

        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")

        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG['table']} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            url VARCHAR(512) NOT NULL UNIQUE,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        connection.commit()
        logging.info("Database setup complete")
        return True
    except Error as e:
        logging.error(f"Database setup error: {e}")
        return False
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def get_existing_writeups():
    """Retrieve all stored writeup URLs from database"""
    try:
        connection = connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"]
        )
        cursor = connection.cursor()
        cursor.execute(f"SELECT url FROM {DB_CONFIG['table']}")
        return {row[0] for row in cursor.fetchall()}
    except Error as e:
        logging.error(f"Database query error: {e}")
        return set()
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def save_new_writeups(writeups):
    """Save new writeups to database"""
    if not writeups:
        return 0

    try:
        connection = connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"]
        )
        cursor = connection.cursor()

        new_count = 0
        for title, url in writeups:
            try:
                cursor.execute(f"""
                    INSERT IGNORE INTO {DB_CONFIG['table']} (title, url)
                    VALUES (%s, %s)
                """, (title, url))
                new_count += cursor.rowcount
            except Error as e:
                logging.error(f"Error saving writeup {url}: {e}")

        connection.commit()
        return new_count
    except Error as e:
        logging.error(f"Database save error: {e}")
        return 0
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def get_bug_bounty_writeups(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        writeups = []
        articles = soup.find_all('article')

        for article in articles:
            title_tag = article.find('h2')
            link_tag = article.find('a', href=True)

            if title_tag and link_tag:
                title = title_tag.get_text().strip()
                url = link_tag['href']
                if not url.startswith('http'):
                    url = f"https://medium.com{url}"
                writeups.append((title, url))

        logging.info(f"Found {len(writeups)} write-ups.")
        return writeups
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data: {e}")
        return []

def send_discord_notification(webhook_url, message):
    try:
        payload = {"content": message}
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        logging.info(f"Notification sent: {message[:50]}...")
    except requests.exceptions.RequestException as e:
        logging.error(f"Discord notification failed: {e}")

def monitor_bug_bounty_writeups(webhook_url, url_to_scrape):
    # Get existing writeups from database
    existing_urls = get_existing_writeups()

    # Fetch current writeups
    current_writeups = get_bug_bounty_writeups(url_to_scrape)

    # Filter new writeups
    new_writeups = [w for w in current_writeups if w[1] not in existing_urls]

    if new_writeups:
        logging.info(f"Found {len(new_writeups)} new write-ups")
        saved = save_new_writeups(new_writeups)
        logging.info(f"Saved {saved} new writeups to database")

        for title, url in new_writeups:
            message = f"**New Write-up**: {title}\n{url}"
            send_discord_notification(webhook_url, message)
    else:
        logging.info("No new write-ups found")

def run_monitoring_task():
    if not setup_database():
        logging.error("Failed to initialize database")
        return

    webhook_url = 'your web hook'
    url_to_scrape = 'https://medium.com/tag/bug-bounty'

    while True:
        logging.info("Starting monitoring cycle...")
        monitor_bug_bounty_writeups(webhook_url, url_to_scrape)
        logging.info("Sleeping for 1 hour...")
        time.sleep(3600)

if __name__ == "__main__":
    run_monitoring_task()