import os
import sqlite3

from utils import get_logger, get_urlhash, normalize
from scraper import is_valid

class Frontier(object):
    def __init__(self, config, restart):
        self.logger = get_logger("FRONTIER")
        self.config = config
        self.to_be_downloaded = list()

        # Store crawler progress in a separate SQLite database.
        self.db_path = self.config.save_file + ".sqlite3"

        # If restarting from scratch, delete the previous crawl progress.
        if restart and os.path.exists(self.db_path):
            os.remove(self.db_path)

        # Allow worker threads to access the database connection.
        # Database operations will be synchronized using an RLock.
        self.save = sqlite3.connect(
            self.db_path,
            check_same_thread=False
        )

        # Store each discovered URL and whether it has been downloaded.
        # The URL hash serves as a unique key to prevent duplicates.
        self.save.execute("""
            CREATE TABLE IF NOT EXISTS frontier (
                urlhash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.save.commit()
        
        if restart:
            for url in self.config.seed_urls:
                self.add_url(url)
        else:
            # Set the frontier state with contents of save file.
            self._parse_save_file()
            if not self.save:
                for url in self.config.seed_urls:
                    self.add_url(url)

    def _parse_save_file(self):
        # Load previously discovered URLs from the database.
        rows = self.save.execute(
            "SELECT url, completed FROM frontier"
        ).fetchall()
        
        for url, completed in rows:
            # Only restore URLs that have not been downloaded.
            if not completed and is_valid(url):
                self.to_be_downloaded.append(url)
                
        self.logger.info(
            f"Found {len(self.to_be_downloaded)} urls to be "
            f"downloaded from {len(rows)} total urls discovered."
        )

    def get_tbd_url(self):
        try:
            return self.to_be_downloaded.pop()
        except IndexError:
            return None

    def add_url(self, url):
        url = normalize(url)
        urlhash = get_urlhash(url)
        
        # Insert the URL only if its hash is not already stored.
        cursor = self.save.execute(
            """
            INSERT OR IGNORE INTO frontier
            (urlhash, url, completed)
            VALUES (?, ?, 0)
            """,
            (urlhash, url)
        )
        self.save.commit()

        # Add only newly discovered URLs to the pending list.
        if cursor.rowcount == 1:
            self.to_be_downloaded.append(url)
    
    def mark_url_complete(self, url):
        urlhash = get_urlhash(url)

        # Mark the URL as downloaded so it won't be retried on restart.
        cursor = self.save.execute(
            """
            UPDATE frontier
            SET completed = 1
            WHERE urlhash = ?
            """,
            (urlhash,)
        )
        self.save.commit()

        if cursor.rowcount == 0:
            self.logger.error(
                f"Completed url {url}, but have not seen it before."
            )
