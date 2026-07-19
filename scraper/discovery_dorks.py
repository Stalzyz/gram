import re
import time
import requests
import urllib.parse
import random
from utils.logger import get_logger
from utils.proxy_manager import ProxyManager

logger = get_logger()

class DorkScraper:
    def __init__(self, proxies=None):
        self.session = requests.Session()
        self.proxy_manager = ProxyManager(proxies=proxies)
        # A list of common user agents to rotate
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        ]
        
    def extract_usernames(self, html_content: str) -> set:
        """
        Regex to find instagram.com/username patterns in the HTML.
        """
        usernames = set()
        # Look for instagram.com/some_username 
        # IG usernames can contain letters, numbers, periods, and underscores. Max 30 chars.
        pattern = r"instagram\.com/([a-zA-Z0-9_\.]{1,30})[/\"\'\?]"
        matches = re.findall(pattern, html_content)
        
        for match in matches:
            username = match.lower().strip('.')
            # Filter out generic IG paths that aren't real target users
            ignore_list = {'p', 'reel', 'explore', 'about', 'developer', 'legal', 'directory', 'stories', 'tv'}
            if username and username not in ignore_list:
                usernames.add(username)
                
        return usernames

    def search_duckduckgo(self, query: str, num_pages: int = 3) -> set:
        """
        Scrape DuckDuckGo Lite for the query.
        """
        logger.info(f"Starting DuckDuckGo search for: {query}")
        results = set()
        url = "https://lite.duckduckgo.com/lite/"
        
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # Initial search POST
        data = {"q": query}
        proxies = self.proxy_manager.next() if self.proxy_manager.enabled else None
        
        try:
            resp = self.session.post(url, headers=headers, data=data, proxies=proxies, timeout=15)
            if resp.status_code == 200:
                page_usernames = self.extract_usernames(resp.text)
                results.update(page_usernames)
                logger.info(f"Page 1: Found {len(page_usernames)} usernames.")
            
            # Since DDG lite pagination requires parsing next form params, 
            # for a robust simple script without BeautifulSoup we might only get page 1 reliably.
            # However, we can also use Bing as a fallback which uses GET params.
        except Exception as e:
            logger.error(f"Error during DuckDuckGo search: {e}")
            
        return results
        
    def search_bing(self, query: str, num_pages: int = 3) -> set:
        """
        Scrape Bing search results using GET pagination.
        """
        logger.info(f"Starting Bing search for: {query}")
        results = set()
        base_url = "https://www.bing.com/search"
        
        for page in range(num_pages):
            # Bing pagination: first=1, first=11, first=21
            first = (page * 10) + 1
            params = {
                "q": query,
                "first": first
            }
            headers = {
                "User-Agent": random.choice(self.user_agents),
                "Accept-Language": "en-US,en;q=0.9"
            }
            proxies = self.proxy_manager.next() if self.proxy_manager.enabled else None
            
            try:
                resp = self.session.get(base_url, params=params, headers=headers, proxies=proxies, timeout=15)
                if resp.status_code == 200:
                    page_usernames = self.extract_usernames(resp.text)
                    results.update(page_usernames)
                    logger.info(f"Bing Page {page+1}: Found {len(page_usernames)} usernames.")
                else:
                    logger.warning(f"Bing returned status {resp.status_code}. Rate limited?")
                    break
            except Exception as e:
                logger.error(f"Error during Bing search: {e}")
                
            time.sleep(random.uniform(2.0, 4.0)) # Polite delay
            
        return results

    def discover_leads(self, keyword: str, platform: str = None, limit: int = 50) -> list:
        """
        Constructs the dork query and aggregates results until limit is reached.
        """
        # Construct Dork
        dork = f'site:instagram.com "{keyword}"'
        if platform:
            dork += f' "{platform}"'
            
        all_usernames = set()
        
        # Try Bing first
        bing_results = self.search_bing(dork, num_pages=5)
        all_usernames.update(bing_results)
        
        if len(all_usernames) < limit:
            # Try DDG if we need more
            ddg_results = self.search_duckduckgo(dork)
            all_usernames.update(ddg_results)
            
        final_list = list(all_usernames)
        return final_list[:limit]
