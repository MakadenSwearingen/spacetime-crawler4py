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
        ''' This function can be overridden for alternate saving techniques. '''
        total_count = len(self.save)
        tbd_count = 0
        for url, completed in self.save.values():
            if not completed and is_valid(url):
                self.to_be_downloaded.append(url)
                tbd_count += 1
        self.logger.info(
            f"Found {tbd_count} urls to be downloaded from {total_count} "
            f"total urls discovered.")

    def get_tbd_url(self):
        try:
            return self.to_be_downloaded.pop()
        except IndexError:
            return None

    def add_url(self, url):
        url = normalize(url)
        urlhash = get_urlhash(url)
        if urlhash not in self.save:
            self.save[urlhash] = (url, False)
            self.save.sync()
            self.to_be_downloaded.append(url)
    
    def mark_url_complete(self, url):
        urlhash = get_urlhash(url)
        if urlhash not in self.save:
            # This should not happen.
            self.logger.error(
                f"Completed url {url}, but have not seen it before.")

        self.save[urlhash] = (url, True)
        self.save.sync()
