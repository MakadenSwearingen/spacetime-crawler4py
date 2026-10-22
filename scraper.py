import re
from urllib.parse import urlparse, urljoin, urldefrag

def scraper(url, resp):
    links = extract_next_links(url, resp)
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

    # Parse the HTML content so we can locate hyperlinks.
    soup = BeautifulSoup(raw_content, "html.parser")
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