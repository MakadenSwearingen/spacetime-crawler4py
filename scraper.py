import re
import sqlite3
from collections import Counter
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urldefrag, parse_qsl


STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can't",
    "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
    "doing", "don't", "down", "during", "each", "few", "for", "from",
    "further", "had", "hadn't", "has", "hasn't", "have", "haven't",
    "having", "he", "he'd", "he'll", "he's", "her", "here", "here's",
    "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't",
    "it", "it's", "its", "itself", "let's", "me", "more", "most",
    "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on",
    "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "shan't", "she", "she'd", "she'll",
    "she's", "should", "shouldn't", "so", "some", "such", "than", "that",
    "that's", "the", "their", "theirs", "them", "themselves", "then",
    "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's",
    "where", "where's", "which", "while", "who", "who's", "whom", "why",
    "why's", "with", "won't", "would", "wouldn't", "you", "you'd",
    "you'll", "you're", "you've", "your", "yours", "yourself",
    "yourselves"
}

# Report statistics are saved on disk (not in memory) so they survive
# Ctrl+C, crashes, and resuming the crawl without --restart.
#   pages: one row per unique (defragmented) URL, with its word count.
#   words: running count of every non-stop word across all pages.
STATS_DB = "crawl_stats.sqlite3"
stats_db = sqlite3.connect(STATS_DB, check_same_thread=False)
stats_db.execute("""
    CREATE TABLE IF NOT EXISTS pages (
        url TEXT PRIMARY KEY,
        hostname TEXT,
        word_count INTEGER NOT NULL
    )
""")
stats_db.execute("""
    CREATE TABLE IF NOT EXISTS words (
        word TEXT PRIMARY KEY,
        count INTEGER NOT NULL
    )
""")
stats_db.commit()

# Pages no larger than 5 MB.
MAX_CONTENT_BYTES = 5242880 

# Pages with fewer visible words than this are "low-information": they still
# count as unique pages, but we don't index their words or follow their links.
MIN_WORD_COUNT = 50


def scraper(url, resp):
    # Redirect (3xx): return the target URL so the crawler downloads
    # and indexes the redirected page on its own.
    if 300 <= resp.status < 400 and resp.raw_response is not None:
        location = resp.raw_response.headers.get("Location")
        if location:
            target = urldefrag(urljoin(url, location))[0]
            if is_valid(target):
                return {target}
        return set()

    # Only process successfully downloaded pages.
    if resp.status == 200 and resp.raw_response is not None:
        raw_content = resp.raw_response.content

        # Skip empty or oversized pages before parsing their HTML.
        # Since is_valid() validates a URL before the crawler downloads it. 
        # It cannot know the page's content size because it only receives a URL. 
        # That why we put it directly in the crawler.
        if not raw_content or len(raw_content) > MAX_CONTENT_BYTES:
            return set()

        # Only HTML pages hold the text we index. Skip binaries/data files
        # (zips, .war, source code, etc.) whose URL had no telltale extension.
        content_type = resp.raw_response.headers.get("Content-Type", "").lower()
        if content_type and "html" not in content_type:
            return set()

        # If the server followed a redirect, the content belongs to the final
        # URL, so that is the page we count. Skip it if the redirect led
        # somewhere we shouldn't crawl (outside our domains, a login page...).
        page_url = urldefrag(resp.raw_response.url)[0]
        if not is_valid(page_url):
            return set()

        # Extract links only from valid responses
        links = extract_next_links(url, resp)

        soup = BeautifulSoup(raw_content, "html.parser")

        # Remove elements that are not page text
        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        text = soup.get_text(" ")

        # Found the below technqiue from: https://4geeks.com/en/how-to/regex-letter. This finds words with uppercase or lowercase.
        # This version: words = re.findall(r"\b[a-zA-Z]+\b", text.lower()) is the old version that doesn't catch apostrophes.
        #The a-z text means: Find words made of letters, while allowing an apostrophe inside a word.
        words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", text.lower())
        low_information = len(words) < MIN_WORD_COUNT

        # Record this page; the URL primary key ignores pages we've
        # already counted (e.g. reached again through a redirect).
        cursor = stats_db.execute(
            "INSERT OR IGNORE INTO pages (url, hostname, word_count) VALUES (?, ?, ?)",
            (page_url, urlparse(page_url).hostname, len(words))
        )

        # Count words, ignoring stop words, only for new pages with real content.
        if cursor.rowcount == 1 and not low_information:
            counts = Counter(word for word in words if word not in STOP_WORDS)
            stats_db.executemany(
                "INSERT OR IGNORE INTO words (word, count) VALUES (?, 0)",
                ((word,) for word in counts)
            )
            stats_db.executemany(
                "UPDATE words SET count = count + ? WHERE word = ?",
                ((count, word) for word, count in counts.items())
            )

        # The page and its words are saved together in one commit.
        stats_db.commit()

        # Don't follow links out of low-information pages (e.g. empty calendar days).
        if low_information:
            return set()

        return {link for link in links if is_valid(link)}
    
    return set()

def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content

    # Only process successful responses that contain a response object.
    # This avoids accessing .content when the request failed or no response
    # object is available.
    if resp.status == 200 and resp.raw_response is not None:
        raw_content = resp.raw_response.content
    else:
        if resp.status != 200:
            print(f"Error occurred while fetching {url}: {resp.error}")
        return list()

    # Skip the dead page if the server returned 200 but sent no actual content.
    if not raw_content or not raw_content.strip():
        print(f"Skipping dead page (no content): {url}")
        return list()

    # Parse the HTML content so we can locate hyperlinks.
    soup = BeautifulSoup(raw_content, "html.parser")
        
    links = soup.find_all("a", href=True)

    extracted_links = []
    
    for link in links:
        # Convert relative URLs to absolute URLs using the current page's URL.
        # raw_response.url is the final URL after any redirect, which is what
        # relative links on the page are relative to.
        try:
            absolute_url = urljoin(resp.raw_response.url, link["href"])
        except ValueError:
            continue

        # Remove fragments (#section) to avoid treating the same page as different URLs.
        absolute_url = urldefrag(absolute_url)[0]

        # Add the processed URL to our list.
        extracted_links.append(absolute_url)
        
    return extracted_links

def is_valid(url):
    # Decide whether to crawl this url or not. 
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
        parsed = urlparse(url)

        # Only send the server plain ASCII URLs (no Unicode or whitespace garbage).
        if not url.isascii() or re.search(r"\s", url):
            return False

        # Only allow HTTP and HTTPS URLs.
        if parsed.scheme not in set(["http", "https"]):
            return False

        hostname = parsed.hostname

        # Reject URLs without a valid hostname.
        if hostname is None:
            return False

        # Restrict crawling to the four assigned UCI domains
        # and their subdomains.
        if not (
            hostname == "ics.uci.edu" or hostname.endswith(".ics.uci.edu")
            or hostname == "cs.uci.edu" or hostname.endswith(".cs.uci.edu")
            or hostname == "informatics.uci.edu" or hostname.endswith(".informatics.uci.edu")
            or hostname == "stat.uci.edu" or hostname.endswith(".stat.uci.edu")
        ):
            return False

        # Avoid excessively deep URL paths that may indicate crawler traps.
        if len([part for part in parsed.path.split("/") if part]) > 10:
            return False
            
        # Avoid URLs with excessive query parameters that may indicate crawler traps.
        if len(parse_qsl(parsed.query, keep_blank_values=True)) > 5:
            return False

        # Avoid calendar traps caused by endless date navigation.
        calendar_keywords = {"calendar", "calendars", "events"}
        
        if any(part in calendar_keywords for part in parsed.path.lower().split("/")):
            if re.search(r"/\d{4}/\d{1,2}(?:/|$)", parsed.path):
                return False

            if re.search(r"/day/\d{4}-\d{2}-\d{2}(?:/|$)", parsed.path):
                return False

            if re.search(r"/\d{4}-\d{2}(?:-\d{2})?(?:/|$)", parsed.path):
                return False
        
            if any(key.lower() in  {
                "year", "month", "date", "tribe-bar-date",
                "ical", "outlook-ical", "eventdisplay"
            } for key, value in parse_qsl(parsed.query)):
                return False

        # Avoid excessive pagination that may indicate a crawler trap.
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() in {"page", "p", "pg"}:
                if value.isdigit() and int(value) > 100:
                    return False

        # Avoid session IDs that may generate endless unique URLs.
        session_params = {"sessionid", "session_id", "phpsessid", "jsessionid"}
        
        if any(key.lower() in session_params
               for key, value in parse_qsl(parsed.query, keep_blank_values=True)):
            return False

        # Avoid excessively long URLs that may indicate crawler traps.
        if len(url) > 2048:
            return False

        # Avoid URLs that would require user login/authentication
        # (including WordPress's wp-login.php, used across several subdomains).
        if any(part in {"login", "signin", "auth", "oauth2", "wp-login.php"}
            for part in parsed.path.lower().split("/")):
                return False

        # Avoid wiki version history traps.
        if any(key.lower() in {"version", "action", "format", "precision"}
               for key, value in parse_qsl(parsed.query)):
            return False

        # Avoid common UI navigation and media-manager traps.
        trap_params = {
            "tab_details",
            "tab_files",
            "do",
            "image",
            "ns",
            "idx",
            "version",
            "precision",
        }
        
        if any(key.lower() in trap_params
               for key, value in parse_qsl(parsed.query)):
            return False

        # Avoid wiki file attachments (zips, raw downloads). This must come
        # before the final return below, otherwise it never runs.
        if any(part in {"zip-attachment", "raw-attachment", "attachment"}
            for part in parsed.path.lower().split("/")):
                return False

        # Skip non-HTML files such as images, documents, archives,
        # and other file types that are not useful for our crawler.
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|war|apk|mpg|ppsx|pps|class|npy|h5|mol|sdf|smi"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())

    # Reject malformed URLs instead of interrupting the crawler.
    except (TypeError, ValueError):
        return False


def reset_statistics():
    # Clear saved statistics when the crawl restarts from scratch (--restart).
    stats_db.execute("DELETE FROM pages")
    stats_db.execute("DELETE FROM words")
    stats_db.commit()


def print_statistics():
    # Answers the four report questions from the saved statistics.
    unique_pages = stats_db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    longest_page = stats_db.execute(
        "SELECT url, word_count FROM pages ORDER BY word_count DESC LIMIT 1"
    ).fetchone() or ("", 0)
    common_words = stats_db.execute(
        "SELECT word, count FROM words ORDER BY count DESC LIMIT 50"
    ).fetchall()
    subdomains = stats_db.execute(
        "SELECT hostname, COUNT(*) FROM pages WHERE hostname LIKE '%.ics.uci.edu' "
        "GROUP BY hostname ORDER BY hostname"
    ).fetchall()

    print("\n===== PAGE STATISTICS =====")

    print("Unique pages:", unique_pages)

    print("\nLongest page:")
    print("URL:", longest_page[0])
    print("Word count:", longest_page[1])

    print("\n50 most common words:")
    for word, count in common_words:
        print(word, count)

    # Lines are "URL, number" as the assignment asks, in alphabetical order.
    print("\nics.uci.edu subdomains:", len(subdomains))
    for subdomain, count in subdomains:
        print(f"http://{subdomain}, {count}")


# Run "python scraper.py" at any time (even after Ctrl+C) to print the report.
if __name__ == "__main__":
    print_statistics()
