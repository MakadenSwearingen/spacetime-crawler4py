import re
from collections import Counter
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urldefrag


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

visited_pages = set()
word_counts = Counter()
longest_page = ("", 0)
subdomain_counts = Counter()

# Pages no larger than 5 MB.
MAX_CONTENT_BYTES = 5242880 

# Pages with fewer visible words than MIN_WORD_COUNT will be considered "low-information"
MIN_WORD_COUNT = 50

#

def scraper(url, resp):
    global visited_pages, word_counts, longest_page, subdomain_counts

    links = extract_next_links(url, resp)


    #Double checks if the page has been downloaded
    if resp.status == 200 and resp.raw_response is not None:
        soup = BeautifulSoup(resp.raw_response.content, "html.parser")

        # Remove elements that are not page text
        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        text = soup.get_text(" ")

        # Found the below technqiue from: https://4geeks.com/en/how-to/regex-letter. This finds words with uppercase or lowercase.
        # This version: words = re.findall(r"\b[a-zA-Z]+\b", text.lower()) is the old version that doesn't catch apostrophes.
        #The a-z text means: Find words made of letters, while allowing an apostrophe inside a word.
        words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", text.lower())

        # Remove fragment and count unique pages
        page_url = urldefrag(resp.url)[0]
        visited_pages.add(page_url)

        # Check if this is the longest page
        word_count = len(words)
        if word_count > longest_page[1]:
            longest_page = (resp.url, word_count)

        # Count words, ignoring stop words
        for word in words:
            if word not in STOP_WORDS:
                word_counts[word] += 1

        # Count ics.uci.edu subdomains
        hostname = urlparse(resp.url).hostname
        if hostname and hostname.endswith(".ics.uci.edu"):
            subdomain_counts[hostname] += 1

    return {link for link in links if is_valid(link)}

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

    # Skip very large pages before parsing them.
    if len(raw_content) > MAX_CONTENT_BYTES:
        print(f"Skipping large page ({len(raw_content)} bytes): {url}") # An ASCII character is 1 byte, hence "len()".
        return list()

    # Parse the HTML content so we can locate hyperlinks.
    soup = BeautifulSoup(raw_content, "html.parser")

    # Skip low-information pages. Only count visible words, so remove <script> and <style> blocks first, since their contents are not text.
    for tag in soup(["script", "style"]):
        tag.decompose() # Removes any text between, for example, <script></script>.
    word_count = len(soup.get_text(separator=" ").split()) # Separates each segment of text with a space, then separates the entire string into a list.
    if word_count < MIN_WORD_COUNT: # Skip page if the words we found are less than our threshold.
        print(f"Skipping low-information page ({word_count} words): {url}")
        return list()
        
    links = soup.find_all("a", href=True)

    extracted_links = []
    
    for link in links:
        # Convert relative URLs to absolute URLs using the current page's URL.
        absolute_url = urljoin(resp.url, link["href"])

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

        # Make sure URLs have only valid alphanumeric characters,
        # forward slashes also acceptable of course.
        if not re.match(r'^[A-Za-z0-9/]+$', parsed.path()):
            return False

        # Avoid URLs that would require user login/authentication.
        if re.match(r"/*\.(auth|login|signin|oauth2)$", parsed.path()):
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
                + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())

    # Handle a TypeError if one occurs inside try.
    except TypeError:
        print ("TypeError for ", parsed)
        raise




def print_statistics():
    print("\n===== PAGE STATISTICS =====")

    print("Unique pages:", len(visited_pages))

    print("\nLongest page:")
    print("URL:", longest_page[0])
    print("Word count:", longest_page[1])

    print("\n50 most common words:")
    for word, count in word_counts.most_common(50):
        print(word, count)

    print("\nics.uci.edu subdomains:")
    for subdomain in sorted(subdomain_counts):
        print(subdomain, subdomain_counts[subdomain])
