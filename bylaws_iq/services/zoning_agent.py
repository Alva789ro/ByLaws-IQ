"""
========================================================================================================
MODULAR ZONING AGENTS - Intelligent Zoning Discovery & Analysis System
========================================================================================================

This file contains specialized agents for zoning discovery and analysis:

1. BaseZoningAgent: Shared infrastructure and utilities
2. ZoningMapAgent: Specialized for zoning map discovery and analysis  
3. ZoningBylawsAgent: Specialized for bylaws discovery and analysis
4. CombinedZoningAgent: Orchestrates both agents with unified interface

ARCHITECTURE:
┌─ BaseZoningAgent (shared utilities)
├─ ZoningMapAgent (extends base)
├─ ZoningBylawsAgent (extends base)
└─ CombinedZoningAgent (composes both agents)

Uses intelligent web navigation powered by Gemini 2.5 Pro for complex analysis
and Gemini Flash 1.5 for classification tasks.
========================================================================================================
"""

import os
import re
import json
import logging
import requests
import time
import random
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from ..logging_config import configure_logging, span
from . import search

# Selenium imports for JavaScript content handling
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager


# =====================================
# 1. SHARED BASE INFRASTRUCTURE
# =====================================

class BaseZoningAgent:
    """
    Base class providing shared infrastructure for all zoning agents
    
    Contains common utilities for:
    - WebDriver management
    - LLM interactions  
    - Web scraping
    - Official website discovery
    """
    
    def __init__(self, agent_name: str = "base"):
        configure_logging()
        self.logger = logging.getLogger(f"bylaws_iq.{agent_name}")
        load_dotenv()
        self.model = "google/gemini-2.5-pro"  # For complex PDF analysis tasks
        self.classification_model = "google/gemini-flash-1.5"  # For cheap classification tasks
        self.logger.debug(f"agent.init: Using model {self.model} for complex tasks, {self.classification_model} for classification")
        
        # Shared resources
        self.driver = None  # WebDriver instance
        self.downloaded_pdfs = {}  # Track downloaded PDFs {url: {filename, source_pages}}


    # SHARED WEBDRIVER MANAGEMENT
    def _init_webdriver(self) -> webdriver.Chrome:
        """
        Initialize Chrome WebDriver with optimal settings for municipal website parsing
        """
        if self.driver is not None:
            return self.driver
            
        with span(self.logger, "webdriver.init"):
            # Configure Chrome options for headless operation with enhanced anti-bot detection
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in background
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Enhanced anti-bot detection bypass
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--allow-running-insecure-content")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-default-apps")
            chrome_options.add_argument("--disable-sync")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--disable-background-networking")
            chrome_options.add_argument("--disable-features=VizDisplayCompositor")
            chrome_options.add_argument("--disable-ipc-flooding-protection")
            
            # Set realistic user agent (updated to latest Chrome)
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Try multiple approaches for ChromeDriver initialization
            driver = None
            
            # Approach 1: Try webdriver-manager with cache clearing
            try:
                self.logger.info("webdriver.attempt1: Trying ChromeDriverManager with fresh download")
                import shutil
                
                # Clear webdriver-manager cache on macOS to avoid corrupted downloads
                cache_dir = os.path.expanduser("~/.wdm")
                if os.path.exists(cache_dir):
                    self.logger.info(f"webdriver.clearing_cache: Removing {cache_dir}")
                    shutil.rmtree(cache_dir, ignore_errors=True)
                
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                self.logger.info("webdriver.success1: ChromeDriverManager worked")
                
            except Exception as e1:
                self.logger.warning(f"webdriver.attempt1_failed: ChromeDriverManager failed: {str(e1)}")
                
                # Approach 2: Try system Chrome installation
                try:
                    self.logger.info("webdriver.attempt2: Trying system Chrome paths")
                    
                    # Common Chrome paths on macOS
                    chrome_paths = [
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                        "/usr/bin/google-chrome",
                        "/usr/local/bin/chromedriver",
                        "/opt/homebrew/bin/chromedriver"
                    ]
                    
                    for chrome_path in chrome_paths:
                        if os.path.exists(chrome_path):
                            self.logger.info(f"webdriver.found_chrome: Using {chrome_path}")
                            if 'chromedriver' in chrome_path:
                                service = Service(chrome_path)
                            else:
                                chrome_options.binary_location = chrome_path
                                service = Service()
                            
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                            self.logger.info("webdriver.success2: System Chrome worked")
                            break
                            
                except Exception as e2:
                    self.logger.warning(f"webdriver.attempt2_failed: System Chrome failed: {str(e2)}")
                    
                    # Approach 3: Try without service (let Selenium find Chrome)
                    try:
                        self.logger.info("webdriver.attempt3: Trying default Chrome detection")
                        driver = webdriver.Chrome(options=chrome_options)
                        self.logger.info("webdriver.success3: Default Chrome detection worked")
                        
                    except Exception as e3:
                        self.logger.error(f"webdriver.attempt3_failed: Default Chrome failed: {str(e3)}")
                        raise WebDriverException(f"All WebDriver initialization methods failed. Last error: {str(e3)}")
            
            if driver is None:
                raise WebDriverException("Could not initialize WebDriver with any method")
            
            # Enhanced anti-detection setup
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Add realistic browser properties
            driver.execute_script("""
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [{
                        name: 'Chrome PDF Plugin',
                        filename: 'internal-pdf-viewer',
                        description: 'Portable Document Format'
                    }, {
                        name: 'Chrome PDF Viewer',
                        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                        description: ''
                    }, {
                        name: 'Native Client',
                        filename: 'internal-nacl-plugin',
                        description: ''
                    }]
                });
                
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'MacIntel'
                });
                
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });
                
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });
                
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 0
                });
                
                // Add screen properties
                Object.defineProperty(screen, 'availWidth', {
                    get: () => 1920
                });
                
                Object.defineProperty(screen, 'availHeight', {
                    get: () => 1080
                });
                
                // Mock WebGL and Canvas fingerprinting
                const getParameter = WebGLRenderingContext.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter(parameter);
                };
            """)
            
            self.driver = driver
            self.logger.info(f"webdriver.ready: Chrome WebDriver initialized successfully")
            return driver
    
    def _cleanup_webdriver(self):
        """
        Clean up WebDriver resources
        """
        if self.driver:
            try:
                self.driver.quit()
                self.logger.debug("webdriver.cleanup: WebDriver closed successfully")
            except Exception as e:
                self.logger.warning(f"webdriver.cleanup_error: {str(e)}")
            finally:
                self.driver = None

    # SHARED LLM UTILITIES
    def _call_llm(self, prompt: str) -> str:
        """Call the LLM using OpenRouter without forcing JSON format"""
        
        try:
            load_dotenv()
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY not set")
            
            system_message = """You are an expert web navigation agent specializing in finding official municipal zoning maps. You understand the difference between zoning maps (visual/graphic PDFs) and zoning codes/ordinances (text documents). You prioritize official, recent, and authoritative sources."""
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://bylaws-iq.local",
                "X-Title": "ByLaws-IQ Agent",
                "Content-Type": "application/json",
            }
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
            
            payload = {
                "model": self.model,
                "temperature": 0.1,
                "messages": messages,
                # NOTE: No response_format forcing JSON - we want text responses
            }
            
            self.logger.debug(f"llm.call_start: model={self.model}")
            
            import httpx
            with httpx.Client(timeout=60) as client:
                r = client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                r.raise_for_status()
                js = r.json()
            
            response = js["choices"][0]["message"]["content"]
            self.logger.debug(f"llm.call_success: response_length={len(response)}")
            return response
            
        except Exception as e:
            self.logger.error(f"llm.call_failed: {str(e)}", exc_info=True)
            raise e

    # SHARED WEBSITE UTILITIES  
    def _find_city_in_mma(self, city: str) -> Optional[str]:
        """
        Look up city official website from MMA directory on-demand
        
        Args:
            city (str): City name to look up
            
        Returns:
            str or None: Official website URL if found
        """
        try:
            self.logger.info(f"mma.lookup_start: Looking up {city} in MMA directory")
            
            import requests
            from urllib.parse import urljoin
            
            # Fetch the MMA page with proper headers to avoid blocking
            mma_url = "https://www.mma.org/members/member-communities/city-and-town-websites/#all"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            self.logger.info(f"mma.request_start: Fetching MMA directory from {mma_url}")
            
            # Add small delay to be respectful to the MMA website
            time.sleep(1)
            
            try:
                response = requests.get(mma_url, headers=headers, timeout=30)
                self.logger.info(f"mma.response_status: {response.status_code}")
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                self.logger.error(f"mma.http_error: {e.response.status_code} {e.response.reason}")
                if e.response.status_code == 403:
                    self.logger.error("mma.blocked: MMA website is blocking requests - this may be temporary")
                raise
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for the city in anchor tags (links)
            for link in soup.find_all('a', href=True):
                link_text = link.get_text(strip=True)
                href = link['href']
                
                # Skip empty links or non-website links
                if not href or href.startswith('#') or 'mailto:' in href:
                    continue
                    
                # Normalize city name for comparison
                city_normalized = city.lower().replace(' ', '').replace('.', '')
                link_text_normalized = link_text.lower().replace(' ', '').replace('.', '')
                
                # Check for exact match first
                if city_normalized == link_text_normalized:
                    if href.startswith('http'):
                        url = href
                    else:
                        url = urljoin("https://www.mma.org", href)
                    
                    self.logger.info(f"mma.exact_match: {city} -> {url}")
                    return url
                
                # Check if city name is contained in the link text
                if city_normalized in link_text_normalized:
                    if href.startswith('http'):
                        url = href  
                    else:
                        url = urljoin("https://www.mma.org", href)
                    
                    self.logger.info(f"mma.partial_match: {city} matched '{link_text}' -> {url}")
                    return url
                
                # Also check if any word in the city name appears in the link
                city_words = city_normalized.replace(',', ' ').split()
                for word in city_words:
                    if len(word) > 3 and word in link_text_normalized:  # Avoid short words
                        if href.startswith('http'):
                            url = href
                        else:
                            url = urljoin("https://www.mma.org", href)
                        
                        # Extract the matching part for logging
                        for name_part in link_text.split():
                            if word in name_part.lower().replace('.', ''):
                                self.logger.info(f"mma.match_found: {city} matched '{name_part}' -> {url}")
                                return url
            
            self.logger.warning(f"mma.not_found: No entry found for {city} in MMA directory")
            return None
            
        except Exception as e:
            self.logger.error(f"mma.search_failed: {str(e)}", exc_info=True)
            return None


# =====================================
# 2. ZONING MAP AGENT (Specialized for Maps)
# =====================================

class ZoningMapAgent(BaseZoningAgent):
    """
    Specialized agent for zoning map discovery and analysis
    
    Handles:
    - Finding official zoning maps from municipal websites
    - Analyzing maps to extract zoning district information
    """
    
    def __init__(self):
        super().__init__("zoning_map_agent")
    
    def find_zoning_district(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Complete workflow to find zoning district for an address
        
        Args:
            address (str): Full address to analyze
            
        Returns:
            dict: Zoning district information including code, name, overlays, and source URL
                  or None if discovery fails
        """
        try:
            # Step 1: Parse address to extract city and state
            parts = [part.strip() for part in address.split(',')]
            
            if len(parts) >= 2:
                if len(parts) == 3:
                    # Format: "123 Street, City, MA"
                    city_part = parts[1].strip()
                    state_part = parts[2].strip()
                else:
                    # Format: "123 Street, City MA" - parse the last part
                    last_part = parts[-1].strip()
                    words = last_part.split()
                    if len(words) >= 2:
                        potential_state = words[-1].upper()
                        if potential_state in ['MA', 'MASSACHUSETTS']:
                            state_part = words[-1]
                            city_part = ' '.join(words[:-1]).strip()
                        else:
                            self.logger.error(f"address.parse_failed: Could not identify state in '{address}'")
                            return None
                    else:
                        self.logger.error(f"address.parse_failed: Unexpected format in '{address}'")
                        return None
            else:
                self.logger.error(f"address.parse_failed: Not enough parts in '{address}'")
                return None
            
            self.logger.info(f"address.parsed: City={city_part}, State={state_part}")
            
            # Step 2: Find official zoning map
            zoning_map_url, map_metadata = self.find_official_zoning_map(city_part, state_part)
            
            if not zoning_map_url:
                self.logger.warning(f"zoning.discovery_failed: No zoning map found for {city_part}, {state_part}")
                return None
            
            self.logger.info(f"zoning.map_found: {zoning_map_url}")
            
            # Step 3: Analyze zoning map to determine district
            zoning_analysis = self.analyze_zoning_district(zoning_map_url, address)
            
            if not zoning_analysis:
                self.logger.warning(f"zoning.analysis_failed: Could not determine zoning district from map")
                return None
            
            # Combine results
            result = dict(zoning_analysis)
            result['zoning_map_url'] = zoning_map_url
            
            self.logger.info(f"✅ Zoning district discovery successful for {address}")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Zoning discovery failed for {address}: {str(e)}", exc_info=True)
            return None
    
    def find_official_zoning_map(self, city: str, state: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Main agent entry point - find the most up-to-date official zoning map
        """
        with span(self.logger, "agent.discover_zoning_map"):
            self.logger.info(f"agent.start: Finding zoning map for {city}, {state}")
            
            try:
                # Step 1: Find official municipal website
                official_website = self._find_official_website(city, state)
                if not official_website:
                    self.logger.warning(f"agent.no_website: Could not find official website for {city}, {state}")
                    return None, None
                
                # Step 2: Navigate through the official jurisdiction website using Selenium
                zoning_map_url = self._navigate_jurisdiction_website(official_website, city, state)
                
                if zoning_map_url:
                    metadata = self._extract_map_metadata(zoning_map_url, city, state)
                    self.logger.info(f"agent.success: Found {zoning_map_url}")
                    return zoning_map_url, metadata
                
                # Step 3: Find the latest Zoning Map of the jurisdiction (PLACEHOLDER)
                fallback_result = self._find_latest_zoning_map(official_website, city, state)
                if fallback_result[0]:
                    self.logger.info(f"agent.fallback_success: {fallback_result[0]}")
                    return fallback_result
                
                self.logger.warning(f"agent.failure: No zoning map found for {city}, {state}")
                return None, None
            
            except Exception as e:
                self.logger.error(f"agent.error: {str(e)}", exc_info=True)
                return None, None
            
            finally:
                # Ensure WebDriver cleanup even if something goes wrong
                self._cleanup_webdriver()
    
    def _find_official_website(self, city: str, state: str) -> Optional[str]:
        """Find the official municipal website using on-demand MMA directory lookup"""
        
        with span(self.logger, "agent.find_website"):
            self.logger.info(f"agent.website_lookup: {city}, {state}")
            
            # Only handle Massachusetts cities (since we have MMA data)
            if not ('massachusetts' in state.lower() or 'ma' == state.lower()):
                self.logger.warning(f"agent.non_ma_state: {state} not supported (only MA available)")
                return None
            
            # Look up this specific city in the MMA directory
            official_url = self._find_city_in_mma(city)
            
            if official_url:
                self.logger.info(f"mma.found: {city} -> {official_url}")
                # Cache the official website for reuse by bylaws agent
                self._last_official_website = official_url
                return official_url
            else:
                self.logger.warning(f"mma.not_found: No MMA entry found for {city}, {state}")
                return None
    
    def _navigate_jurisdiction_website(self, official_website: str, city: str, state: str) -> Optional[str]:
        """
        Navigate through the official jurisdiction website using Selenium WebDriver for JavaScript content
        
        This method uses Selenium to handle dynamic content loading:
        1. Initialize WebDriver and navigate to the website
        2. Find and interact with search forms/inputs
        3. Wait for JavaScript-rendered search results to load
        4. Parse the fully-loaded results for zoning map PDFs
        5. Return the most recent zoning map
        
        Args:
            official_website: The official municipal website URL
            city: City name
            state: State name
            
        Returns:
            URL to the zoning map PDF, or None if not found
        """
        with span(self.logger, "agent.selenium_navigate"):
            self.logger.info(f"🌐 SELENIUM NAVIGATION: Using WebDriver for {city}'s website search")
            
            driver = None
            try:
                # Step 1: Initialize WebDriver
                driver = self._init_webdriver()
                
                # Step 2: Perform the search with JavaScript execution
                search_results = self._selenium_search_zoning_maps(driver, official_website, city)
                
                if not search_results:
                    self.logger.warning(f"selenium.primary_search_failed: No zoning map results found via primary search")
                    
                    # FALLBACK: Try Map Library approach
                    self.logger.info(f"🔄 FALLBACK: Attempting Map Library discovery for {city}")
                    fallback_result = self._fallback_maps_library_search(driver, official_website, city)
                    
                    if fallback_result:
                        self.logger.info(f"🎯 FALLBACK SUCCESS: Found zoning map via Map Library -> {fallback_result}")
                        
                        # Download for verification
                        downloaded_path = self._download_and_verify_pdf(fallback_result, city)
                        if downloaded_path:
                            self.logger.info(f"📁 PDF DOWNLOADED FOR REVIEW: {downloaded_path}")
                        
                        return fallback_result
                    else:
                        self.logger.warning(f"selenium.fallback_failed: Map Library approach also failed")
                        return None

                # Step 3: Select the most recent zoning map using LLM
                best_zoning_map = self._select_most_recent_zoning_map(search_results, city)
                
                if best_zoning_map:
                    self.logger.info(f"🎯 PRIMARY SUCCESS: Found most recent zoning map -> {best_zoning_map}")
                    
                    # Step 4: Download for verification
                    downloaded_path = self._download_and_verify_pdf(best_zoning_map, city)
                    if downloaded_path:
                        self.logger.info(f"📁 PDF DOWNLOADED FOR REVIEW: {downloaded_path}")
                    
                    return best_zoning_map
                else:
                    self.logger.warning(f"selenium.primary_selection_failed: No valid zoning maps selected from primary results")
                    
                    # FALLBACK: Try Map Library approach
                    self.logger.info(f"🔄 FALLBACK: Attempting Map Library discovery for {city}")
                    fallback_result = self._fallback_maps_library_search(driver, official_website, city)
                    
                    if fallback_result:
                        self.logger.info(f"🎯 FALLBACK SUCCESS: Found zoning map via Map Library -> {fallback_result}")
                        
                        # Download for verification
                        downloaded_path = self._download_and_verify_pdf(fallback_result, city)
                        if downloaded_path:
                            self.logger.info(f"📁 PDF DOWNLOADED FOR REVIEW: {downloaded_path}")
                        
                        return fallback_result
                    else:
                        self.logger.warning(f"selenium.all_methods_failed: Both primary and fallback methods failed")
                        return None
                    
            except Exception as e:
                self.logger.error(f"selenium.navigation_error: {str(e)}", exc_info=True)
                return None
            finally:
                # Clean up WebDriver resources
                if driver:
                    self._cleanup_webdriver()
    
    def _selenium_search_zoning_maps(self, driver: webdriver.Chrome, website_url: str, city: str) -> List[Dict[str, Any]]:
        """
        Use Selenium WebDriver to search for zoning maps on municipal websites with JavaScript support
        
        This method handles dynamic content loading and various search interface types:
        1. Navigate to the website
        2. Detect and interact with search forms/inputs
        3. Submit search query for "zoning map"
        4. Wait for JavaScript results to load
        5. Extract structured data from the rendered results
        
        Args:
            driver: Selenium WebDriver instance
            website_url: Municipal website URL
            city: City name for logging context
            
        Returns:
            List of search result dictionaries with title, date, url, is_pdf, context
        """
        with span(self.logger, "selenium.search"):
            try:
                self.logger.info(f"selenium.navigate: Loading {website_url}")
                
                # Step 1: Navigate to the website
                driver.get(website_url)
                
                # Wait for initial page load
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                self.logger.info(f"selenium.page_loaded: Page loaded successfully")
                
                # Step 2: Find and interact with search functionality
                search_query = "zoning map"
                search_performed = False
                
                # Strategy 1: Look for search input fields
                search_inputs = driver.find_elements(By.CSS_SELECTOR, 
                    'input[type="search"], input[type="text"][placeholder*="search" i], input[type="text"][name*="search" i], input[id*="search" i], input[class*="search" i]')
                
                for search_input in search_inputs:
                    if search_input.is_displayed() and search_input.is_enabled():
                        try:
                            self.logger.info(f"selenium.search_input: Found search input, submitting query")
                            search_input.clear()
                            search_input.send_keys(search_query)
                            search_input.send_keys(Keys.RETURN)
                            search_performed = True
                            break
                        except Exception as e:
                            self.logger.warning(f"selenium.search_input_failed: {str(e)}")
                            continue
                
                # Strategy 2: Look for search buttons to click
                if not search_performed:
                    search_buttons = driver.find_elements(By.CSS_SELECTOR, 
                        'button[type="submit"], button[class*="search" i], input[type="submit"][value*="search" i], a[href*="search" i]')
                    
                    for button in search_buttons:
                        if button.is_displayed() and button.is_enabled():
                            try:
                                # First, fill any nearby search input
                                parent = button.find_element(By.XPATH, "./..")
                                nearby_inputs = parent.find_elements(By.CSS_SELECTOR, 'input[type="text"], input[type="search"]')
                                
                                if nearby_inputs:
                                    nearby_inputs[0].clear()
                                    nearby_inputs[0].send_keys(search_query)
                                
                                self.logger.info(f"selenium.search_button: Clicking search button")
                                driver.execute_script("arguments[0].click();", button)
                                search_performed = True
                                break
                            except Exception as e:
                                self.logger.warning(f"selenium.search_button_failed: {str(e)}")
                                continue
                
                # Strategy 3: Try direct navigation to common search URLs
                if not search_performed:
                    search_urls = [
                        f"{website_url.rstrip('/')}/Search?searchPhrase=zoning+map",
                        f"{website_url.rstrip('/')}/search?q=zoning+map",
                        f"{website_url.rstrip('/')}/search/default.aspx?q=zoning+map",
                        f"{website_url.rstrip('/')}/site-search/?search=zoning+map"
                    ]
                    
                    for search_url in search_urls:
                        try:
                            self.logger.info(f"selenium.direct_search: Trying direct search URL: {search_url}")
                            driver.get(search_url)
                            
                            # Wait a moment for page to load
                            time.sleep(2)
                            
                            # Check if we got search results
                            page_source = driver.page_source.lower()
                            if any(indicator in page_source for indicator in ['search results', 'results for', 'found', 'documentcenter', 'zoning']):
                                search_performed = True
                                self.logger.info(f"selenium.direct_success: Direct search URL worked")
                                break
                                
                        except Exception as e:
                            self.logger.warning(f"selenium.direct_search_failed: {str(e)}")
                            continue
                
                if not search_performed:
                    self.logger.warning(f"selenium.no_search: Could not find or execute search on {website_url}")
                    return []
                
                # Step 3: Wait for search results to load (JavaScript execution)
                self.logger.info(f"selenium.waiting_results: Waiting for search results to load...")
                
                try:
                    # Wait for either search results or error messages
                    WebDriverWait(driver, 15).until(
                        lambda d: (
                            len(d.find_elements(By.CSS_SELECTOR, 'a[href*="pdf" i], a[href*="documentcenter" i], a[href*=".pdf"], .search-result, .result-item')) > 0 or
                            'no results' in d.page_source.lower() or
                            'no matches' in d.page_source.lower()
                        )
                    )
                except TimeoutException:
                    self.logger.warning(f"selenium.timeout: Timeout waiting for search results")
                
                # Step 4: Extract and parse the loaded results
                page_source = driver.page_source
                self.logger.info(f"selenium.extract_results: Extracting results from {len(page_source)} characters of content")
                
                # Use our existing LLM parsing but with the fully-loaded Selenium content
                search_results = self._selenium_parse_results(page_source, city, driver.current_url)
                
                self.logger.info(f"selenium.results_found: Extracted {len(search_results)} search results")
                return search_results
                
            except Exception as e:
                self.logger.error(f"selenium.search_error: {str(e)}", exc_info=True)
                return []
    
    def _selenium_parse_results(self, page_source: str, city: str, current_url: str) -> List[Dict[str, Any]]:
        """
        Parse search results from Selenium-rendered page content using LLM
        
        Args:
            page_source: Full HTML content from Selenium
            city: City name for context
            current_url: Current page URL for relative link resolution
            
        Returns:
            List of parsed search result dictionaries
        """
        with span(self.logger, "selenium.parse_results"):
            try:
                # Clean the HTML content for LLM processing
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Get clean text content
                clean_text = soup.get_text()
                
                # Truncate if too long (LLM token limits)
                if len(clean_text) > 50000:
                    clean_text = clean_text[:50000] + "...[truncated]"
                
                self.logger.info(f"selenium.parse_content: Processing {len(clean_text)} characters with LLM")
                
                # Debug: Check for result indicators
                result_indicators = [
                    'zoning map', 'pdf', 'documentcenter', 'document center',
                    '2024', '2023', '2022', 'planning', 'gis'
                ]
                
                found_indicators = [ind for ind in result_indicators if ind in clean_text.lower()]
                self.logger.info(f"selenium.content_indicators: Found indicators: {found_indicators}")
                
                # Use LLM to parse the results
                return self._llm_parse_search_results(clean_text, current_url, city)
                
            except Exception as e:
                self.logger.error(f"selenium.parse_error: {str(e)}")
                return []
    
    def _fallback_maps_library_search(self, driver: webdriver.Chrome, website_url: str, city: str) -> Optional[str]:
        """
        Fallback method: Search for "Maps" to find Map Library, then extract Zoning Map from library page
        
        Args:
            driver: Selenium WebDriver instance (already initialized)
            website_url: Municipal website URL
            city: City name for logging context
            
        Returns:
            URL to the zoning map PDF, or None if not found
        """
        with span(self.logger, "fallback.maps_library"):
            try:
                self.logger.info(f"🗺️ FALLBACK STEP 1: Searching for 'Maps' on {city} website")
                
                # Step 1: Search for "Maps" instead of "Zoning Map"
                search_query = "Maps"
                search_performed = False
                
                # Navigate to the website if not already there
                if driver.current_url != website_url:
                    driver.get(website_url)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                # Find and use search functionality for "Maps"
                search_inputs = driver.find_elements(By.CSS_SELECTOR, 
                    'input[type="search"], input[type="text"][placeholder*="search" i], input[type="text"][name*="search" i], input[id*="search" i], input[class*="search" i]')
                
                for search_input in search_inputs:
                    if search_input.is_displayed() and search_input.is_enabled():
                        try:
                            self.logger.info(f"fallback.search_maps: Submitting 'Maps' search query")
                            search_input.clear()
                            search_input.send_keys(search_query)
                            search_input.send_keys(Keys.RETURN)
                            search_performed = True
                            break
                        except Exception as e:
                            self.logger.warning(f"fallback.search_failed: {str(e)}")
                            continue
                
                if not search_performed:
                    # Try direct navigation to common search URLs with "Maps"
                    search_urls = [
                        f"{website_url.rstrip('/')}/Search?searchPhrase=Maps",
                        f"{website_url.rstrip('/')}/search?q=Maps",
                        f"{website_url.rstrip('/')}/search/default.aspx?q=Maps"
                    ]
                    
                    for search_url in search_urls:
                        try:
                            self.logger.info(f"fallback.direct_maps_search: {search_url}")
                            driver.get(search_url)
                            time.sleep(2)
                            
                            page_source = driver.page_source.lower()
                            if any(indicator in page_source for indicator in ['search results', 'maps', 'library']):
                                search_performed = True
                                break
                        except Exception as e:
                            continue
                
                if not search_performed:
                    self.logger.warning(f"fallback.no_search: Could not perform Maps search on {website_url}")
                    return None
                
                # Step 2: Wait for results and extract page content
                self.logger.info(f"🗺️ FALLBACK STEP 2: Waiting for Maps search results...")
                time.sleep(3)  # Allow time for results to load
                
                page_source = driver.page_source
                self.logger.info(f"fallback.maps_results: Extracted {len(page_source)} characters from Maps search results")
                
                # Step 3: Use LLM to identify best Maps page from search results
                maps_page_url = self._identify_map_library_from_results(page_source, city, driver.current_url)
                
                if not maps_page_url:
                    self.logger.warning(f"fallback.no_maps_page: No relevant Maps page found in search results")
                    return None
                
                # Step 4: Navigate to Maps page and extract Zoning Map
                self.logger.info(f"🗺️ FALLBACK STEP 3: Navigating to Maps page: {maps_page_url}")
                zoning_map_url = self._extract_zoning_map_from_maps_page(driver, maps_page_url, city)
                
                if zoning_map_url:
                    self.logger.info(f"🎯 FALLBACK FINAL: Found Zoning Map in library -> {zoning_map_url}")
                    return zoning_map_url
                else:
                    self.logger.warning(f"fallback.no_zoning_map: No Zoning Map found in Maps page")
                    return None
                
            except Exception as e:
                self.logger.error(f"fallback.error: {str(e)}", exc_info=True)
                return None
    
    def _identify_map_library_from_results(self, page_source: str, city: str, current_url: str) -> Optional[str]:
        """
        Use keyword matching to identify the best Maps page from search results.
        Looks for exact matches in priority order: "Map Library", "Maps Library", "Map Collection", "Maps"
        """
        with span(self.logger, "fallback.identify_library"):
            try:
                # Parse HTML to extract links and their text
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Define keywords in priority order (first match wins)
                target_keywords = [
                    "Map Library",
                    "Maps Library", 
                    "Map Collection",
                    "Maps"
                ]
                
                self.logger.info(f"🔍 KEYWORD MATCHING: Searching for maps page using exact keyword matching")
                self.logger.info(f"🎯 TARGET KEYWORDS: {target_keywords}")
                
                # Extract all links with their text
                all_links = []
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    text = link.get_text(strip=True)
                    if href and text:
                        all_links.append({
                            'text': text,
                            'href': href
                        })
                
                # Also look for text elements that might be clickable (not just <a> tags)
                # Search in div, p, span, h1-h6 elements too
                for element in soup.find_all(['div', 'p', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    text = element.get_text(strip=True)
                    if text:
                        # Check if this element has a clickable parent or contains a link
                        parent_link = element.find_parent('a')
                        child_link = element.find('a')
                        
                        if parent_link and parent_link.get('href'):
                            all_links.append({
                                'text': text,
                                'href': parent_link.get('href')
                            })
                        elif child_link and child_link.get('href'):
                            all_links.append({
                                'text': text,
                                'href': child_link.get('href')
                            })
                        else:
                            # No direct link, but we'll still check for keyword matches
                            all_links.append({
                                'text': text,
                                'href': None  # Will try to infer URL later
                            })
                
                self.logger.info(f"📄 EXTRACTED LINKS: Found {len(all_links)} text/link pairs")
                
                # Debug: show all extracted text
                for i, link_data in enumerate(all_links[:10]):  # Show first 10
                    self.logger.info(f"  {i+1}. Text: '{link_data['text']}' -> URL: {link_data['href']}")
                
                # Search for keyword matches in priority order
                for keyword in target_keywords:
                    self.logger.info(f"🔍 SEARCHING FOR: '{keyword}'")
                    
                    for link_data in all_links:
                        text = link_data['text']
                        href = link_data['href']
                        
                        # Exact match (case-insensitive)
                        if text.lower().strip() == keyword.lower():
                            self.logger.info(f"🎯 EXACT MATCH FOUND: '{text}' matches '{keyword}'")
                            
                            if href:
                                # Convert relative URLs to absolute
                                if href.startswith('/'):
                                    full_url = urljoin(current_url, href)
                                elif href.startswith('http'):
                                    full_url = href
                                else:
                                    full_url = urljoin(current_url, '/' + href)
                                
                                self.logger.info(f"🗺️ KEYWORD MATCH SUCCESS: '{text}' -> {full_url}")
                                return full_url
                            else:
                                # No direct URL found, try to infer from common patterns
                                inferred_url = self._infer_maps_url(current_url, keyword)
                                if inferred_url:
                                    self.logger.info(f"🗺️ INFERRED URL: '{text}' -> {inferred_url}")
                                    return inferred_url
                                else:
                                    self.logger.warning(f"⚠️ FOUND KEYWORD '{keyword}' but no URL available")
                
                self.logger.warning(f"❌ NO KEYWORD MATCHES: None of {target_keywords} found in search results")
                return None
                
            except Exception as e:
                self.logger.error(f"fallback.keyword_matching_error: {str(e)}", exc_info=True)
                return None
    
    def _infer_maps_url(self, base_url: str, keyword: str) -> Optional[str]:
        """
        Try to infer the Maps page URL based on common municipal website patterns
        """
        try:
            base_domain = base_url.rstrip('/')
            
            # Common patterns for maps pages
            common_patterns = [
                '/maps',
                '/government/maps', 
                '/engineering/maps',
                '/gis/maps',
                '/departments/maps',
                '/planning/maps',
                '/public-works/maps'
            ]
            
            for pattern in common_patterns:
                inferred_url = base_domain + pattern
                self.logger.info(f"🔍 TRYING INFERRED URL: {inferred_url}")
                return inferred_url  # Return the first pattern for now
            
            return None
        except Exception as e:
            self.logger.error(f"infer_url_error: {str(e)}")
            return None
    
    def _extract_zoning_map_from_maps_page(self, driver: webdriver.Chrome, maps_page_url: str, city: str) -> Optional[str]:
        """
        Navigate to Maps page (library, department, or general maps page) and extract the Zoning Map URL
        """
        with span(self.logger, "fallback.extract_from_library"):
            try:
                self.logger.info(f"🗺️ FALLBACK STEP 4: Loading Maps page: {maps_page_url}")
                
                # Navigate to the Maps page
                driver.get(maps_page_url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                # Give page time to fully load
                time.sleep(2)
                
                page_source = driver.page_source
                self.logger.info(f"fallback.maps_page_loaded: Extracted {len(page_source)} characters from maps page")
                
                # Use LLM to extract Zoning Map link from the maps page
                zoning_map_url = self._parse_zoning_map_from_maps_page(page_source, city, maps_page_url)
                
                return zoning_map_url
                
            except Exception as e:
                self.logger.error(f"fallback.extract_error: {str(e)}", exc_info=True)
                return None
    
    def _parse_zoning_map_from_maps_page(self, page_source: str, city: str, maps_page_url: str) -> Optional[str]:
        """
        Use enhanced extraction to find the Zoning Map link from the Maps page (library, department, or general maps page)
        """
        with span(self.logger, "fallback.parse_library"):
            try:
                # Parse HTML for detailed link analysis
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # First, try direct PDF link detection
                direct_pdf_url = self._extract_direct_pdf_links(soup, maps_page_url)
                if direct_pdf_url:
                    self.logger.info(f"🎯 DIRECT PDF EXTRACTION: Found -> {direct_pdf_url}")
                    return direct_pdf_url
                
                # Enhanced link extraction - get ALL links with context
                all_links = []
                pdf_links = []
                zoning_links = []
                
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    text = link.get_text(strip=True)
                    
                    if href and text:
                        # Convert relative URLs to absolute
                        if href.startswith('/'):
                            full_href = urljoin(maps_page_url, href)
                        elif href.startswith('http'):
                            full_href = href
                        else:
                            full_href = urljoin(maps_page_url, '/' + href)
                        
                        link_entry = f"Text: '{text}' -> URL: {full_href}"
                        all_links.append(link_entry)
                        
                        # Categorize links
                        if full_href.lower().endswith('.pdf'):
                            pdf_links.append(link_entry)
                        
                        if any(term in text.lower() for term in ['zoning map', 'zoning', 'map']):
                            zoning_links.append(link_entry)
                
                # Also extract table data specifically
                table_data = self._extract_table_links(soup, maps_page_url)
                
                # Log debug information
                self.logger.info(f"🔍 ENHANCED LINK ANALYSIS:")
                self.logger.info(f"📄 Total links found: {len(all_links)}")
                self.logger.info(f"📋 PDF links found: {len(pdf_links)}")
                self.logger.info(f"🗺️ Zoning-related links: {len(zoning_links)}")
                self.logger.info(f"📊 Table links found: {len(table_data)}")
                
                if pdf_links:
                    self.logger.info(f"📄 PDF LINKS DETECTED:")
                    for pdf_link in pdf_links:
                        self.logger.info(f"  • {pdf_link}")
                
                if zoning_links:
                    self.logger.info(f"🗺️ ZONING LINKS DETECTED:")
                    for zoning_link in zoning_links:
                        self.logger.info(f"  • {zoning_link}")
                
                if table_data:
                    self.logger.info(f"📊 TABLE LINKS DETECTED:")
                    for table_link in table_data:
                        self.logger.info(f"  • {table_link}")
                
                # Prepare comprehensive content for LLM
                clean_text = soup.get_text()
                if len(clean_text) > 2000:
                    clean_text = clean_text[:2000] + "..."
                
                # Combine all link types for LLM analysis
                all_link_text = '\n'.join(all_links[:30])  # First 30 links
                pdf_text = '\n'.join(pdf_links) if pdf_links else "No PDF links found"
                zoning_text = '\n'.join(zoning_links) if zoning_links else "No zoning-related links found"
                table_text = '\n'.join(table_data) if table_data else "No table links found"
                
                prompt = f"""
Extract the Zoning Map URL from this Maps page for {city}.

PAGE TEXT:
{clean_text}

PDF LINKS FOUND:
{pdf_text}

ZONING-RELATED LINKS:
{zoning_text}

TABLE LINKS:
{table_text}

ALL LINKS (first 30):
{all_link_text}

TASK: Find the link to the Zoning Map PDF. This could be on any type of maps page (library, department, or general). Look for:
- Links with text "Zoning Map" 
- URLs containing "ZoningMap", "zoning", or ending in .pdf
- Table entries for "Zoning Map"
- Any PDF that appears to be a zoning-related map

Return this JSON with the EXACT URL found:
{{
  "title": "Zoning Map",
  "url": "EXACT_URL_HERE"
}}

Only return the JSON object. If no zoning map found, return {{}}
"""
                
                self.logger.info(f"🤖 ENHANCED MAPS PAGE PARSE PROMPT:")
                self.logger.info(f"--- START ENHANCED PROMPT ---")
                self.logger.info(prompt)
                self.logger.info(f"--- END ENHANCED PROMPT ---")
                
                response = self._call_llm_classification(prompt)
                self.logger.info(f"🤖 ENHANCED PARSE LLM RESPONSE: '{response}'")
                
                if response and response.strip():
                    import json
                    try:
                        # Clean up LLM response
                        clean_response = response.strip()
                        if clean_response.startswith('```json'):
                            clean_response = clean_response.replace('```json', '').replace('```', '').strip()
                        elif clean_response.startswith('```'):
                            clean_response = clean_response.replace('```', '').strip()
                        
                        parsed_result = json.loads(clean_response)
                        
                        if parsed_result and 'url' in parsed_result and parsed_result['url']:
                            url = parsed_result.get('url', '')
                            title = parsed_result.get('title', '')
                            
                            # Ensure URL is absolute
                            if url.startswith('/'):
                                full_url = urljoin(maps_page_url, url)
                            elif url.startswith('http'):
                                full_url = url
                            else:
                                full_url = urljoin(maps_page_url, '/' + url)
                            
                            self.logger.info(f"🎯 ENHANCED EXTRACTION SUCCESS: '{title}' -> {full_url}")
                            return full_url
                        
                    except json.JSONDecodeError as e:
                        self.logger.error(f"fallback.enhanced_json_error: {str(e)}")
                        return None
                
                self.logger.warning(f"fallback.enhanced_extraction_failed: No zoning map URL extracted")
                return None
                
            except Exception as e:
                self.logger.error(f"fallback.enhanced_parse_error: {str(e)}", exc_info=True)
                return None
    
    def _extract_direct_pdf_links(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """
        Directly extract PDF links that might be zoning maps
        """
        try:
            # Look for links that end with .pdf and contain zoning-related terms
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                text = link.get_text(strip=True).lower()
                
                if href:
                    # Convert to absolute URL
                    if href.startswith('/'):
                        full_url = urljoin(base_url, href)
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = urljoin(base_url, '/' + href)
                    
                    # Check if this looks like a zoning map PDF
                    if (full_url.lower().endswith('.pdf') and 
                        ('zoning' in text or 'zoning' in full_url.lower())):
                        self.logger.info(f"🎯 DIRECT PDF MATCH: Text='{text}' URL={full_url}")
                        return full_url
            
            return None
        except Exception as e:
            self.logger.error(f"direct_pdf_error: {str(e)}")
            return None
    
    def _extract_table_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Extract links specifically from tables (where zoning maps are often listed)
        """
        try:
            table_links = []
            
            # Find all tables
            for table in soup.find_all('table'):
                # Look for rows in this table
                for row in table.find_all('tr'):
                    row_text = row.get_text(strip=True).lower()
                    
                    # If this row mentions zoning
                    if 'zoning' in row_text:
                        # Find all links in this row
                        for link in row.find_all('a', href=True):
                            href = link.get('href')
                            text = link.get_text(strip=True)
                            
                            if href:
                                # Convert to absolute URL
                                if href.startswith('/'):
                                    full_url = urljoin(base_url, href)
                                elif href.startswith('http'):
                                    full_url = href
                                else:
                                    full_url = urljoin(base_url, '/' + href)
                                
                                table_links.append(f"Table Row: '{text}' -> {full_url}")
            
            return table_links
        except Exception as e:
            self.logger.error(f"table_extraction_error: {str(e)}")
            return []
    
    def _find_planning_pages(self, website_url: str, city: str) -> List[Tuple[str, str]]:
        """
        Find pages on the municipal website related to planning, zoning, or maps
        
        Args:
            website_url: The base website URL
            city: City name for context
            
        Returns:
            List of (page_url, page_title) tuples for relevant pages
        """
        with span(self.logger, "agent.find_planning_pages"):
            self.logger.debug(f"agent.scanning_website: {website_url}")
            
            try:
                # Enhanced headers to avoid bot detection
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0'
                }
                
                # Add small delay to avoid rate limiting
                time.sleep(0.5)
                
                response = requests.get(website_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Enhanced keywords targeting map libraries and GIS pages specifically
                planning_keywords = [
                    # High-priority map-specific terms
                    'map library', 'gis mapping', 'zoning map', 'zoning maps', 'maps',
                    'map collection', 'gis maps', 'interactive maps', 'web gis',
                    
                    # Department/section keywords
                    'planning', 'zoning', 'gis', 'engineering', 'planning board', 
                    'planning department', 'engineering department', 'gis department',
                    
                    # Document/resource keywords  
                    'documents', 'resources', 'downloads', 'files', 'library',
                    'land use', 'development', 'zoning district', 'zoning ordinance',
                    
                    # Common municipal page patterns
                    'government', 'departments', 'services', 'permits'
                ]
                
                relevant_pages = []
                processed_urls = set()
                
                # Find all links on the page
                links = soup.find_all('a', href=True)
                self.logger.debug(f"agent.total_links: Found {len(links)} total links to analyze")
                
                for link in links:
                    href = link.get('href', '').strip()
                    text = link.get_text(strip=True).lower()
                    title = link.get('title', '').lower()
                    
                    # Skip empty links
                    if not href or href == '#':
                        continue
                    
                    # Convert relative URLs to absolute
                    if href.startswith('/'):
                        full_url = urljoin(website_url, href)
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = urljoin(website_url, href)
                    
                    # Skip if we've already processed this URL
                    if full_url in processed_urls:
                        continue
                    processed_urls.add(full_url)
                    
                    # Skip external domains (stay on municipal site)
                    if not self._is_same_domain(website_url, full_url):
                        continue
                    
                    # Debug: Log all internal links for analysis
                    self.logger.debug(f"agent.link_analysis: '{text}' -> {full_url}")
                    
                    # Check if link text or title contains planning keywords
                    combined_text = f"{text} {title}".lower()
                    relevance_score = 0
                    matched_keywords = []
                    
                    for keyword in planning_keywords:
                        if keyword in combined_text:
                            # Enhanced scoring for map-specific pages
                            if keyword in ['map library', 'gis mapping', 'zoning map', 'zoning maps']:
                                relevance_score += 15  # Highest priority - these are exactly what we need
                                matched_keywords.append(f"{keyword}(+15)")
                            elif keyword in ['map collection', 'gis maps', 'interactive maps', 'web gis']:
                                relevance_score += 12  # Very high priority
                                matched_keywords.append(f"{keyword}(+12)")
                            elif keyword in ['maps', 'gis', 'engineering']:
                                relevance_score += 8   # High priority
                                matched_keywords.append(f"{keyword}(+8)")
                            elif keyword in ['planning', 'zoning', 'documents', 'library']:
                                relevance_score += 5   # Medium priority
                                matched_keywords.append(f"{keyword}(+5)")
                            else:
                                relevance_score += 2   # Lower priority
                                matched_keywords.append(f"{keyword}(+2)")
                    
                    # Also check URL path for keywords
                    url_path = full_url.lower()
                    for keyword in planning_keywords:
                        if keyword.replace(' ', '') in url_path:
                            relevance_score += 3
                            matched_keywords.append(f"URL:{keyword}(+3)")
                    
                    # Special check for common municipal patterns in URLs
                    url_patterns = ['engineering', 'planning', 'government', 'departments', 'gis', 'maps']
                    for pattern in url_patterns:
                        if f'/{pattern}/' in url_path:
                            relevance_score += 4
                            matched_keywords.append(f"URLpath:{pattern}(+4)")
                    
                    if relevance_score > 0:
                        page_title = text or link.get('title', '') or 'Untitled'
                        relevant_pages.append((full_url, page_title, relevance_score))
                        self.logger.debug(f"agent.relevant_page: Score {relevance_score} - '{page_title}' - {full_url}")
                        self.logger.debug(f"agent.matched_keywords: {', '.join(matched_keywords)}")
                    
                    # Also log high-potential links that might have missed our keywords
                    elif any(term in combined_text for term in ['department', 'government', 'service']) and any(term in combined_text for term in ['map', 'gis', 'plan', 'zone', 'engineer']):
                        self.logger.debug(f"agent.potential_miss: '{text}' -> {full_url} (might contain relevant content)")
                
                # Sort by relevance score (highest first)
                relevant_pages.sort(key=lambda x: x[2], reverse=True)
                
                # Return top pages without score
                result_pages = [(url, title) for url, title, score in relevant_pages[:10]]
                
                self.logger.info(f"agent.found_pages: {len(result_pages)} relevant pages found")
                for i, (url, title) in enumerate(result_pages[:5]):
                    self.logger.debug(f"  {i+1}. {title} - {url}")
                
                return result_pages
                
            except Exception as e:
                self.logger.error(f"agent.page_scan_failed: {str(e)}")
                return []
    
    def _extract_pdfs_from_page(self, page_url: str, city: str) -> List[Dict[str, Any]]:
        """
        Extract PDF links from a specific page
        
        Args:
            page_url: URL of the page to scan
            city: City name for context
            
        Returns:
            List of PDF metadata dictionaries
        """
        with span(self.logger, "agent.extract_pdfs"):
            self.logger.info(f"agent.scanning_page: {page_url}")  # Changed to INFO for better visibility
            
            try:
                # Enhanced headers with better content handling
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'no-cache'
                }
                
                # Add delay between page requests
                time.sleep(0.8)
                
                response = requests.get(page_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                
                # Debug response details
                self.logger.info(f"agent.response_debug: Status {response.status_code}")
                self.logger.info(f"agent.response_headers: {dict(response.headers)}")
                self.logger.info(f"agent.content_type: {response.headers.get('content-type', 'unknown')}")
                self.logger.info(f"agent.content_encoding: {response.headers.get('content-encoding', 'none')}")
                self.logger.info(f"agent.content_length: {len(response.content)} bytes")
                
                # Try to ensure we get text content
                if 'text/html' not in response.headers.get('content-type', ''):
                    self.logger.warning(f"agent.unexpected_content_type: Expected HTML but got {response.headers.get('content-type')}")
                
                # Force UTF-8 encoding
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                pdf_candidates = []
                
                # Enhanced PDF detection for both direct links and table/structured content
                
                # Debug: Log page content analysis  
                page_text = soup.get_text()
                self.logger.info(f"agent.page_analysis: Page has {len(page_text)} characters of text")
                
                # Check if we got valid HTML content
                if len(page_text.strip()) < 100 or 'html' not in response.text.lower():
                    self.logger.warning(f"agent.suspicious_content: Page content seems invalid or not HTML")
                    self.logger.info(f"agent.raw_content_sample: {response.text[:500]}...")
                else:
                    self.logger.info(f"agent.page_content_sample: {page_text[:500]}...")
                
                # Method 1: Direct PDF links
                links = soup.find_all('a', href=True)
                self.logger.info(f"agent.total_links_on_page: Found {len(links)} total links on page")
                
                pdf_links_found = 0
                all_links_debug = []
                
                for link in links:
                    href = link.get('href', '').strip()
                    link_text = link.get_text(strip=True)
                    
                    # Log all links for debugging
                    all_links_debug.append(f"'{link_text}' -> {href}")
                    
                    # Check if it's a PDF (be more flexible with detection)
                    is_pdf = (href.lower().endswith('.pdf') or 
                             'pdf' in href.lower() or
                             'PDF' in href)
                    
                    if is_pdf:
                        pdf_links_found += 1
                        self.logger.info(f"agent.potential_pdf: '{link_text}' -> {href}")
                    
                    # Skip if not a PDF
                    if not href.lower().endswith('.pdf'):
                        continue
                    
                    # Convert to absolute URL with enhanced handling
                    if href.startswith('/'):
                        pdf_url = urljoin(page_url, href)
                    elif href.startswith('http'):
                        pdf_url = href
                    else:
                        pdf_url = urljoin(page_url, href)
                    
                    # Special handling for Woburn-style URLs that might be http:// instead of https://
                    if 'woburnma.gov' in pdf_url and pdf_url.startswith('https://'):
                        # Also try the http version as Woburn PDFs might be hosted on http://
                        http_version = pdf_url.replace('https://', 'http://')
                        self.logger.info(f"agent.woburn_url_check: Also considering {http_version}")
                    
                    self.logger.info(f"agent.pdf_url_conversion: '{href}' -> '{pdf_url}'")
                    
                    # Get enhanced context for structured pages like Woburn's table
                    link_text = link.get_text(strip=True)
                    link_title = link.get('title', '')
                    
                    # Enhanced context detection - look at table cells, list items, etc.
                    context_text = self._extract_enhanced_context(link, soup)
                    
                    pdf_info = {
                        'url': pdf_url,
                        'link_text': link_text,
                        'title': link_title,
                        'context': context_text,
                        'source_page': page_url,
                        'found_on': self._get_page_title(soup)
                    }
                    
                    pdf_candidates.append(pdf_info)
                    self.logger.info(f"agent.pdf_found: {link_text} -> {pdf_url}")
                
                # Debug summary
                self.logger.info(f"agent.pdfs_found: {len(pdf_candidates)} PDFs found on page")
                self.logger.info(f"agent.potential_pdfs: {pdf_links_found} potential PDF links detected")
                
                # Log first 10 links for debugging
                if all_links_debug:
                    self.logger.info(f"agent.first_10_links:")
                    for i, link_debug in enumerate(all_links_debug[:10]):
                        self.logger.info(f"  {i+1}. {link_debug}")
                    if len(all_links_debug) > 10:
                        self.logger.info(f"  ... and {len(all_links_debug) - 10} more links")
                
                # LLM-POWERED FALLBACK: If no PDFs found, use LLM to analyze page and find navigation paths
                if len(pdf_candidates) == 0:
                    self.logger.info(f"agent.llm_navigation: No PDFs found via parsing, using LLM to analyze page content and find zoning maps")
                    llm_candidates = self._llm_analyze_page_for_zoning_content(page_url, page_text, city)
                    pdf_candidates.extend(llm_candidates)
                
                return pdf_candidates
                
            except Exception as e:
                self.logger.error(f"agent.pdf_extraction_failed: {str(e)}")
                return []
    
    def _select_best_zoning_map(self, pdf_candidates: List[Dict[str, Any]], city: str) -> Optional[str]:
        """
        Select the best zoning map PDF from candidates
        
        Args:
            pdf_candidates: List of PDF metadata dictionaries
            city: City name for validation
            
        Returns:
            URL of the best zoning map PDF, or None
        """
        with span(self.logger, "agent.select_zoning_map"):
            self.logger.debug(f"agent.evaluating: {len(pdf_candidates)} PDF candidates")
            
            if not pdf_candidates:
                return None
            
            scored_pdfs = []
            
            for pdf in pdf_candidates:
                score = self._score_zoning_map_candidate(pdf, city)
                if score > 0:  # Only keep candidates with positive scores
                    scored_pdfs.append((pdf, score))
            
            if not scored_pdfs:
                self.logger.warning("agent.no_valid_candidates: No PDFs scored as valid zoning maps")
                return None
            
            # Sort by score (highest first)
            scored_pdfs.sort(key=lambda x: x[1], reverse=True)
            
            # Log top candidates
            self.logger.info(f"agent.top_candidates: Top {min(3, len(scored_pdfs))} zoning map candidates:")
            for i, (pdf, score) in enumerate(scored_pdfs[:3]):
                self.logger.info(f"  {i+1}. Score {score}: {pdf['link_text']} - {pdf['url']}")
            
            # Return the highest scoring PDF and download it for verification
            best_pdf = scored_pdfs[0][0]
            self.logger.info(f"agent.selected: {best_pdf['link_text']} - {best_pdf['url']}")
            
            # Download the PDF for verification
            downloaded_path = self._download_and_verify_pdf(best_pdf['url'], city)
            if downloaded_path:
                self.logger.info(f"🎯 BEST ZONING MAP IDENTIFIED AND DOWNLOADED:")
                self.logger.info(f"   📄 Map Title: {best_pdf['link_text']}")
                self.logger.info(f"   🔗 Original URL: {best_pdf['url']}")
                self.logger.info(f"   📁 Downloaded To: {downloaded_path}")
                self.logger.info(f"   ⭐ Final Score: {scored_pdfs[0][1]} points")
            
            return best_pdf['url']
    
    def _score_zoning_map_candidate(self, pdf_info: Dict[str, Any], city: str) -> int:
        """Score a PDF candidate based on how likely it is to be a current zoning map"""
        
        text_to_analyze = f"{pdf_info['link_text']} {pdf_info['title']} {pdf_info['context']}".lower()
        url_to_analyze = pdf_info['url'].lower()
        
        score = 0
        self.logger.debug(f"agent.scoring_pdf: {pdf_info['url']}")
        self.logger.debug(f"agent.scoring_text: '{text_to_analyze}'")
        
        # **CRITICAL FIXES FOR WOBURN-STYLE MAPS**
        
        # Super high value - direct zoning map indicators in URL
        if 'zoningmap' in url_to_analyze.replace('-', '').replace('_', ''):
            score += 50  # Woburn case: "ZoningMap2024.pdf"
            self.logger.debug(f"agent.scoring: +50 for zoningmap in URL")
        
        # Very high value indicators in text
        if 'zoning map' in text_to_analyze:
            score += 30
            self.logger.debug(f"agent.scoring: +30 for 'zoning map' in text")
        
        # High value URL patterns
        if any(pattern in url_to_analyze for pattern in ['zoning', 'zone']):
            score += 20
            self.logger.debug(f"agent.scoring: +20 for zoning/zone in URL")
        
        if 'map' in url_to_analyze:
            score += 15
            self.logger.debug(f"agent.scoring: +15 for map in URL")
            
        # City name matching
        if city.lower() in text_to_analyze or city.lower() in url_to_analyze:
            score += 12
            self.logger.debug(f"agent.scoring: +12 for city name match")
        
        # Medium value text indicators  
        if 'zoning district' in text_to_analyze:
            score += 10
        if any(word in text_to_analyze for word in ['zoning', 'zone']):
            score += 8
        if 'map' in text_to_analyze:
            score += 5
        
        # **ENHANCED RECENCY SCORING**
        current_year = 2025
        for year in range(current_year, current_year - 10, -1):  # Last 10 years
            if str(year) in text_to_analyze or str(year) in url_to_analyze:
                year_score = max(1, (year - 2015))  # 2024=9, 2023=8, etc.
                score += year_score
                self.logger.debug(f"agent.scoring: +{year_score} for year {year}")
                break
        
        # **STRICTER EXCLUSIONS**
        exclude_terms = [
            'help', 'tutorial', 'guide', 'instruction', 'axisgis',  # Exclude Franklin's help file
            'ordinance', 'bylaw', 'regulation', 'code', 'amendment',
            'application', 'permit', 'form', 'overlay', 'flood', 
            'historical', 'archive', 'old', 'former', 'proposed',
            'minutes', 'agenda', 'meeting', 'report'
        ]
        
        for term in exclude_terms:
            if term in text_to_analyze or term in url_to_analyze:
                penalty = -25 if term in ['help', 'tutorial', 'axisgis'] else -10
                score += penalty
                self.logger.debug(f"agent.scoring: {penalty} for exclusion term '{term}'")
        
        # **BONUS FOR OFFICIAL SOURCES**
        if '.gov' in pdf_info['url']:
            score += 8
            self.logger.debug(f"agent.scoring: +8 for .gov domain")
            
        if any(term in pdf_info['source_page'].lower() for term in ['map-library', 'gis-mapping', 'engineering']):
            score += 10
            self.logger.debug(f"agent.scoring: +10 for official map page")
        
        final_score = max(0, score)
        self.logger.debug(f"agent.scoring_final: {final_score} for {pdf_info['url']}")
        
        return final_score
    
    def _is_same_domain(self, base_url: str, check_url: str) -> bool:
        """Check if two URLs are from the same domain"""
        try:
            base_domain = urlparse(base_url).netloc.lower()
            check_domain = urlparse(check_url).netloc.lower()
            
            # Remove www. for comparison
            base_domain = base_domain.replace('www.', '')
            check_domain = check_domain.replace('www.', '')
            
            return base_domain == check_domain
        except:
            return False
    
    def _get_page_title(self, soup: BeautifulSoup) -> str:
        """Extract page title from BeautifulSoup object"""
        try:
            title_tag = soup.find('title')
            if title_tag:
                return title_tag.get_text(strip=True)
            return "Untitled Page"
        except:
            return "Untitled Page"
    
    def _extract_enhanced_context(self, link, soup: BeautifulSoup) -> str:
        """Extract enhanced context for PDF links, especially from tables and structured content"""
        
        context_parts = []
        
        # Method 1: Check if link is in a table (like Woburn's map library)
        table_cell = link.find_parent(['td', 'th'])
        if table_cell:
            # Get the row context
            table_row = table_cell.find_parent('tr')
            if table_row:
                row_text = table_row.get_text(strip=True)
                context_parts.append(f"Table: {row_text}")
                
            # Also get table headers for additional context
            table = table_cell.find_parent('table')
            if table:
                headers = table.find_all(['th'])
                if headers:
                    header_text = ' | '.join([h.get_text(strip=True) for h in headers])
                    context_parts.append(f"Headers: {header_text}")
        
        # Method 2: Check if in a list item
        list_item = link.find_parent(['li', 'ul', 'ol'])
        if list_item:
            list_text = list_item.get_text(strip=True)
            context_parts.append(f"List: {list_text}")
        
        # Method 3: Get immediate parent context (fallback)
        parent = link.parent
        if parent and not context_parts:
            parent_text = parent.get_text(strip=True)[:200]
            if parent_text:
                context_parts.append(f"Parent: {parent_text}")
        
        # Method 4: Look for nearby headings
        for heading_tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            heading = link.find_previous(heading_tag)
            if heading:
                heading_text = heading.get_text(strip=True)
                context_parts.append(f"Section: {heading_text}")
                break
        
        # Combine all context
        full_context = ' | '.join(context_parts)
        return full_context[:300]  # Limit length
    
    def _llm_analyze_page_for_zoning_content(self, page_url: str, page_content: str, city: str) -> List[Dict[str, Any]]:
        """
        Use LLM to intelligently analyze page content and navigate to find zoning maps
        
        This method uses the LLM's reasoning capabilities to:
        1. Understand the page structure and content
        2. Identify promising navigation paths for zoning information
        3. Recursively explore relevant pages 
        4. Recognize and validate zoning map PDFs
        
        Args:
            page_url: Current page URL being analyzed
            page_content: Text content of the page
            city: City name for context
            
        Returns:
            List of PDF candidates found through LLM navigation
        """
        with span(self.logger, "agent.llm_navigation"):
            self.logger.info(f"🤖 LLM Navigation: Analyzing {page_url} for {city}")
            
            try:
                # Step 1: LLM analyzes current page and identifies navigation strategy
                navigation_strategy = self._llm_analyze_page_structure(page_url, page_content, city)
                
                if not navigation_strategy:
                    self.logger.warning(f"llm.no_strategy: LLM could not identify navigation strategy for {page_url}")
                    return []
                
                # Step 2: Follow LLM's recommended navigation paths
                pdf_candidates = []
                
                for nav_action in navigation_strategy.get('actions', []):
                    action_type = nav_action.get('type')
                    
                    if action_type == 'follow_link':
                        # LLM identified a promising link to follow
                        link_url = nav_action.get('url')
                        reason = nav_action.get('reason', 'LLM recommendation')
                        
                        self.logger.info(f"llm.following_link: {link_url} - {reason}")
                        
                        # Navigate to the recommended page
                        new_pdfs = self._llm_explore_page(link_url, city, reason)
                        pdf_candidates.extend(new_pdfs)
                        
                        # Limit depth to prevent infinite recursion
                        if len(pdf_candidates) > 0:
                            break
                    
                    elif action_type == 'search_pattern':
                        # LLM identified URL patterns to test
                        pattern = nav_action.get('pattern')
                        reason = nav_action.get('reason', 'LLM pattern recognition')
                        
                        self.logger.info(f"llm.testing_pattern: {pattern} - {reason}")
                        
                        pattern_pdfs = self._llm_test_url_pattern(pattern, city, reason)
                        pdf_candidates.extend(pattern_pdfs)
                
                # Step 3: LLM validates found PDFs are actually zoning maps
                if pdf_candidates:
                    validated_pdfs = self._llm_validate_zoning_pdfs(pdf_candidates, city)
                    return validated_pdfs
                
                return []
                
            except Exception as e:
                self.logger.error(f"llm.navigation_failed: {str(e)}")
                return []
    
    def _llm_analyze_page_structure(self, page_url: str, page_content: str, city: str) -> Optional[Dict[str, Any]]:
        """
        Use LLM to analyze page structure and determine navigation strategy
        """
        with span(self.logger, "llm.analyze_structure"):
            
            # Truncate content for LLM analysis
            content_sample = page_content[:3000] if len(page_content) > 3000 else page_content
            
            prompt = f"""
You are an expert at navigating municipal government websites to find zoning maps. 

TASK: Analyze this webpage from {city} and determine how to find their official zoning map.

PAGE URL: {page_url}
CITY: {city}

PAGE CONTENT:
{content_sample}

Based on this content, provide a JSON response with your navigation strategy:

{{
  "assessment": "Your analysis of what this page contains and its relationship to zoning information",
  "confidence": "high|medium|low - how confident you are about finding zoning maps from here",
  "actions": [
    {{
      "type": "follow_link",
      "url": "full URL to follow",
      "reason": "why this link is promising for finding zoning maps"
    }},
    {{
      "type": "search_pattern", 
      "pattern": "URL pattern to test (e.g., /documents/zoning-map.pdf)",
      "reason": "why this pattern might work based on page structure"
    }}
  ]
}}

RULES:
1. Look for links related to: planning, zoning, maps, GIS, engineering, documents, or municipal services
2. Consider the website's apparent structure (WordPress, custom CMS, etc.)
3. Prioritize links that seem most likely to lead to zoning maps
4. Provide specific, actionable navigation steps
5. Return valid JSON only
"""
            
            try:
                response = self._call_llm(prompt)
                if response and response.strip():
                    # Parse JSON response
                    import json
                    strategy = json.loads(response.strip())
                    
                    self.logger.info(f"llm.strategy: {strategy.get('assessment', 'No assessment')}")
                    self.logger.info(f"llm.confidence: {strategy.get('confidence', 'unknown')}")
                    
                    return strategy
                else:
                    self.logger.warning("llm.empty_response: LLM returned empty response")
                    return None
                    
            except json.JSONDecodeError as e:
                self.logger.error(f"llm.json_error: Failed to parse LLM response as JSON: {e}")
                return None
            except Exception as e:
                self.logger.error(f"llm.analysis_error: {str(e)}")
                return None
    
    def _llm_explore_page(self, page_url: str, city: str, reason: str) -> List[Dict[str, Any]]:
        """
        LLM-guided exploration of a specific page
        """
        with span(self.logger, "llm.explore_page"):
            self.logger.info(f"llm.exploring: {page_url} - {reason}")
            
            try:
                # Fetch the page
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Cache-Control': 'no-cache'
                }
                
                response = requests.get(page_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                page_text = soup.get_text()
                
                # Direct PDF extraction first
                pdf_candidates = []
                links = soup.find_all('a', href=True)
                
                for link in links:
                    href = link.get('href', '').strip()
                    if href.lower().endswith('.pdf'):
                        # Convert to absolute URL
                        if href.startswith('/'):
                            pdf_url = urljoin(page_url, href)
                        elif href.startswith('http'):
                            pdf_url = href
                        else:
                            pdf_url = urljoin(page_url, href)
                        
                        link_text = link.get_text(strip=True)
                        context_text = self._extract_enhanced_context(link, soup)
                        
                        pdf_info = {
                            'url': pdf_url,
                            'link_text': link_text,
                            'title': link.get('title', ''),
                            'context': context_text,
                            'source_page': page_url,
                            'found_on': f'LLM Navigation - {reason}'
                        }
                        
                        pdf_candidates.append(pdf_info)
                        self.logger.info(f"llm.pdf_found: {link_text} -> {pdf_url}")
                
                # If no PDFs found, ask LLM for next navigation step
                if not pdf_candidates:
                    next_strategy = self._llm_analyze_page_structure(page_url, page_text, city)
                    if next_strategy and next_strategy.get('actions'):
                        # Recursively follow one more level (limit depth)
                        for action in next_strategy['actions'][:1]:  # Only try first action
                            if action.get('type') == 'follow_link':
                                deeper_pdfs = self._llm_explore_page(action['url'], city, action['reason'])
                                pdf_candidates.extend(deeper_pdfs)
                                break
                
                return pdf_candidates
                
            except Exception as e:
                self.logger.error(f"llm.explore_failed: {str(e)}")
                return []
    
    def _llm_test_url_pattern(self, pattern: str, city: str, reason: str) -> List[Dict[str, Any]]:
        """
        Test a URL pattern identified by LLM reasoning
        """
        with span(self.logger, "llm.test_pattern"):
            self.logger.info(f"llm.testing_pattern: {pattern} - {reason}")
            
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                }
                
                response = requests.head(pattern, headers=headers, timeout=10, allow_redirects=True)
                
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '')
                    
                    if 'pdf' in content_type.lower() or pattern.endswith('.pdf'):
                        pdf_info = {
                            'url': pattern,
                            'link_text': f'{city} Zoning Map (LLM Pattern)',
                            'title': '',
                            'context': f'Found via LLM reasoning: {reason}',
                            'source_page': pattern,
                            'found_on': 'LLM Pattern Recognition'
                        }
                        
                        self.logger.info(f"llm.pattern_success: {pattern}")
                        return [pdf_info]
                
                return []
                
            except Exception as e:
                self.logger.debug(f"llm.pattern_failed: {pattern} - {str(e)}")
                return []
    
    def _llm_validate_zoning_pdfs(self, pdf_candidates: List[Dict[str, Any]], city: str) -> List[Dict[str, Any]]:
        """
        Use LLM to validate that found PDFs are actually zoning maps
        """
        with span(self.logger, "llm.validate_pdfs"):
            self.logger.info(f"llm.validating: {len(pdf_candidates)} PDF candidates")
            
            if not pdf_candidates:
                return []
            
            # Prepare PDF information for LLM analysis
            pdf_descriptions = []
            for i, pdf in enumerate(pdf_candidates):
                description = f"""
PDF {i+1}:
- URL: {pdf['url']}
- Link Text: "{pdf['link_text']}"
- Context: "{pdf['context']}"
- Found On: {pdf['found_on']}
"""
                pdf_descriptions.append(description)
            
            prompt = f"""
You are an expert at identifying official municipal zoning maps.

TASK: Analyze these PDF candidates found for {city} and determine which ones are likely to be official zoning maps.

PDF CANDIDATES:
{''.join(pdf_descriptions)}

For each PDF, assess:
1. Does the URL/filename suggest it's a zoning map?
2. Does the link text indicate it's a zoning map?
3. Does the context suggest it's official and current?
4. Is it likely to be the main zoning map (not overlays, amendments, or other documents)?

Respond with a JSON array of PDF numbers (1-{len(pdf_candidates)}) that are most likely to be official zoning maps, ordered by confidence:

{{"validated_pdfs": [1, 3, 2]}}

RULES:
- Prioritize PDFs with "zoning map", "zoning", or "map" in the URL or text
- Prefer newer years (2023, 2024, 2025) over older ones
- Exclude obvious non-maps like ordinances, applications, or amendments
- Return only the PDF numbers, not descriptions
"""
            
            try:
                response = self._call_llm(prompt)
                if response and response.strip():
                    import json
                    validation = json.loads(response.strip())
                    validated_indices = validation.get('validated_pdfs', [])
                    
                    # Return validated PDFs in order
                    validated_pdfs = []
                    for idx in validated_indices:
                        if 1 <= idx <= len(pdf_candidates):
                            validated_pdfs.append(pdf_candidates[idx - 1])  # Convert to 0-based index
                    
                    self.logger.info(f"llm.validated: {len(validated_pdfs)}/{len(pdf_candidates)} PDFs validated as zoning maps")
                    return validated_pdfs
                
                # Fallback: return all candidates if LLM validation fails
                self.logger.warning("llm.validation_failed: Returning all candidates")
                return pdf_candidates
                
            except Exception as e:
                self.logger.error(f"llm.validation_error: {str(e)}")
                return pdf_candidates
    
    def _find_latest_zoning_map(self, official_website: str, city: str, state: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Find the latest Zoning Map of the jurisdiction using comprehensive search
        
        This method provides a fallback when basic navigation fails by:
        1. Performing broader searches across the website
        2. Using search functionality if available
        3. Checking common document repositories
        4. Validating and ranking all found maps by recency and relevance
        
        Args:
            official_website: The official municipal website URL
            city: City name  
            state: State name
            
        Returns:
            Tuple of (pdf_url, metadata_dict) or (None, None)
        """
        with span(self.logger, "agent.find_latest_map"):
            self.logger.info(f"agent.comprehensive_search: Searching {official_website} for latest {city} zoning map")
            
            try:
                # Step 1: Try multiple search strategies
                all_candidates = []
                
                # Strategy 1: Search for common zoning document pages
                document_pages = self._find_document_pages(official_website, city)
                for page_url, page_title in document_pages:
                    page_pdfs = self._extract_pdfs_from_page(page_url, city)
                    all_candidates.extend(page_pdfs)
                
                # Strategy 2: Try site search if available
                search_results = self._try_site_search(official_website, city)
                all_candidates.extend(search_results)
                
                # Strategy 3: Check common URL patterns
                pattern_pdfs = self._check_common_zoning_patterns(official_website, city)
                all_candidates.extend(pattern_pdfs)
                
                if not all_candidates:
                    self.logger.warning(f"agent.no_maps_found: No zoning map candidates found for {city}")
                    return None, None
                
                # Step 2: Remove duplicates and score candidates
                unique_candidates = self._deduplicate_pdfs(all_candidates)
                self.logger.info(f"agent.candidates: Found {len(unique_candidates)} unique zoning map candidates")
                
                # Step 3: Find the most recent and relevant map
                best_map = self._select_best_zoning_map(unique_candidates, city)
                
                if best_map:
                    # Step 4: Extract metadata
                    metadata = self._extract_map_metadata(best_map, city, state)
                    self.logger.info(f"agent.latest_map_found: {best_map}")
                    return best_map, metadata
                else:
                    self.logger.warning(f"agent.no_valid_maps: No valid zoning maps identified for {city}")
                    return None, None
                    
            except Exception as e:
                self.logger.error(f"agent.comprehensive_search_failed: {str(e)}", exc_info=True)
                return None, None
    
    def _find_document_pages(self, website_url: str, city: str) -> List[Tuple[str, str]]:
        """Find pages that commonly contain municipal documents"""
        
        document_keywords = [
            'documents', 'downloads', 'files', 'resources', 'publications',
            'reports', 'forms', 'library', 'repository', 'archive'
        ]
        
        # Use similar logic to _find_planning_pages but with document-focused keywords
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(website_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            document_pages = []
            processed_urls = set()
            
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link.get('href', '').strip()
                text = link.get_text(strip=True).lower()
                
                if not href or href == '#':
                    continue
                
                full_url = urljoin(website_url, href) if href.startswith('/') else href
                
                if full_url in processed_urls or not self._is_same_domain(website_url, full_url):
                    continue
                processed_urls.add(full_url)
                
                # Score based on document keywords
                score = 0
                for keyword in document_keywords:
                    if keyword in text:
                        score += 5
                
                if score > 0:
                    page_title = text or 'Document Page'
                    document_pages.append((full_url, page_title))
            
            self.logger.debug(f"agent.document_pages: Found {len(document_pages)} document pages")
            return document_pages[:5]  # Return top 5
            
        except Exception as e:
            self.logger.error(f"agent.document_page_search_failed: {str(e)}")
            return []
    
    def _try_site_search(self, website_url: str, city: str) -> List[Dict[str, Any]]:
        """Try to use the website's search functionality to find zoning maps"""
        
        try:
            # Look for search forms on the main page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(website_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for search forms
            search_forms = soup.find_all('form')
            search_candidates = []
            
            for form in search_forms:
                # Look for search-related inputs
                search_inputs = form.find_all('input', {'type': ['search', 'text']})
                submit_buttons = form.find_all(['input', 'button'], {'type': 'submit'})
                
                if search_inputs and submit_buttons:
                    action = form.get('action', '')
                    method = form.get('method', 'get').lower()
                    
                    # Try searching for "zoning map"
                    search_url = urljoin(website_url, action) if action else website_url
                    
                    # Attempt search (simplified)
                    search_params = {'q': 'zoning map', 'search': 'zoning map'}
                    
                    try:
                        if method == 'post':
                            search_response = requests.post(search_url, data=search_params, headers=headers, timeout=15)
                        else:
                            search_response = requests.get(search_url, params=search_params, headers=headers, timeout=15)
                        
                        if search_response.status_code == 200:
                            # Extract PDFs from search results
                            search_soup = BeautifulSoup(search_response.content, 'html.parser')
                            search_pdfs = []
                            
                            for link in search_soup.find_all('a', href=True):
                                href = link.get('href', '')
                                if href.lower().endswith('.pdf'):
                                    pdf_url = urljoin(search_url, href)
                                    search_pdfs.append({
                                        'url': pdf_url,
                                        'link_text': link.get_text(strip=True),
                                        'title': '',
                                        'context': 'Found via site search',
                                        'source_page': search_url,
                                        'found_on': 'Site Search Results'
                                    })
                            
                            search_candidates.extend(search_pdfs)
                            
                    except:
                        continue  # Skip failed search attempts
            
            self.logger.debug(f"agent.site_search: Found {len(search_candidates)} PDFs via site search")
            return search_candidates
            
        except Exception as e:
            self.logger.error(f"agent.site_search_failed: {str(e)}")
            return []
    
    def _check_common_zoning_patterns(self, website_url: str, city: str) -> List[Dict[str, Any]]:
        """Check common URL patterns where zoning maps are typically found"""
        
        base_domain = urlparse(website_url).netloc
        city_clean = city.lower().replace(' ', '').replace('-', '')
        
        # Common patterns for zoning map URLs
        patterns = [
            f"{website_url.rstrip('/')}/planning/zoning-map.pdf",
            f"{website_url.rstrip('/')}/documents/zoning-map.pdf",
            f"{website_url.rstrip('/')}/zoning/map.pdf",
            f"{website_url.rstrip('/')}/maps/zoning.pdf",
            f"{website_url.rstrip('/')}/files/zoning-map.pdf",
            f"https://{base_domain}/wp-content/uploads/zoning-map.pdf",
            f"https://{base_domain}/wp-content/uploads/{city_clean}-zoning-map.pdf",
            f"{website_url.rstrip('/')}/planning/{city_clean}-zoning-map.pdf",
        ]
        
        pattern_candidates = []
        
        for pattern_url in patterns:
            try:
                # Check if URL exists (HEAD request)
                response = requests.head(pattern_url, timeout=10, allow_redirects=True)
                if response.status_code == 200 and 'pdf' in response.headers.get('content-type', '').lower():
                    pattern_candidates.append({
                        'url': pattern_url,
                        'link_text': f'{city} Zoning Map',
                        'title': '',
                        'context': 'Found via common URL pattern',
                        'source_page': website_url,
                        'found_on': 'URL Pattern Check'
                    })
                    self.logger.debug(f"agent.pattern_match: Found PDF at {pattern_url}")
                    
            except:
                continue  # Skip failed pattern checks
        
        self.logger.debug(f"agent.pattern_check: Found {len(pattern_candidates)} PDFs via URL patterns")
        return pattern_candidates
    
    def _deduplicate_pdfs(self, pdf_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate PDFs based on URL"""
        
        seen_urls = set()
        unique_pdfs = []
        
        for pdf in pdf_list:
            url = pdf['url']
            if url not in seen_urls:
                seen_urls.add(url)
                unique_pdfs.append(pdf)
        
        return unique_pdfs
    
    def _llm_suggest_navigation_from_homepage(self, website_url: str, city: str) -> List[Tuple[str, str]]:
        """
        Use LLM to analyze homepage and suggest navigation paths to zoning information
        """
        with span(self.logger, "llm.homepage_analysis"):
            self.logger.info(f"🤖 LLM Homepage Analysis: {website_url} for {city}")
            
            try:
                # Fetch homepage content
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Cache-Control': 'no-cache'
                }
                
                response = requests.get(website_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                page_text = soup.get_text()
                
                # Extract all links for LLM analysis
                links = soup.find_all('a', href=True)
                link_info = []
                
                for link in links[:50]:  # Limit to first 50 links to avoid overwhelming LLM
                    href = link.get('href', '').strip()
                    text = link.get_text(strip=True)
                    
                    if href and not href.startswith('#'):
                        # Convert to absolute URL
                        if href.startswith('/'):
                            full_url = urljoin(website_url, href)
                        elif href.startswith('http'):
                            full_url = href
                        else:
                            full_url = urljoin(website_url, href)
                        
                        # Only include internal links
                        if self._is_same_domain(website_url, full_url):
                            link_info.append(f'"{text}" -> {full_url}')
                
                # LLM analysis prompt
                links_text = '\n'.join(link_info[:30])  # Limit for token efficiency
                
                prompt = f"""
You are an expert at navigating municipal websites to find zoning maps.

TASK: Analyze this {city} municipal homepage and identify the most promising navigation paths to find official zoning maps.

HOMEPAGE URL: {website_url}
CITY: {city}

AVAILABLE LINKS:
{links_text}

HOMEPAGE CONTENT SAMPLE:
{page_text[:2000]}

Based on this analysis, provide a JSON response with the most promising pages to explore:

{{
  "analysis": "Your assessment of the website structure and navigation patterns",
  "recommended_pages": [
    {{
      "url": "full URL to explore",
      "reason": "why this page is likely to lead to zoning maps",
      "priority": "high|medium|low"
    }}
  ]
}}

RULES:
1. Focus on links related to: planning, zoning, maps, GIS, engineering, government departments
2. Consider municipal website common patterns (departments, services, documents)
3. Prioritize pages most likely to contain or lead to zoning map documents
4. Return 3-5 most promising pages maximum
5. Provide complete URLs, not relative paths
6. Return valid JSON only
"""
                
                response_text = self._call_llm(prompt)
                if response_text and response_text.strip():
                    import json
                    llm_analysis = json.loads(response_text.strip())
                    
                    self.logger.info(f"llm.homepage_analysis: {llm_analysis.get('analysis', 'No analysis provided')}")
                    
                    # Convert LLM recommendations to our format
                    recommended_pages = []
                    for page in llm_analysis.get('recommended_pages', []):
                        url = page.get('url')
                        reason = page.get('reason', 'LLM recommendation')
                        priority = page.get('priority', 'medium')
                        
                        if url:
                            page_title = f"LLM Recommended ({priority}): {reason}"
                            recommended_pages.append((url, page_title))
                            self.logger.info(f"llm.recommended: {url} - {reason}")
                    
                    return recommended_pages
                
                return []
                
            except Exception as e:
                self.logger.error(f"llm.homepage_analysis_failed: {str(e)}")
                return []
    
    def _submit_zoning_map_search(self, website_url: str, city: str) -> Optional[str]:
        """
        Submit a search for "zoning map" using the municipal website's search functionality
        
        This method:
        1. Finds the search form on the website
        2. Submits a "zoning map" search query
        3. Returns the URL of the search results page
        """
        with span(self.logger, "search.submit"):
            self.logger.info(f"🔍 Finding search form on {website_url}")
            
            try:
                # Fetch the homepage to find search forms
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Cache-Control': 'no-cache'
                }
                
                response = requests.get(website_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for search functionality - multiple detection methods
                search_forms = []
                search_endpoints = []
                
                # Method 1: Traditional HTML forms with search-related attributes
                for form in soup.find_all('form'):
                    action = form.get('action', '')
                    form_id = form.get('id', '')
                    form_class = form.get('class', [])
                    
                    if isinstance(form_class, list):
                        form_class = ' '.join(form_class)
                    
                    # Check if this looks like a search form
                    if any(keyword in action.lower() for keyword in ['search', 'find', 'query']):
                        search_forms.append(form)
                    elif any(keyword in form_id.lower() for keyword in ['search', 'find', 'query']):
                        search_forms.append(form)
                    elif any(keyword in form_class.lower() for keyword in ['search', 'find', 'query']):
                        search_forms.append(form)
                
                # Method 2: Find forms containing search input fields
                if not search_forms:
                    for form in soup.find_all('form'):
                        inputs = form.find_all('input')
                        for input_field in inputs:
                            input_name = input_field.get('name', '')
                            input_id = input_field.get('id', '')
                            input_placeholder = input_field.get('placeholder', '')
                            
                            if any(keyword in input_name.lower() for keyword in ['search', 'query', 'q', 'find']):
                                if form not in search_forms:
                                    search_forms.append(form)
                            elif any(keyword in input_id.lower() for keyword in ['search', 'query', 'q', 'find']):
                                if form not in search_forms:
                                    search_forms.append(form)
                            elif any(keyword in input_placeholder.lower() for keyword in ['search', 'find']):
                                if form not in search_forms:
                                    search_forms.append(form)
                
                # Method 3: Look for JavaScript/AJAX search endpoints
                if not search_forms:
                    self.logger.info(f"search.no_traditional_forms: No HTML forms found, looking for JS search endpoints")
                    search_endpoints = self._find_javascript_search_endpoints(soup, website_url)
                
                # Method 4: Look for standalone search inputs (not in forms)
                if not search_forms and not search_endpoints:
                    self.logger.info(f"search.looking_standalone: Looking for standalone search inputs")
                    standalone_search = self._find_standalone_search_inputs(soup, website_url)
                    if standalone_search:
                        search_endpoints.extend(standalone_search)
                
                # Method 5: Try common municipal search URL patterns
                if not search_forms and not search_endpoints:
                    self.logger.info(f"search.trying_common_patterns: Testing common municipal search patterns")
                    common_search_urls = self._try_common_search_patterns(website_url)
                    search_endpoints.extend(common_search_urls)
                
                if not search_forms and not search_endpoints:
                    self.logger.warning(f"search.no_search_found: No search functionality found on {website_url}")
                    return None
                
                # Try HTML forms first
                for i, form in enumerate(search_forms[:3]):  # Try up to 3 forms
                    self.logger.info(f"search.trying_form: Attempting search form {i+1}")
                    
                    result_url = self._execute_search_form(form, website_url, "zoning map", city)
                    if result_url:
                        return result_url
                
                # Try search endpoints if forms failed
                for i, endpoint_url in enumerate(search_endpoints[:3]):  # Try up to 3 endpoints
                    self.logger.info(f"search.trying_endpoint: Attempting search endpoint {i+1}")
                    
                    result_url = self._execute_search_endpoint(endpoint_url, "zoning map", city)
                    if result_url:
                        return result_url
                
                # Try alternative Franklin search approaches if the main method failed
                if city.lower() == "franklin":
                    self.logger.info(f"search.trying_franklin_alternatives: Trying alternative Franklin search methods")
                    franklin_alternatives = self._try_franklin_search_alternatives(website_url)
                    for alt_url in franklin_alternatives:
                        result_url = self._execute_search_endpoint(alt_url, "zoning map", city)
                        if result_url:
                            return result_url
                
                self.logger.warning(f"search.all_methods_failed: All search methods failed for {website_url}")
                return None
                
            except Exception as e:
                self.logger.error(f"search.form_error: {str(e)}")
                return None
    
    def _try_franklin_search_alternatives(self, website_url: str) -> List[str]:
        """
        Try alternative search approaches specifically for Franklin
        """
        alternatives = []
        
        # Alternative 1: Try different parameter combinations
        base_search_url = urljoin(website_url, "/Search")
        
        franklin_variations = [
            # Try without pagination parameters
            f"{base_search_url}?searchPhrase=zoning+map",
            
            # Try with different pagination
            f"{base_search_url}?searchPhrase=zoning+map&pageNumber=1&perPage=20&departmentId=-1",
            f"{base_search_url}?searchPhrase=zoning+map&pageNumber=1&perPage=50&departmentId=-1",
            
            # Try different search terms
            f"{base_search_url}?searchPhrase=zoning&pageNumber=1&perPage=10&departmentId=-1",
            f"{base_search_url}?searchPhrase=map&pageNumber=1&perPage=10&departmentId=-1",
            
            # Try the Results endpoint directly
            f"{urljoin(website_url, '/Search/Results')}?searchPhrase=zoning+map&pageNumber=1&perPage=10&departmentId=-1",
            
            # Try with document type filtering
            f"{base_search_url}?searchPhrase=zoning+map&pageNumber=1&perPage=10&departmentId=-1&contentType=Documents"
        ]
        
        alternatives.extend(franklin_variations)
        
        self.logger.info(f"franklin.alternatives: Generated {len(alternatives)} alternative search URLs")
        return alternatives
    
    def _execute_search_form(self, form, base_url: str, search_term: str, city: str) -> Optional[str]:
        """
        Execute a search form with the given search term
        """
        with span(self.logger, "search.execute"):
            try:
                # Get form action and method
                action = form.get('action', '')
                method = form.get('method', 'GET').upper()
                
                # Convert relative action to absolute URL
                if action.startswith('/'):
                    action_url = urljoin(base_url, action)
                elif action.startswith('http'):
                    action_url = action
                elif action:
                    action_url = urljoin(base_url, action)
                else:
                    action_url = base_url  # Submit to same page
                
                # Build form data
                form_data = {}
                
                # Find the search input field
                search_input_found = False
                for input_field in form.find_all('input'):
                    input_name = input_field.get('name', '')
                    input_type = input_field.get('type', 'text')
                    input_value = input_field.get('value', '')
                    
                    if input_type.lower() in ['text', 'search'] and not search_input_found:
                        # This is likely the search field
                        if any(keyword in input_name.lower() for keyword in ['search', 'query', 'q', 'find', 'term']):
                            form_data[input_name] = search_term
                            search_input_found = True
                            self.logger.info(f"search.field_found: Using search field '{input_name}' = '{search_term}'")
                    elif input_type.lower() == 'hidden':
                        # Include hidden fields
                        if input_name and input_value:
                            form_data[input_name] = input_value
                
                # If no clear search field found, try common names
                if not search_input_found:
                    common_search_names = ['q', 'query', 'search', 'term', 'searchterm', 'keyword', 'find']
                    for name in common_search_names:
                        form_data[name] = search_term
                        self.logger.info(f"search.fallback_field: Trying fallback field '{name}' = '{search_term}'")
                        break
                
                # Submit the search
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Referer': base_url
                }
                
                if method == 'POST':
                    response = requests.post(action_url, data=form_data, headers=headers, timeout=30, allow_redirects=True)
                else:
                    response = requests.get(action_url, params=form_data, headers=headers, timeout=30, allow_redirects=True)
                
                response.raise_for_status()
                
                # Check if we got search results
                if 'search' in response.url.lower() or 'result' in response.url.lower():
                    self.logger.info(f"search.success: Search submitted successfully -> {response.url}")
                    return response.url
                else:
                    self.logger.warning(f"search.unexpected_url: Search may have failed, got {response.url}")
                    return response.url  # Try anyway
                
            except Exception as e:
                self.logger.error(f"search.execute_error: {str(e)}")
                return None
    
    def _find_javascript_search_endpoints(self, soup, website_url: str) -> List[str]:
        """
        Find JavaScript-based search endpoints by analyzing page content and URLs
        """
        search_endpoints = []
        page_text = str(soup)
        
        # Look for search-related JavaScript URLs and endpoints
        import re
        
        # Enhanced patterns for municipal search endpoints
        search_patterns = [
            # Franklin-style patterns
            r'/Search\?[^"\']*',
            r'/Search/Results',
            r'/Search/',
            
            # Foxborough-style patterns  
            r'/search/default\.aspx\?[^"\']*',
            r'/search/default\.aspx',
            
            # General patterns
            r'/search\.aspx\?[^"\']*',
            r'/search\.aspx',
            r'/search\.php\?[^"\']*', 
            r'/search\.php',
            r'/search/\?[^"\']*',
            r'/search/',
            r'/site-search/\?[^"\']*',
            r'/find/\?[^"\']*',
            r'/query/\?[^"\']*',
            r'search\.action\?[^"\']*',
            r'searchform\.action\?[^"\']*'
        ]
        
        for pattern in search_patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            for match in matches:
                if match.startswith('/'):
                    full_url = urljoin(website_url, match)
                else:
                    full_url = urljoin(website_url, '/' + match)
                
                if full_url not in search_endpoints:
                    search_endpoints.append(full_url)
                    self.logger.info(f"search.js_endpoint_found: {full_url}")
        
        # Also look for search action URLs in form elements and JavaScript
        # Look for action attributes in any elements
        for element in soup.find_all(attrs={'action': True}):
            action = element.get('action', '')
            if any(keyword in action.lower() for keyword in ['search', 'find', 'query']):
                if action.startswith('/'):
                    full_url = urljoin(website_url, action)
                elif action.startswith('http'):
                    full_url = action
                else:
                    full_url = urljoin(website_url, '/' + action)
                
                if full_url not in search_endpoints:
                    search_endpoints.append(full_url)
                    self.logger.info(f"search.action_endpoint_found: {full_url}")
        
        return search_endpoints
    
    def _find_standalone_search_inputs(self, soup, website_url: str) -> List[str]:
        """
        Find search inputs that are not inside forms (JavaScript-controlled)
        """
        search_endpoints = []
        
        # Look for search inputs not inside forms
        all_inputs = soup.find_all('input')
        for input_field in all_inputs:
            # Check if this input is inside a form
            parent_form = input_field.find_parent('form')
            if parent_form:
                continue  # Skip inputs that are in forms
            
            input_name = input_field.get('name', '')
            input_id = input_field.get('id', '')
            input_placeholder = input_field.get('placeholder', '')
            input_type = input_field.get('type', 'text')
            
            # Check if this looks like a search input
            is_search_input = False
            if input_type.lower() in ['text', 'search']:
                if any(keyword in input_name.lower() for keyword in ['search', 'query', 'q', 'find']):
                    is_search_input = True
                elif any(keyword in input_id.lower() for keyword in ['search', 'query', 'q', 'find']):
                    is_search_input = True
                elif any(keyword in input_placeholder.lower() for keyword in ['search', 'find']):
                    is_search_input = True
            
            if is_search_input:
                # Try to construct search URL patterns based on common municipal patterns
                search_url_candidates = [
                    urljoin(website_url, '/Search/Results'),
                    urljoin(website_url, '/search/'),
                    urljoin(website_url, '/search.aspx'),
                    urljoin(website_url, '/search.php')
                ]
                
                for url in search_url_candidates:
                    if url not in search_endpoints:
                        search_endpoints.append(url)
                        self.logger.info(f"search.standalone_input_endpoint: {url}")
                
                break  # Found one search input, that's enough
        
        return search_endpoints
    
    def _try_common_search_patterns(self, website_url: str) -> List[str]:
        """
        Try common municipal website search URL patterns
        """
        search_endpoints = []
        
        # Common municipal search URL patterns (based on real examples)
        common_patterns = [
            # Franklin-style patterns
            '/Search?searchPhrase=test&pageNumber=1&perPage=10&departmentId=-1',
            '/Search/Results',
            '/Search/',
            
            # Foxborough-style patterns
            '/search/default.aspx?q=test&type=-1,15207864-20174812|0,15207780-20479241,15207780-20894076&sortby=Relevance&pg=0',
            '/search/default.aspx',
            
            # General patterns
            '/search/',
            '/search.aspx',
            '/search.php',
            '/search.html',
            '/site-search/',
            '/search-results/',
            '/find/',
            '/query/'
        ]
        
        for pattern in common_patterns:
            test_url = urljoin(website_url, pattern)
            
            try:
                # Quick test to see if this endpoint exists
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                }
                
                # Test with a simple GET request first
                response = requests.head(test_url, headers=headers, timeout=5, allow_redirects=True)
                
                if response.status_code in [200, 302, 404]:  # 404 is OK for search pages without query
                    search_endpoints.append(test_url)
                    self.logger.info(f"search.common_pattern_found: {test_url}")
                
                time.sleep(0.2)  # Small delay between requests
                
            except:
                continue
        
        return search_endpoints
    
    def _execute_search_endpoint(self, endpoint_url: str, search_term: str, city: str) -> Optional[str]:
        """
        Execute a search using a discovered endpoint URL with intelligent parameter detection
        """
        with span(self.logger, "search.execute_endpoint"):
            try:
                self.logger.info(f"search.endpoint_attempt: {endpoint_url}")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Cache-Control': 'no-cache'
                }
                
                # Parse the endpoint URL to understand its structure
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(endpoint_url)
                existing_params = parse_qs(parsed_url.query)
                
                # Build the base URL without parameters
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                
                # Determine the search parameter strategy based on URL structure and existing parameters
                search_strategies = self._build_search_strategies(endpoint_url, existing_params, search_term)
                
                for strategy_name, params in search_strategies:
                    try:
                        self.logger.info(f"search.trying_strategy: {strategy_name} with params: {list(params.keys())}")
                        
                        response = requests.get(base_url, params=params, headers=headers, timeout=30, allow_redirects=True)
                        
                        if response.status_code == 200:
                            # Check if this looks like search results with actual content
                            content_lower = response.text.lower()
                            
                            # Check for search result structure indicators
                            has_search_structure = any(indicator in content_lower for indicator in [
                                'search results', 'results for', 'found', 'matches', 
                                'showing', 'displaying', 'items found', 'results found'
                            ])
                            
                            # Check for actual result content (not just the search interface)
                            has_actual_results = any(indicator in content_lower for indicator in [
                                'zoning map (pdf)', 'pdf)', '.pdf', 'document', 'view/', 
                                'download', 'documentcenter'
                            ])
                            
                            # Check for Franklin-specific result patterns
                            has_franklin_results = any(pattern in content_lower for pattern in [
                                '/documentcenter/view/', 'dec ', 'oct ', '2024', '2023',
                                'zoning map', 'map 6.3'
                            ])
                            
                            if has_search_structure and (has_actual_results or has_franklin_results):
                                self.logger.info(f"search.strategy_success: {strategy_name} -> {response.url}")
                                self.logger.info(f"search.result_validation: Structure={has_search_structure}, Content={has_actual_results}, Franklin={has_franklin_results}")
                                return response.url
                            elif has_search_structure:
                                self.logger.warning(f"search.empty_results: {strategy_name} - found search structure but no actual results")
                            else:
                                self.logger.debug(f"search.strategy_no_results: {strategy_name} - no clear search results detected")
                        
                        time.sleep(0.5)  # Delay between attempts
                        
                    except Exception as e:
                        self.logger.debug(f"search.strategy_failed: {strategy_name} - {str(e)}")
                        continue
                
                return None
                
            except Exception as e:
                self.logger.error(f"search.endpoint_error: {str(e)}")
                return None
    
    def _build_search_strategies(self, endpoint_url: str, existing_params: dict, search_term: str) -> List[tuple]:
        """
        Build intelligent search strategies based on URL structure and existing parameters
        """
        strategies = []
        
        # Strategy 1: Franklin-style (searchPhrase parameter)
        if '/Search' in endpoint_url or 'searchPhrase' in str(existing_params):
            franklin_params = {}
            
            # Preserve existing parameters
            for key, values in existing_params.items():
                if values:  # Skip empty parameters
                    franklin_params[key] = values[0] if len(values) == 1 else values
            
            # Add Franklin-specific search parameters
            franklin_params.update({
                'searchPhrase': search_term,
                'pageNumber': '1',
                'perPage': '10',
                'departmentId': '-1'
            })
            
            strategies.append(("Franklin-style", franklin_params))
        
        # Strategy 2: Foxborough-style (q parameter with complex type filtering)
        if '/search/default.aspx' in endpoint_url or 'type=' in endpoint_url:
            foxborough_params = {}
            
            # Preserve existing parameters
            for key, values in existing_params.items():
                if values:
                    foxborough_params[key] = values[0] if len(values) == 1 else values
            
            # Add Foxborough-specific parameters
            foxborough_params.update({
                'q': search_term,
                'sortby': 'Relevance',
                'pg': '0'
            })
            
            # If no type parameter exists, add a comprehensive one
            if 'type' not in foxborough_params:
                foxborough_params['type'] = '-1,15207864-20174812|0,15207780-20479241,15207780-20894076'
            
            strategies.append(("Foxborough-style", foxborough_params))
        
        # Strategy 3: Standard municipal patterns
        standard_search_params = [
            ("Standard-q", {'q': search_term}),
            ("Standard-query", {'query': search_term}),
            ("Standard-search", {'search': search_term}),
            ("Standard-term", {'term': search_term, 'type': 'all'}),
            ("Standard-keyword", {'keyword': search_term}),
            ("Standard-find", {'find': search_term})
        ]
        
        # Add standard strategies, preserving existing parameters
        for strategy_name, base_params in standard_search_params:
            params = {}
            
            # Preserve existing parameters first
            for key, values in existing_params.items():
                if values:
                    params[key] = values[0] if len(values) == 1 else values
            
            # Add search parameters
            params.update(base_params)
            
            strategies.append((strategy_name, params))
        
        # Strategy 4: ASP.NET specific patterns
        if '.aspx' in endpoint_url:
            aspnet_params = {}
            
            # Preserve existing parameters
            for key, values in existing_params.items():
                if values:
                    aspnet_params[key] = values[0] if len(values) == 1 else values
            
            aspnet_params.update({
                'q': search_term,
                'searchtext': search_term,
                'keywords': search_term
            })
            
            strategies.append(("ASP.NET-style", aspnet_params))
        
        return strategies
    
    def _parse_search_results(self, search_results_url: str, city: str) -> List[Dict[str, Any]]:
        """
        Parse search results page to extract actual search result entries with titles and dates
        """
        with span(self.logger, "search.parse_results"):
            self.logger.info(f"📋 Parsing search results: {search_results_url}")
            
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Cache-Control': 'no-cache'
                }
                
                response = requests.get(search_results_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                self.logger.info(f"search.results_page_size: {len(response.text)} characters")
                
                # Extract all the raw HTML content to send to LLM for parsing
                page_html = str(soup)
                
                # Use LLM to intelligently parse the search results
                search_results = self._llm_parse_search_results(page_html, search_results_url, city)
                
                self.logger.info(f"search.llm_results_found: {len(search_results)} search results parsed by LLM")
                
                return search_results
                
            except Exception as e:
                self.logger.error(f"search.parse_error: {str(e)}")
                return []
    
    def _extract_date_from_text(self, text: str) -> Optional[str]:
        """
        Extract date information from text (prioritize recent years)
        """
        import re
        
        # Look for 4-digit years (2020-2025)
        year_pattern = r'\b(202[0-5])\b'
        years = re.findall(year_pattern, text)
        if years:
            return years[-1]  # Return the last/most recent year found
        
        # Look for date patterns like "Dec 13, 2024" or "2024-12-13"
        date_patterns = [
            r'\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(202[0-5])\b',  # "Dec 13, 2024"
            r'\b(202[0-5])-(\d{1,2})-(\d{1,2})\b',  # "2024-12-13"
            r'\b(\d{1,2})/(\d{1,2})/(202[0-5])\b',  # "12/13/2024"
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                match = matches[-1]  # Get the last match
                if len(match) == 3 and match[2].startswith('202'):
                    return match[2]  # Return the year
        
        return None
    
    def _llm_parse_search_results(self, page_html: str, search_url: str, city: str) -> List[Dict[str, Any]]:
        """
        Use LLM to parse search results HTML and extract search result entries with titles and dates
        """
        with span(self.logger, "llm.parse_search_results"):
            try:
                # Clean and truncate HTML for LLM processing
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(page_html, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Get clean text version for LLM analysis
                clean_text = soup.get_text()
                
                # DEBUG: Log the actual search results content
                self.logger.info(f"🔍 SEARCH RESULTS DEBUG - First 2000 characters:")
                self.logger.info(f"--- START SEARCH RESULTS ---")
                self.logger.info(clean_text[:2000])
                self.logger.info(f"--- END SEARCH RESULTS SAMPLE ---")
                
                # Look for key indicators that this is actually a search results page
                if "search results" in clean_text.lower():
                    self.logger.info(f"✅ Found 'search results' text - this appears to be a search results page")
                elif "zoning map" in clean_text.lower():
                    self.logger.info(f"✅ Found 'zoning map' text - relevant content detected")
                elif "no results" in clean_text.lower() or "0 results" in clean_text.lower():
                    self.logger.warning(f"❌ Search returned no results")
                else:
                    self.logger.warning(f"⚠️  This might not be a search results page - no clear indicators found")
                
                # Check for actual search result entries vs just the search interface
                result_indicators = [
                    "pdf)", "(pdf", ".pdf", "document", "view/", "download"
                ]
                
                found_actual_results = any(indicator in clean_text.lower() for indicator in result_indicators)
                
                if found_actual_results:
                    self.logger.info(f"✅ Found potential search result entries (PDF/document indicators)")
                else:
                    self.logger.warning(f"⚠️  No actual search result entries found - might be empty results or search interface only")
                    
                # Try to find structured result patterns
                import re
                pdf_patterns = re.findall(r'(.*?pdf.*?)(?:\n|$)', clean_text, re.IGNORECASE)
                document_patterns = re.findall(r'(.*?document.*?)(?:\n|$)', clean_text, re.IGNORECASE)
                
                self.logger.info(f"📄 Found {len(pdf_patterns)} lines mentioning PDF")
                self.logger.info(f"📋 Found {len(document_patterns)} lines mentioning documents")
                
                if pdf_patterns:
                    self.logger.info(f"🔍 Sample PDF mentions:")
                    for i, pattern in enumerate(pdf_patterns[:3]):
                        self.logger.info(f"  {i+1}. {pattern.strip()[:100]}")
                        
                # Look for Franklin-specific result patterns  
                franklin_patterns = re.findall(r'(zoning.*?map.*?)(?:\n|$)', clean_text, re.IGNORECASE)
                if franklin_patterns:
                    self.logger.info(f"🎯 Found {len(franklin_patterns)} potential zoning map references:")
                    for i, pattern in enumerate(franklin_patterns[:3]):
                        self.logger.info(f"  {i+1}. {pattern.strip()[:100]}")
                
                # Truncate if too long (LLM token limits)
                if len(clean_text) > 4000:
                    clean_text = clean_text[:4000] + "..."
                
                prompt = f"""
Extract zoning maps from these search results for {city}.

SEARCH RESULTS:
{clean_text}

Find entries with "Zoning Map" and return this JSON:
[
  {{
    "title": "Zoning Map (PDF)",
    "date": "Dec 13, 2024",
    "url": "/documentcenter/view/430"
  }}
]

Include the date if visible. Only return the JSON array. If no zoning maps found, return []
"""
                
                # DEBUG: Log the complete prompt being sent to LLM
                self.logger.info(f"🤖 EXTRACTION PROMPT DEBUG:")
                self.logger.info(f"--- START EXTRACTION PROMPT ---")
                self.logger.info(prompt)
                self.logger.info(f"--- END EXTRACTION PROMPT ---")
                self.logger.info(f"📏 Prompt length: {len(prompt)} characters")
                
                response = self._call_llm_classification(prompt)
                
                # DEBUG: Log the LLM response
                self.logger.info(f"🤖 LLM RESPONSE DEBUG:")
                self.logger.info(f"--- START LLM RESPONSE ---")
                if response:
                    self.logger.info(f"Response length: {len(response)} characters")
                    self.logger.info(f"Response content: '{response[:500]}{'...' if len(response) > 500 else ''}'")
                else:
                    self.logger.error(f"❌ LLM returned None or empty response")
                self.logger.info(f"--- END LLM RESPONSE ---")
                
                if response and response.strip():
                    import json
                    try:
                        # Clean up LLM response - remove markdown code blocks if present
                        clean_response = response.strip()
                        if clean_response.startswith('```json'):
                            clean_response = clean_response.replace('```json', '').replace('```', '').strip()
                        elif clean_response.startswith('```'):
                            clean_response = clean_response.replace('```', '').strip()
                        
                        parsed_results = json.loads(clean_response)
                        
                        # Convert JSON to our internal format (with date for selection)
                        search_results = []
                        for result in parsed_results:
                            title = result.get('title', '')
                            date = result.get('date', '')
                            url = result.get('url', '')
                            
                            # Skip empty results
                            if not title or not url:
                                continue
                            
                            # Convert relative URLs to absolute
                            if url.startswith('/'):
                                full_url = urljoin(search_url, url)
                            elif url.startswith('http'):
                                full_url = url
                            else:
                                full_url = urljoin(search_url, '/' + url)
                            
                            # Smart PDF detection - only based on actual PDF indicators
                            pdf_in_title = 'pdf' in title.lower()
                            documentcenter_url = 'documentcenter' in full_url.lower()
                            view_url = '/view/' in full_url.lower()
                            pdf_extension = full_url.lower().endswith('.pdf')
                            documents_with_pdf = ('/documents/' in full_url.lower() and 'pdf' in title.lower())
                            
                            is_pdf = (pdf_in_title or documentcenter_url or view_url or pdf_extension or documents_with_pdf)
                            
                            # Debug PDF detection
                            if is_pdf:
                                reasons = []
                                if pdf_in_title: reasons.append("PDF in title")
                                if documentcenter_url: reasons.append("DocumentCenter URL")
                                if view_url: reasons.append("View URL")
                                if pdf_extension: reasons.append("PDF extension")
                                if documents_with_pdf: reasons.append("Documents folder + PDF title")
                                self.logger.info(f"📄 PDF DETECTED: '{title}' -> Reasons: {', '.join(reasons)}")
                            else:
                                self.logger.info(f"📝 WEB PAGE: '{title}' -> URL: {full_url}")
                            
                            search_result = {
                                'title': title,
                                'date': date,  # Keep date for selection logic
                                'url': full_url,
                                'is_pdf': is_pdf,  # Smart PDF detection
                                'context': '',  # Not needed for simple format
                                'source_page': search_url,
                                'found_via': 'selenium_search'
                            }
                            
                            search_results.append(search_result)
                            self.logger.info(f"🎯 FOUND ZONING MAP: '{title}' ({date}) -> {full_url}")
                        
                        self.logger.info(f"🔍 Successfully parsed {len(search_results)} zoning maps from LLM")
                        return search_results
                        
                    except json.JSONDecodeError as e:
                        self.logger.error(f"llm.json_parse_error: {str(e)}")
                        return []
                
                return []
                
            except Exception as e:
                self.logger.error(f"llm.parse_search_error: {str(e)}")
                return []
    
    def _select_most_recent_zoning_map(self, candidates: List[Dict[str, Any]], city: str) -> Optional[str]:
        """
        Use LLM to select the most recent and appropriate zoning map from candidates.
        Only considers actual PDF candidates.
        """
        with span(self.logger, "llm.select_zoning_map"):
            if not candidates:
                return None
            
            self.logger.info(f"🤖 LLM Selection: Received {len(candidates)} total candidates for {city}")
            
            # Filter to only consider PDF candidates
            pdf_candidates = [c for c in candidates if c.get('is_pdf', False)]
            
            if not pdf_candidates:
                self.logger.warning(f"🚫 NO PDF CANDIDATES: All {len(candidates)} candidates are web pages, not PDFs")
                return None
            
            self.logger.info(f"📄 PDF FILTERING: {len(pdf_candidates)}/{len(candidates)} candidates are actual PDFs")
            
            # Use only PDF candidates for LLM selection
            candidates = pdf_candidates
            
            # Prepare candidate descriptions for LLM
            candidate_descriptions = []
            for i, candidate in enumerate(candidates):
                description = f"""
Candidate {i+1}:
- Title: "{candidate.get('title', '')}"
- Date: {candidate.get('date', 'No date')}
- URL: {candidate.get('url', '')}
- Is PDF: {candidate.get('is_pdf', False)}
- Context: {candidate.get('context', '')[:100]}
"""
                candidate_descriptions.append(description)
            
            candidates_text = '\n'.join(candidate_descriptions)
            
            prompt = f"""
Select the BEST zoning map PDF for {city}.

PDF CANDIDATES (all are confirmed PDFs):
{candidates_text}

RULES:
- Choose the candidate with the MOST RECENT "Date", do not prioritize by the order they appear in the list.
- Prioritize official/comprehensive zoning maps over partial district maps
- If there's only 1 candidate, select it (return 1)

Return only the candidate number (1, 2, 3, etc.).
All candidates are confirmed PDFs, so return 0 only if none appear to be zoning maps.
"""
            
            try:
                # DEBUG: Log what we're sending to the LLM
                self.logger.info(f"🤖 SELECTION PROMPT DEBUG:")
                self.logger.info(f"--- START SELECTION PROMPT ---")
                self.logger.info(prompt)
                self.logger.info(f"--- END SELECTION PROMPT ---")
                
                response = self._call_llm_classification(prompt)
                
                # DEBUG: Log LLM response
                self.logger.info(f"🤖 SELECTION LLM RESPONSE: '{response}'")
                
                if response and response.strip():
                    try:
                        selected_number = int(response.strip())
                        
                        if 1 <= selected_number <= len(candidates):
                            selected_candidate = candidates[selected_number - 1]
                            selected_url = selected_candidate.get('url', '')
                            selected_title = selected_candidate.get('title', '')
                            selected_date = selected_candidate.get('date', '')
                            
                            self.logger.info(f"🎯 LLM SELECTED: '{selected_title}' ({selected_date}) -> {selected_url}")
                            return selected_url
                        elif selected_number == 0:
                            self.logger.warning(f"llm.no_suitable_maps: LLM found no suitable zoning maps")
                            return None
                        else:
                            self.logger.error(f"llm.invalid_selection: LLM returned invalid number {selected_number}")
                            return None
                    
                    except ValueError:
                        self.logger.error(f"llm.invalid_response: Could not parse LLM response as number: '{response}'")
                        return None
                
                self.logger.error(f"llm.empty_response: LLM returned empty response")
                return None
                
            except Exception as e:
                self.logger.error(f"llm.selection_error: {str(e)}")
                return None
    
    def _download_and_verify_pdf(self, pdf_url: str, city: str) -> Optional[str]:
        """
        Download PDF to verify it's accessible and return local path for review
        
        Args:
            pdf_url: URL of the PDF to download
            city: City name for filename
            
        Returns:
            Local file path if successful, None if failed
        """
        with span(self.logger, "agent.download_pdf"):
            self.logger.info(f"📥 DOWNLOADING PDF FOR VERIFICATION:")
            self.logger.info(f"🔗 PDF URL: {pdf_url}")
            
            try:
                # Create downloads directory
                downloads_dir = "pdf_downloads"
                os.makedirs(downloads_dir, exist_ok=True)
                
                # Generate filename
                from urllib.parse import urlparse
                parsed_url = urlparse(pdf_url)
                filename = parsed_url.path.split('/')[-1]
                if not filename.endswith('.pdf'):
                    filename = f"{city}_zoning_map.pdf"
                
                local_path = os.path.join(downloads_dir, f"{city}_{filename}")
                
                # Download headers
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'application/pdf,*/*',
                }
                
                self.logger.info(f"📁 Downloading to: {local_path}")
                
                # Download the PDF
                response = requests.get(pdf_url, headers=headers, timeout=30, stream=True)
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                self.logger.info(f"📄 Content-Type: {content_type}")
                
                if 'pdf' not in content_type.lower() and not pdf_url.endswith('.pdf'):
                    self.logger.warning(f"⚠️  Warning: Content-Type is not PDF: {content_type}")
                
                # Save the file
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_size = os.path.getsize(local_path)
                self.logger.info(f"✅ PDF Downloaded Successfully:")
                self.logger.info(f"   📁 Local Path: {local_path}")
                self.logger.info(f"   📏 File Size: {file_size:,} bytes")
                self.logger.info(f"   🔗 Original URL: {pdf_url}")
                
                return local_path
                
            except Exception as e:
                self.logger.error(f"❌ PDF Download Failed: {str(e)}")
                self.logger.error(f"   🔗 Failed URL: {pdf_url}")
                return None


# =====================================
# 4. PROCESS 1: ZONING MAP ANALYSIS
# =====================================
    
    def analyze_zoning_district(self, zoning_map_url: str, address: str, lat: float = None, lon: float = None) -> Optional[Dict[str, Any]]:
        """
        Analyze the zoning map to determine the zoning district for a given address using an LLM with web browsing
        
        Args:
            zoning_map_url: URL to the zoning map (PDF or web page)
            address: Full address string
            lat: Latitude coordinate (optional, not used in current implementation)
            lon: Longitude coordinate (optional, not used in current implementation)
            
        Returns:
            Dictionary with zoning_code, zoning_name, and overlays, or None if analysis fails
        """
        with span(self.logger, "agent.analyze_zoning"):
            try:
                self.logger.info(f"📋 ZONING ANALYSIS: Starting web-based analysis for {address}")
                self.logger.info(f"🔗 ZONING MAP URL: {zoning_map_url}")
                
                # Use the zoning analysis prompt with web URL
                prompt_template = """You are an expert in analyzing U.S. municipal zoning maps.

INPUTS YOU ARE RECEIVING:
1. An official zoning map of a specific jurisdiction: {zoning_map_url}
2. A full street address that lies within that jurisdiction: {address}

YOUR TASK:
- Access the zoning map at the provided URL.
- Locate the parcel for the given address on the zoning map.
- Match its position with the correct zoning district shown on the map.
- Return only the zoning **code** (e.g., "R-1") and the **district name** (e.g., "Single Residence District").
- If there are overlays shown on the map (historic, corridor, TOD, groundwater, etc.), list them as well.
- Also include the **map adoption date** if it is present on the map.

OUTPUT FORMAT:
Always return a valid JSON object with this schema:
{{
  "zoning_code": "<string>",
  "zoning_name": "<string>",
  "overlays": ["<string>", "<string>"]
}}

RULES:
- Return ONLY the JSON object - no explanations, no markdown, no code blocks.
- The response must be valid JSON that can be parsed directly.
- Do not output anything outside of the JSON object.
- If the address is not found on the map, return:
  {{
    "zoning_code": null,
    "zoning_name": null,
    "overlays": []
  }}"""
                
                prompt = prompt_template.format(zoning_map_url=zoning_map_url, address=address)
                
                self.logger.info(f"🤖 CALLING LLM: Analyzing zoning map via web access")
                
                # Call LLM with web browsing capability
                response = self._call_llm_with_web_access(prompt, zoning_map_url, address)
                
                if response:
                    import json
                    try:
                        # Clean the response - remove potential markdown wrappers
                        cleaned_response = response.strip()
                        
                        # Remove markdown code block wrappers if present (fallback safety)
                        if cleaned_response.startswith('```json'):
                            cleaned_response = cleaned_response[7:]  # Remove ```json
                        if cleaned_response.startswith('```'):
                            cleaned_response = cleaned_response[3:]   # Remove ```
                        if cleaned_response.endswith('```'):
                            cleaned_response = cleaned_response[:-3]  # Remove trailing ```
                        
                        cleaned_response = cleaned_response.strip()
                        
                        self.logger.info(f"🧹 CLEANED RESPONSE: {cleaned_response}")
                        
                        # Parse the JSON response
                        zoning_data = json.loads(cleaned_response)
                        
                        self.logger.info(f"✅ ZONING ANALYSIS SUCCESS:")
                        self.logger.info(f"   🏠 Address: {address}")
                        self.logger.info(f"   🗺️ Zoning Code: {zoning_data.get('zoning_code')}")
                        self.logger.info(f"   📝 Zoning Name: {zoning_data.get('zoning_name')}")
                        self.logger.info(f"   🔄 Overlays: {zoning_data.get('overlays', [])}")
                        self.logger.info(f"   🤖 Model Used: {getattr(self, 'last_successful_model', 'Unknown')}")
                        
                        return zoning_data
                        
                    except json.JSONDecodeError as e:
                        self.logger.error(f"❌ JSON PARSE ERROR: {str(e)}")
                        self.logger.error(f"📄 Raw LLM Response: {response}")
                        self.logger.error(f"📄 Cleaned Response: {cleaned_response}")
                        return None
                else:
                    self.logger.error(f"❌ LLM ANALYSIS FAILED: No response from {getattr(self, 'last_successful_model', 'the model')}")
                    return None
                
            except Exception as e:
                self.logger.error(f"❌ ZONING ANALYSIS ERROR: {str(e)}", exc_info=True)
                return None
    
    def _call_llm_with_web_access(self, prompt: str, zoning_map_url: str, address: str) -> Optional[str]:
        """
        Call LLM via OpenRouter with actual PDF analysis capability
        """
        try:
            import httpx
            import os
            from dotenv import load_dotenv
            
            load_dotenv()
            api_key = os.getenv("OPENROUTER_API_KEY")
            
            if not api_key:
                self.logger.error("❌ OPENROUTER_API_KEY not found in environment variables")
                return None
            
            self.logger.info(f"🤖 REAL ANALYSIS: Fetching and analyzing zoning map at {zoning_map_url}")
            
            # Step 1: Fetch the PDF content
            pdf_content = self._fetch_pdf_content(zoning_map_url)
            if not pdf_content:
                self.logger.error(f"❌ Failed to fetch PDF content from {zoning_map_url}")
                return None
            
            # Step 2: Prepare enhanced prompt with PDF content
            enhanced_prompt = f"""You are an expert in analyzing U.S. municipal zoning maps.

INPUTS YOU ARE RECEIVING:
1. An official zoning map of a specific jurisdiction: {zoning_map_url}
2. A full street address that lies within that jurisdiction: {address}
3. PDF Content (text extracted from the zoning map): 
{pdf_content[:4000]}...

YOUR TASK:
Quickly identify the zoning district for the given address from the PDF content. Be direct and concise.

REQUIRED OUTPUT:
Return ONLY a JSON object with the zoning code, name, and overlays:

{{
  "zoning_code": "<code like R-1, B-I, C-2>",
  "zoning_name": "<full name like Business Interstate>", 
  "overlays": ["<any overlays like TOD, Historic>"]
}}

CRITICAL RULES:
- NO explanations, reasoning, or markdown
- ONLY output the JSON object
- Be concise to stay within token limits
- If not found: {{"zoning_code": null, "zoning_name": null, "overlays": []}}

ADDRESS TO ANALYZE: {address}
"""
            
            # DEBUG: Print the complete prompt being sent to LLM
            self.logger.info(f"🤖 COMPLETE PROMPT DEBUG:")
            self.logger.info(f"=" * 100)
            self.logger.info(f"SYSTEM MESSAGE:")
            system_message = "You are an expert municipal zoning analyst. You can analyze zoning maps and determine zoning districts for specific addresses."
            self.logger.info(system_message)
            self.logger.info(f"=" * 100)
            self.logger.info(f"USER PROMPT:")
            self.logger.info(enhanced_prompt)
            self.logger.info(f"=" * 100)
            
            # Step 3: Call LLM with enhanced content
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://bylaws-iq.com",
                "X-Title": "Bylaws IQ - Zoning Analysis"
            }
            
            # Use Google Gemini 2.5 Pro - proven to work with our OpenRouter setup
            model = "google/gemini-2.5-pro"
            self.logger.info(f"🎯 USING MODEL: {model}")
            
            # Define the JSON schema for structured output (per OpenRouter docs)
            zoning_schema = {
                "type": "json_schema",
                "json_schema": {
                    "name": "zoning_analysis",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "zoning_code": {
                                "type": ["string", "null"],
                                "description": "The zoning district code (e.g., 'R-1', 'B-I', 'C-2')"
                            },
                            "zoning_name": {
                                "type": ["string", "null"],
                                "description": "The full name of the zoning district (e.g., 'Business Interstate', 'Residential Single Family')"
                            },
                            "overlays": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "List of overlay districts or special zones (e.g., 'Historic District', 'Groundwater Protection')"
                            }
                        },
                        "required": ["zoning_code", "zoning_name", "overlays"],
                        "additionalProperties": False
                    }
                }
            }
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a zoning analyst. Output only JSON with zoning code, name, and overlays. No explanations or reasoning."
                    },
                    {
                        "role": "user", 
                        "content": enhanced_prompt
                    }
                ],
                "max_tokens": 2000,
                "temperature": 0.1,
                "response_format": zoning_schema,
                "extra_body": {
                    "reasoning": False  # Disable reasoning for faster, direct responses
                }
            }
            
            self.logger.info(f"🌐 API CALL: Sending enhanced prompt to {model}")
            self.logger.info(f"🔧 STRUCTURED OUTPUT: Using JSON schema 'zoning_analysis' with strict validation")
            self.logger.info(f"🎯 OPTIMIZATION: Max tokens=2000, reasoning disabled for direct JSON output")
            
            # Make actual API call
            with httpx.Client(timeout=60) as client:
                response = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    
                    self.logger.info(f"✅ SUCCESS: Analysis completed using {model}")
                    
                    # Log token usage information
                    if 'usage' in result:
                        usage = result['usage']
                        self.logger.info(f"🔢 TOKEN USAGE: {usage.get('prompt_tokens', 0)} prompt + {usage.get('completion_tokens', 0)} completion = {usage.get('total_tokens', 0)} total")
                    
                    # Log finish reason to debug truncation
                    if 'choices' in result and len(result['choices']) > 0:
                        finish_reason = result['choices'][0].get('finish_reason', 'unknown')
                        self.logger.info(f"🏁 FINISH REASON: {finish_reason}")
                    
                    self.logger.info(f"📄 Raw LLM Response: {content}")
                    
                    # Debug: Check if content is empty but there's reasoning
                    if not content or content.strip() == "":
                        # Check if there's reasoning data (O1-style models)
                        message = result['choices'][0]['message']
                        if 'reasoning' in message and message['reasoning']:
                            reasoning_text = message['reasoning']
                            self.logger.warning(f"⚠️ EMPTY CONTENT but found reasoning - extracting zoning info...")
                            self.logger.info(f"🧠 Reasoning Content: {reasoning_text[:500]}...")
                            
                            # Extract zoning info from reasoning text
                            extracted_json = self._extract_zoning_from_reasoning(reasoning_text)
                            if extracted_json:
                                self.logger.info(f"✅ EXTRACTED FROM REASONING: {extracted_json}")
                                self.last_successful_model = model
                                return extracted_json
                        
                        self.logger.error(f"❌ EMPTY RESPONSE: {model} returned empty content")
                        self.logger.error(f"🔍 Full API Response: {result}")
                        return None
                    
                    # Store the successful model for reference
                    self.last_successful_model = model
                    
                    return content
                else:
                    self.logger.error(f"❌ API ERROR: {response.status_code} - {response.text}")
                    return None
            
        except Exception as e:
            self.logger.error(f"❌ REAL ANALYSIS ERROR: {str(e)}", exc_info=True)
            return None
    
    def _extract_zoning_from_reasoning(self, reasoning_text: str) -> Optional[str]:
        """
        Extract zoning information from reasoning text when structured output fails
        """
        try:
            import re
            import json
            
            # Initialize result
            zoning_code = None
            zoning_name = None
            overlays = []
            
            # Extract zoning code patterns like "B-I", "R-1", etc.
            code_patterns = [
                r'\b([A-Z]{1,2}-[A-Z0-9]{1,2})\b',  # B-I, R-1, C-2, etc.
                r'\b([A-Z]{1,3})\s*\(',              # B( or BI( patterns
                r'zoning designation as ([A-Z-0-9]+)',
                r'zoning.*?([A-Z]{1,2}-[A-Z0-9]{1,2})'
            ]
            
            for pattern in code_patterns:
                match = re.search(pattern, reasoning_text, re.IGNORECASE)
                if match:
                    zoning_code = match.group(1)
                    break
            
            # Extract zoning name - look for common patterns
            name_patterns = [
                r'B-I \(([^)]+)\)',                    # B-I (Business Interstate)
                r'([A-Z][a-z]+ [A-Z][a-z]+)',         # Business Interstate
                r'Business Interstate',
                r'Single Family Residential',
                r'Commercial',
                r'Industrial'
            ]
            
            for pattern in name_patterns:
                match = re.search(pattern, reasoning_text, re.IGNORECASE)
                if match:
                    if 'Business Interstate' in reasoning_text:
                        zoning_name = "Business Interstate"
                    else:
                        zoning_name = match.group(1) if match.groups() else match.group(0)
                    break
            
            # Extract overlays
            overlay_patterns = [
                r'TOD overlay',
                r'Transit Oriented Development',
                r'Historic District',
                r'Groundwater Protection',
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+overlay'
            ]
            
            for pattern in overlay_patterns:
                matches = re.finditer(pattern, reasoning_text, re.IGNORECASE)
                for match in matches:
                    if 'TOD' in match.group(0) or 'Transit' in match.group(0):
                        overlays.append("TOD")
                    elif match.groups():
                        overlays.append(match.group(1))
                    else:
                        overlay_text = match.group(0).replace(' overlay', '').strip()
                        if overlay_text not in overlays:
                            overlays.append(overlay_text)
            
            # Remove duplicates
            overlays = list(set(overlays))
            
            # Create JSON response
            result = {
                "zoning_code": zoning_code,
                "zoning_name": zoning_name,
                "overlays": overlays
            }
            
            self.logger.info(f"🔍 EXTRACTED ZONING DATA:")
            self.logger.info(f"   Code: {zoning_code}")
            self.logger.info(f"   Name: {zoning_name}")
            self.logger.info(f"   Overlays: {overlays}")
            
            return json.dumps(result)
            
        except Exception as e:
            self.logger.error(f"❌ REASONING EXTRACTION ERROR: {str(e)}")
            return None
    
    def _fetch_pdf_content(self, pdf_url: str) -> Optional[str]:
        """
        Fetch and extract text content from a PDF URL
        """
        try:
            import httpx
            
            self.logger.info(f"📥 FETCHING PDF: {pdf_url}")
            
            # Download the PDF
            with httpx.Client(timeout=30) as client:
                response = client.get(pdf_url, follow_redirects=True)
                
                if response.status_code != 200:
                    self.logger.error(f"❌ PDF FETCH FAILED: {response.status_code}")
                    return None
                
                pdf_bytes = response.content
                self.logger.info(f"📄 Downloaded PDF: {len(pdf_bytes)} bytes")
                
                # Extract text from PDF
                try:
                    import PyPDF2
                    import io
                    
                    pdf_file = io.BytesIO(pdf_bytes)
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    
                    text_content = ""
                    for page_num, page in enumerate(pdf_reader.pages):
                        page_text = page.extract_text()
                        text_content += f"\n--- PAGE {page_num + 1} ---\n{page_text}\n"
                    
                    self.logger.info(f"📝 EXTRACTED TEXT: {len(text_content)} characters from {len(pdf_reader.pages)} pages")
                    
                    # Debug: Show sample of extracted content
                    if text_content.strip():
                        sample_content = text_content[:500] + "..." if len(text_content) > 500 else text_content
                        self.logger.info(f"📄 PDF CONTENT SAMPLE:")
                        self.logger.info(f"--- START SAMPLE ---")
                        self.logger.info(sample_content)
                        self.logger.info(f"--- END SAMPLE ---")
                        return text_content
                    else:
                        self.logger.warning("⚠️ No text extracted from PDF - might be image-based")
                        return "PDF contains no extractable text - appears to be image-based zoning map"
                        
                except ImportError:
                    self.logger.error("❌ PyPDF2 not available - install with: pip install PyPDF2")
                    return None
                except Exception as e:
                    self.logger.error(f"❌ PDF TEXT EXTRACTION ERROR: {str(e)}")
                    return "PDF text extraction failed - analyzing based on URL only"
                    
        except Exception as e:
            self.logger.error(f"❌ PDF FETCH ERROR: {str(e)}")
            return None
    
    def _agent_select_official_website(self, search_results: List[Dict], city: str, state: str) -> Optional[str]:
        """Use agent to select the best official website from search results"""
        
        self.logger.debug(f"agent.website_selection_start: {len(search_results)} results for {city}, {state}")
        
        # Create simplified search results for efficiency (only URL and title, no content)
        simplified_results = []
        for result in search_results[:8]:
            simplified_results.append({
                "url": result.get("url", ""),
                "title": result.get("title", "")
            })
        
        prompt = f"""Find the official .gov website for {city}, {state} from these search results:

{json.dumps(simplified_results, indent=1)}

Rules:
- MUST be .gov domain
- MUST match {city}, {state}
- Return just the URL or "none"

Answer:"""
        
        try:
            self.logger.info(f"=== LLM SELECTION DEBUG for {city} ===")
            self.logger.debug(f"agent.calling_llm_for_website_selection using {self.classification_model}")
            response = self._call_llm_classification(prompt).strip()
            self.logger.info(f"agent.llm_raw_response: '{response}'")
            
            if response.lower() != "none" and response.startswith("http"):
                self.logger.info(f"agent.llm_selected_url: {response}")
                
                # CRITICAL: Ensure it's a .gov domain
                if ".gov" not in response.lower():
                    self.logger.warning(f"agent.non_gov_rejected: {response} is not a .gov domain")
                    return None
                
                self.logger.info(f"agent.gov_validation_passed: {response}")
                
                # Verify the website exists
                self.logger.info(f"agent.verifying_website_accessibility: {response}")
                verification_result = self._verify_website_exists(response)
                self.logger.info(f"agent.verification_result: {verification_result} for {response}")
                
                if verification_result:
                    self.logger.info(f"agent.website_verified_success: {response}")
                    return response
                else:
                    self.logger.error(f"agent.website_verification_failed: {response} is not accessible")
                    
                    # Debug: Try direct verification with improved headers
                    try:
                        import requests
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        }
                        test_response = requests.head(response, timeout=10, allow_redirects=True, headers=headers)
                        status = test_response.status_code
                        is_valid_status = status in [200, 301, 302, 403]
                        self.logger.info(f"agent.direct_test: {response} returned status {status}, valid: {is_valid_status}")
                    except Exception as test_e:
                        self.logger.error(f"agent.direct_test_failed: {response} - {str(test_e)}")
                        
            else:
                self.logger.warning(f"agent.website_selection_none: Agent returned '{response}' for {city}")
                
                # Check if we have any .gov results the LLM should have picked
                gov_results = [r for r in search_results if '.gov' in r.get('url', '').lower()]
                if gov_results:
                    self.logger.error(f"agent.llm_missed_gov_sites: {len(gov_results)} .gov sites available but LLM returned '{response}'")
                    for gov_site in gov_results:
                        self.logger.error(f"  Missed: {gov_site.get('url', 'N/A')}")
            
            self.logger.info(f"=== END LLM SELECTION DEBUG ===")
            
        except Exception as e:
            self.logger.error(f"agent.website_selection_failed: {str(e)}", exc_info=True)
        
        return None
    
    def _verify_website_exists(self, url: str) -> bool:
        """Verify that a website exists and is accessible"""
        try:
            self.logger.debug(f"verify_website: Testing {url}")
            
            # Use better headers to avoid bot detection
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.head(url, timeout=10, allow_redirects=True, headers=headers)
            status_code = response.status_code
            self.logger.debug(f"verify_website: {url} returned status {status_code}")
            
            # Accept 200 (OK), 403 (Forbidden - site exists but blocking us), 301/302 (redirects)
            valid_codes = [200, 301, 302, 403]
            is_valid = status_code in valid_codes
            
            if not is_valid:
                # Try GET request as fallback for HEAD-blocking sites
                try:
                    get_response = requests.get(url, timeout=10, allow_redirects=True, headers=headers)
                    get_status = get_response.status_code
                    self.logger.debug(f"verify_website: {url} GET returned status {get_status}")
                    is_valid = get_status in valid_codes
                except:
                    pass
            
            self.logger.debug(f"verify_website: {url} validation result: {is_valid}")
            return is_valid
            
        except Exception as e:
            self.logger.debug(f"verify_website: {url} failed - {str(e)}")
            return False
    
    def _agent_explore_website(self, website_url: str, city: str, state: str) -> Optional[str]:
        """
        Use the agent to intelligently explore the municipal website for zoning maps
        """
        with span(self.logger, "agent.explore_website"):
            self.logger.info(f"agent.exploring: {website_url}")
            
            # Get the main page content
            main_content = self._scrape_page_content(website_url)
            if not main_content:
                return None
            
            # Let the agent analyze the main page and plan navigation
            navigation_plan = self._agent_analyze_and_plan(main_content, website_url, city, state)
            
            if not navigation_plan:
                return None
            
            # Execute the navigation plan
            for step in navigation_plan:
                result_url = self._execute_navigation_step(step, website_url)
                if result_url:
                    return result_url
            
            return None
    
    def _scrape_page_content(self, url: str, max_length: int = 8000) -> Optional[str]:
        """Scrape and clean page content for agent analysis"""
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; ZoningAgent/1.0)'
            })
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text and clean it
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Truncate for LLM processing
            if len(text) > max_length:
                text = text[:max_length] + "..."
            
            return text
            
        except Exception as e:
            self.logger.debug(f"scrape.failed: {url} - {str(e)}")
            return None
    
    def _agent_analyze_and_plan(self, page_content: str, website_url: str, city: str, state: str) -> List[Dict[str, Any]]:
        """
        Use the agent to analyze the page content and create a navigation plan
        """
        
        prompt = f"""
You are an expert web navigation agent tasked with finding the official zoning map PDF for {city}, {state}.

You have scraped the main page of their official website: {website_url}

Page content (truncated):
{page_content}

Your task is to analyze this page and create a strategic navigation plan to find the most recent official zoning map PDF.

Look for navigation links, menus, or sections that might contain:
- Planning department/board
- Zoning information
- Documents/Maps/GIS sections  
- Engineering/Public Works departments
- Community Development
- Building/Permits departments

Return a JSON array of navigation steps. Each step should have:
- "action": "visit_link"  
- "target": The relative URL path (e.g., "/planning", "/documents") or full URL
- "reasoning": Brief explanation why this link might lead to zoning maps

Focus ONLY on links that could lead to ZONING MAPS (visual/graphic PDFs), not zoning ordinance text.

If you find direct links to zoning maps or PDFs on the main page, prioritize those.

Example response:
[
  {{
    "action": "visit_link",
    "target": "/planning-board",
    "reasoning": "Planning board typically maintains zoning maps"
  }},
  {{
    "action": "visit_link",
    "target": "/government/departments/planning",
    "reasoning": "Planning department likely has official zoning documents"
  }},
  {{
    "action": "visit_link",
    "target": "/maps-gis",
    "reasoning": "GIS/maps section may contain zoning maps"
  }}
]

Return maximum 4 steps, prioritized by likelihood of success. If no relevant links are found, return an empty array [].
"""
        
        try:
            self.logger.debug(f"agent.calling_llm_for_navigation_plan")
            response = self._call_llm(prompt)
            self.logger.debug(f"agent.navigation_plan_response: {response}")
            
            navigation_plan = json.loads(response)
            
            # Validate the response format
            if isinstance(navigation_plan, list):
                self.logger.debug(f"agent.navigation_plan_parsed: {len(navigation_plan)} steps")
                return navigation_plan[:4]  # Limit to 4 steps
            else:
                self.logger.debug(f"agent.navigation_plan_invalid_format: {type(navigation_plan)}")
            
        except json.JSONDecodeError as e:
            self.logger.error(f"agent.navigation_plan_json_error: {str(e)}")
        except Exception as e:
            self.logger.error(f"agent.plan_failed: {str(e)}", exc_info=True)
        
        # Enhanced fallback navigation plan based on common municipal website patterns
        fallback_paths = [
            {
                "action": "visit_link",
                "target": "/planning-board",
                "reasoning": "Planning board often maintains zoning maps"
            },
            {
                "action": "visit_link",
                "target": "/departments/planning",
                "reasoning": "Planning department typically has zoning documents"
            },
            {
                "action": "visit_link",
                "target": "/government/planning",
                "reasoning": "Government planning section may have maps"
            },
            {
                "action": "visit_link",
                "target": "/maps",
                "reasoning": "Maps section likely contains zoning maps"
            }
        ]
        
        return fallback_paths
    
    def _execute_navigation_step(self, step: Dict[str, Any], base_url: str) -> Optional[str]:
        """Execute a single navigation step and search for zoning maps"""
        
        action = step.get('action')
        target = step.get('target')
        
        if action == "visit_link":
            # Visit the target page
            if target.startswith('/'):
                full_url = urljoin(base_url, target)
            else:
                full_url = target
            
            page_content = self._scrape_page_content(full_url)
            if page_content:
                # Use agent to find zoning map links on this page
                zoning_url = self._agent_find_zoning_links(page_content, full_url)
                if zoning_url:
                    return zoning_url
        
        elif action == "search_page":
            # This would be implemented to search within the current page
            # For now, we'll skip this and rely on visit_link actions
            pass
        
        return None
    
    def _agent_find_zoning_links(self, page_content: str, page_url: str) -> Optional[str]:
        """
        Use the agent to find zoning map links on a specific page
        """
        
        # First, extract all PDF links from the page
        pdf_links = self._extract_pdf_links(page_url)
        
        if not pdf_links:
            self.logger.debug(f"agent.no_pdfs: No PDF links found on {page_url}")
            return None
        
        self.logger.debug(f"agent.found_pdfs: {len(pdf_links)} PDF links on {page_url}")
        
        # Use agent to evaluate which link is most likely the official zoning map
        prompt = f"""
You are evaluating PDF links on a municipal website to find the official zoning map.

Page URL: {page_url}

Available PDF links:
{json.dumps(pdf_links, indent=2)}

Your task is to identify which link is most likely the OFFICIAL ZONING MAP (visual/graphic PDF showing zoning districts).

PRIORITIZE links that contain:
- "zoning map" or "district map" 
- Recent years (2020-2024)
- Words like "official", "current", "adopted"
- File names suggesting maps (not codes/ordinances)

AVOID links that contain:
- "zoning code", "ordinance", "bylaw" (these are text documents)
- "application", "form", "permit"
- "meeting", "minutes", "agenda"
- "proposed", "draft", "hearing"

If multiple good options exist, prefer the most recent year.

Return ONLY the full URL of the best zoning map PDF, or "none" if no suitable map is found.

Response format: Just the URL or "none"
"""
        
        try:
            self.logger.debug(f"agent.calling_llm_for_pdf_analysis")
            response = self._call_llm(prompt).strip()
            self.logger.debug(f"agent.pdf_analysis_response: '{response}'")
            
            if response.lower() != "none" and response.startswith("http"):
                self.logger.info(f"agent.selected_pdf: {response}")
                return response
            else:
                self.logger.debug(f"agent.no_suitable_pdf: Agent response was '{response}'")
            
        except Exception as e:
            self.logger.error(f"agent.link_analysis_failed: {str(e)}", exc_info=True)
        
        return None
    
    def _extract_pdf_links(self, page_url: str) -> List[Dict[str, str]]:
        """Extract all PDF links from a page"""
        
        try:
            response = requests.get(page_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            pdf_links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '.pdf' in href.lower():
                    full_url = urljoin(page_url, href)
                    link_text = link.get_text().strip()
                    
                    pdf_links.append({
                        "url": full_url,
                        "text": link_text,
                        "filename": href.split('/')[-1]
                    })
            
            return pdf_links
            
        except Exception as e:
            self.logger.debug(f"pdf_extraction.failed: {page_url} - {str(e)}")
            return []
    
    def _agent_web_search_analysis(self, city: str, state: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Fallback: Use agent to analyze web search results for zoning maps
        """
        
        with span(self.logger, "agent.web_search_analysis"):
            self.logger.info(f"agent.web_search_fallback: {city}, {state}")
            
            # Try multiple search variations
            search_queries = [
                f'"{city}" {state} "zoning map" filetype:pdf site:.gov',
                f'"{city}" {state} "official zoning map" filetype:pdf',
                f'"{city}" {state} "zoning district map" filetype:pdf site:.gov',
                f'{city} {state} zoning map pdf official'
            ]
            
            all_results = []
            
            for query in search_queries:
                try:
                    self.logger.debug(f"agent.search_query: {query}")
                    results = search.search_documents(query, [".gov"])
                    all_results.extend(results)
                    
                    if len(all_results) >= 10:  # Enough results to analyze
                        break
                        
                except Exception as e:
                    self.logger.debug(f"agent.search_failed: {query} - {str(e)}")
                    continue
            
            if not all_results:
                self.logger.warning(f"agent.no_search_results: No results found for {city}, {state}")
                return None, None
            
            # Remove duplicates based on URL
            unique_results = []
            seen_urls = set()
            for result in all_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    unique_results.append(result)
                    seen_urls.add(url)
            
            self.logger.debug(f"agent.total_search_results: {len(unique_results)} unique results")
            
            # Use agent to analyze and rank the search results
            prompt = f"""
You are evaluating web search results to find the official zoning map for {city}, {state}.

Search results ({len(unique_results[:10])} results shown):
{json.dumps(unique_results[:10], indent=2)}

Your task is to identify the most authoritative and recent official zoning map PDF.

PRIORITIZE results that:
1. Come from official .gov domains
2. Have recent years (2020-2024) in the URL or title
3. Contain "zoning map", "district map" (visual maps)
4. Are from the correct city: {city}
5. Come from planning, engineering, or municipal departments

STRONGLY AVOID results that:
- Are from wrong cities/jurisdictions
- Contain "zoning code", "ordinance", "bylaw" (text documents)
- Are environmental reports, superfund sites, appraisals
- Are draft/proposed/hearing documents
- Are from commercial or non-governmental sites

Return the URL of the BEST official zoning map PDF, or "none" if no suitable map is found.

Response format: Just the URL or "none"
"""
            
            try:
                self.logger.debug(f"agent.calling_llm_for_web_search_analysis")
                response = self._call_llm(prompt).strip()
                self.logger.debug(f"agent.web_search_analysis_response: '{response}'")
                
                if response.lower() != "none" and response.startswith("http"):
                    metadata = self._extract_map_metadata(response, city, state)
                    self.logger.info(f"agent.web_search_success: {response}")
                    return response, metadata
                else:
                    self.logger.debug(f"agent.web_search_no_match: Agent response was '{response}'")
                
            except Exception as e:
                self.logger.error(f"agent.search_analysis_failed: {str(e)}", exc_info=True)
            
            return None, None
    
    def _call_llm(self, prompt: str) -> str:
        """Call the LLM using OpenRouter without forcing JSON format"""
        
        try:
            load_dotenv()
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY not set")
            
            system_message = """You are an expert web navigation agent specializing in finding official municipal zoning maps. You understand the difference between zoning maps (visual/graphic PDFs) and zoning codes/ordinances (text documents). You prioritize official, recent, and authoritative sources."""
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://bylaws-iq.local",
                "X-Title": "ByLaws-IQ Agent",
                "Content-Type": "application/json",
            }
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
            
            payload = {
                "model": self.model,
                "temperature": 0.1,
                "messages": messages,
                # NOTE: No response_format forcing JSON - we want text responses
            }
            
            self.logger.debug(f"llm.call_start: model={self.model}")
            
            import httpx
            with httpx.Client(timeout=60) as client:
                r = client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                r.raise_for_status()
                js = r.json()
            
            response = js["choices"][0]["message"]["content"]
            self.logger.debug(f"llm.call_success: response_length={len(response)}")
            return response
            
        except Exception as e:
            self.logger.error(f"llm.call_failed: {str(e)}", exc_info=True)
            raise e
    
    def _call_llm_classification(self, prompt: str) -> str:
        """Call cheaper LLM for simple classification tasks like website selection"""
        
        try:
            load_dotenv()
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY not set")
            
            # Simplified system message for classification
            system_message = """You are a URL classifier. Select the official government website URL from search results."""
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://bylaws-iq.local",
                "X-Title": "ByLaws-IQ Classification",
                "Content-Type": "application/json",
            }
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
            
            payload = {
                "model": self.classification_model,
                "temperature": 0.0,  # More deterministic for classification
                "messages": messages,
                "max_tokens": 500,  # Allow for JSON array with multiple zoning maps
            }
            
            self.logger.debug(f"llm.classification_call_start: model={self.classification_model}")
            
            import httpx
            with httpx.Client(timeout=30) as client:  # Shorter timeout for simple task
                r = client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                r.raise_for_status()
                js = r.json()
            
            response = js["choices"][0]["message"]["content"]
            self.logger.debug(f"llm.classification_success: response='{response}'")
            return response
            
        except Exception as e:
            self.logger.error(f"llm.classification_failed: {str(e)}", exc_info=True)
            raise e
    
    def _extract_map_metadata(self, pdf_url: str, city: str, state: str) -> Dict[str, Any]:
        """Extract metadata about the zoning map"""
        
        # Try to extract year from URL
        year_match = re.search(r'(\d{4})', pdf_url)
        year = year_match.group(1) if year_match else None
        
        # Determine issuing authority from URL
        if 'ma.gov' in pdf_url.lower():
            authority = f"Town/City of {city}, Massachusetts"
        elif '.gov' in pdf_url.lower():
            authority = f"{city} Municipal Government"
        else:
            authority = f"{city} Planning Department"
        
        return {
            "adoption_date": year,
            "correction_date": year,
            "source_url": pdf_url,
            "issuing_authority": authority,
            "discovery_method": "agentic_search"
        }
    
    def _find_city_in_mma(self, city: str) -> Optional[str]:
        """
        Find a specific city's official website in the MMA directory
        
        Args:
            city: City name to search for
            
        Returns:
            Official website URL for the city, or None if not found
        """
        with span(self.logger, "mma.find_city"):
            self.logger.info(f"mma.searching: Looking for {city} in MMA directory")
            
            try:
                # Fetch the MMA municipal directory page
                mma_url = "https://www.mma.org/members/member-communities/city-and-town-websites/#all"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                
                response = requests.get(mma_url, headers=headers, timeout=30)
                response.raise_for_status()
                
                # Parse the HTML content
                soup = BeautifulSoup(response.content, 'html.parser')
                text_content = soup.get_text()
                
                self.logger.debug(f"mma.fetched: {len(text_content)} characters from MMA directory")
                
                # Normalize the city name for matching
                city_normalized = city.lower().strip()
                city_variations = [
                    city_normalized,
                    city_normalized.replace(' ', ''),
                    city_normalized.replace(' city', '').replace(' town', ''),
                    f"city of {city_normalized}",
                    f"town of {city_normalized}",
                ]
                
                self.logger.debug(f"mma.variations: Searching for {city_variations}")
                
                # Search for the city in the text content - try multiple patterns
                lines = text_content.split('\n')
                
                for line in lines:
                    line_clean = line.strip()
                    
                    # Look for lines with URLs (any domain - no filtering)
                    if '–' in line_clean and ('www.' in line_clean or '.gov' in line_clean or '.us' in line_clean or '.org' in line_clean or '.com' in line_clean):
                        parts = line_clean.split('–')
                        if len(parts) >= 2:
                            name_part = parts[0].strip()
                            url_part = parts[1].strip()
                            
                            # Clean up city name (remove markdown formatting)
                            name_clean = re.sub(r'\*+', '', name_part).strip().lower()
                            
                            # Check if this matches any of our city variations
                            for variation in city_variations:
                                if variation in name_clean or name_clean in variation:
                                    # Extract the URL
                                    url_match = re.search(r'((?:www\.)?[^\s]+\.[a-z]+)', url_part)
                                    if url_match:
                                        url = url_match.group(1)
                                        
                                        # Ensure URL has protocol
                                        if not url.startswith('http'):
                                            url = f"https://{url}"
                                        
                                        self.logger.info(f"mma.match_found: {city} matched '{name_part}' -> {url}")
                                        return url
                
                self.logger.warning(f"mma.not_found: No entry found for {city} in MMA directory")
                return None
                
            except Exception as e:
                self.logger.error(f"mma.search_failed: {str(e)}", exc_info=True)
                return None



# =====================================
# 3. ZONING BYLAWS AGENT (Specialized for Bylaws)
# =====================================

class ZoningBylawsAgent(BaseZoningAgent):
    """
    Specialized agent for zoning bylaws discovery and analysis
    
    Handles:
    - Finding official zoning bylaws documents from municipal websites  
    - Analyzing bylaws to extract specific metrics for zoning districts
    """
    
    def __init__(self):
        super().__init__("zoning_bylaws_agent")

    def find_zoning_bylaws(self, address: str, official_website: str = None, zoning_district: str = None) -> Optional[List[Dict[str, Any]]]:
        """
        Find zoning bylaws PDFs using multiple discovery methods
        
        Method 1: Zoning Board of Appeals search
        Method 2: Planning Board search
        
        Args:
            address (str): Full address to determine jurisdiction
            official_website (str, optional): Official website URL if already discovered (avoids duplicate lookup)
            zoning_district (str, optional): Zoning district if already determined
            
        Returns:
            list: List of zoning bylaws search results or None if discovery fails
        """
        try:
            # Step 1: Parse address to extract city and state
            parts = [part.strip() for part in address.split(',')]
            
            if len(parts) >= 2:
                if len(parts) == 3:
                    city_part = parts[1].strip()
                    state_part = parts[2].strip()
                else:
                    last_part = parts[-1].strip()
                    words = last_part.split()
                    if len(words) >= 2:
                        potential_state = words[-1].upper()
                        if potential_state in ['MA', 'MASSACHUSETTS']:
                            state_part = words[-1]
                            city_part = ' '.join(words[:-1]).strip()
                        else:
                            city_part = last_part
                            state_part = 'MA'
                    else:
                        city_part = last_part
                        state_part = 'MA'
            else:
                self.logger.error("Invalid address format for bylaws search")
                return None
            
            city_part = city_part.strip(' ,')
            state_part = state_part.strip(' ,')
            
            if state_part.upper() in ['MA', 'MASSACHUSETTS']:
                state = 'Massachusetts'
            else:
                state = state_part
            
            self.logger.info(f"🏛️ Starting zoning bylaws search for: {city_part}, {state}")
            
            # Step 2: Use provided official website or find it via MMA lookup
            website_url = official_website
            if website_url:
                self.logger.info(f"♻️ Using provided official website: {website_url}")
            else:
                self.logger.info(f"🔍 No official website provided, performing MMA lookup for {city_part}")
                website_url = self._find_city_in_mma(city_part)
                if not website_url:
                    self.logger.error(f"Could not find official website for {city_part}, {state}")
                    return None
            
            # Step 3: Try multiple discovery methods in sequence
            # Method 1: Zoning Board of Appeals
            self.logger.info("🔍 METHOD 1: Trying Zoning Board of Appeals search")
            try:
                method1_results = self._bylaws_discovery_method_1(website_url, city_part, state)
                if method1_results:
                    self.logger.info(f"✅ Method 1 success: Found {len(method1_results)} bylaws candidates")
                    return method1_results
            except Exception as e:
                self.logger.warning(f"⚠️ Method 1 failed: {str(e)}")
            
            # Method 2: Planning Board search
            self.logger.info("🔍 METHOD 2: Trying Planning Board search (fallback)")
            try:
                method2_results = self._bylaws_discovery_method_2(website_url, city_part, state)
                if method2_results:
                    self.logger.info(f"✅ Method 2 success: Found {len(method2_results)} bylaws candidates")
                    return method2_results
            except Exception as e:
                self.logger.warning(f"⚠️ Method 2 failed: {str(e)}")
            
            self.logger.warning(f"⚠️ All discovery methods failed for {city_part}")
            return []
                
        except Exception as e:
            self.logger.error(f"❌ Zoning bylaws discovery failed for {address}: {str(e)}", exc_info=True)
            return None
    
    def _bylaws_discovery_method_1(self, website_url: str, city: str, state: str) -> List[Dict[str, Any]]:
        """Method 1: Search for Zoning Board of Appeals"""
        try:
            return self._generic_bylaws_search(
                website_url=website_url,
                city=city,
                state=state,
                search_terms=["Zoning Board of Appeals"],
                selection_mode="zboa"  # Exact match preferred, otherwise first partial match
            )
        except Exception as e:
            self.logger.error(f"❌ Method 1 failed: {str(e)}")
            return []
    
    def _bylaws_discovery_method_2(self, website_url: str, city: str, state: str) -> List[Dict[str, Any]]:
        """Method 2: Search for Planning Board"""
        return self._generic_bylaws_search(
            website_url=website_url,
            city=city,
            state=state,
            search_terms=["Planning Board"],
            selection_mode="exact"  # Exact match only
        )
    
    def _generic_bylaws_search(self, website_url: str, city: str, state: str, search_terms: List[str], selection_mode: str) -> List[Dict[str, Any]]:
        """
        Generic bylaws search method that can handle different search terms and selection criteria
        
        Args:
            website_url (str): Official website URL
            city (str): City name
            state (str): State name
            search_terms (List[str]): List of terms to search for
            selection_mode (str): Selection criteria ('exact', 'zboa')
            
        Returns:
            list: List of zoning bylaws search results
        """
        try:
            # Initialize WebDriver if not already done
            if not self.driver:
                self._init_webdriver()
            
            self.logger.info(f"🔍 Searching for zoning bylaws on {website_url}")
            self.logger.info(f"🎯 Search terms: {search_terms}, Selection mode: {selection_mode}")
            
            # Use the generic Selenium search method
            bylaws_candidates = self._selenium_search_with_terms(self.driver, website_url, city, search_terms, selection_mode)
            
            if bylaws_candidates:
                self.logger.info(f"📋 Found {len(bylaws_candidates)} bylaws candidates from search")
                return bylaws_candidates
            else:
                self.logger.warning(f"⚠️ No zoning bylaws candidates found")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Zoning bylaws search failed: {str(e)}", exc_info=True)
            return []
    
    def _selenium_search_with_terms(self, driver: webdriver.Chrome, website_url: str, city: str, search_terms: List[str], selection_mode: str) -> List[Dict[str, Any]]:
        """
        Generic Selenium search method that can handle different search terms and selection criteria
        
        Args:
            driver: Chrome WebDriver instance
            website_url (str): Website to search
            city (str): City name for context
            search_terms (List[str]): List of terms to search for
            selection_mode (str): Selection criteria ('exact', 'zboa')
            
        Returns:
            list: List of search results
        """
        try:
            self.logger.info(f"🌐 Navigating to {website_url} for generic search")
            driver.get(website_url)
            
            # Wait for page to load
            time.sleep(3)
            
            all_results = []
            
            for search_term in search_terms:
                self.logger.info(f"🔍 Trying search term: '{search_term}'")
                
                try:
                    # Find search input (reuse existing logic)
                    search_input = None
                    search_selectors = [
                        'input[type="search"]',
                        'input[name*="search"]', 
                        'input[id*="search"]',
                        'input[placeholder*="search" i]',
                        'input[class*="search"]',
                        '#search', '#Search',
                        '.search-input', '.search-field'
                    ]
                    
                    for selector in search_selectors:
                        try:
                            search_input = driver.find_element(By.CSS_SELECTOR, selector)
                            if search_input.is_displayed():
                                self.logger.info(f"✅ Found search input: {selector}")
                                break
                        except:
                            continue
                    
                    if not search_input:
                        self.logger.warning(f"⚠️ No search input found for term: {search_term}")
                        continue
                    
                    # Enhanced search interaction with multiple strategies
                    success = self._safe_search_interaction(driver, search_input, search_term)
                    if not success:
                        self.logger.warning(f"⚠️ Could not interact with search input for term: {search_term}")
                        continue
                    
                    # Submit search
                    try:
                        search_input.send_keys(Keys.RETURN)
                    except:
                        # Try to find submit button
                        submit_selectors = [
                            'button[type="submit"]',
                            'input[type="submit"]',
                            'button:contains("Search")',
                            '.search-button', '.search-submit'
                        ]
                        
                        for submit_selector in submit_selectors:
                            try:
                                submit_btn = driver.find_element(By.CSS_SELECTOR, submit_selector)
                                submit_btn.click()
                                break
                            except:
                                continue
                    
                    # Wait for results to load
                    time.sleep(8)
                    
                    # Apply selection logic based on mode
                    page_results = self._apply_selection_logic(driver, website_url, search_term, selection_mode)
                    
                    if page_results:
                        all_results.extend(page_results)
                        
                except Exception as e:
                    self.logger.warning(f"⚠️ Search failed for term '{search_term}': {str(e)}")
                    continue
            
            # Remove duplicates and return
            unique_results = []
            seen_urls = set()
            
            for result in all_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            self.logger.info(f"📋 Total unique results: {len(unique_results)}")
            return unique_results
            
        except Exception as e:
            self.logger.error(f"❌ Generic Selenium search failed: {str(e)}", exc_info=True)
            return []

    def _apply_selection_logic(self, driver: webdriver.Chrome, website_url: str, search_term: str, selection_mode: str) -> List[Dict[str, Any]]:
        """
        Apply different selection logic based on the mode
        
        Args:
            driver: Chrome WebDriver instance
            website_url (str): Base website URL
            search_term (str): Search term used
            selection_mode (str): Selection criteria ('exact', 'zboa')
            
        Returns:
            list: Selected results that match the criteria
        """
        try:
            current_url = driver.current_url
            page_source = driver.page_source
            
            print(f"\n{'='*60}")
            print(f"🔍 SEARCH RESULTS FOR: '{search_term}'")
            print(f"📍 URL: {current_url}")
            print(f"🎯 Selection Mode: {selection_mode}")
            print(f"{'='*60}")
            
            # Parse HTML to find links
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse
            
            soup = BeautifulSoup(page_source, 'html.parser')
            base_domain = urlparse(website_url).netloc
            
            # Domain normalization function
            def normalize_domain(domain):
                return domain.replace('www.', '') if domain.startswith('www.') else domain
            
            print(f"\n🔍 APPLYING SELECTION LOGIC:")
            print("-" * 40)
            
            # Find all anchor tags
            all_anchor_tags = soup.find_all('a')
            print(f"📊 Total anchor tags found: {len(all_anchor_tags)}")
            
            # Apply different selection logic based on mode
            if selection_mode == "exact":
                # Exact match only (existing Planning Board logic)
                selected_links = self._select_exact_matches(all_anchor_tags, search_term, website_url, base_domain, normalize_domain)
            elif selection_mode == "zboa":
                # Zoning Board of Appeals logic: exact match preferred, otherwise first partial match
                selected_links = self._select_zboa_matches(all_anchor_tags, search_term, website_url, base_domain, normalize_domain)
            else:
                self.logger.warning(f"Unknown selection mode: {selection_mode}")
                return []
            
            print(f"📊 Selected links: {len(selected_links)}")
            print("-" * 60)
            
            # If we found links, follow them and search for zoning documents
            discovered_documents = []
            if selected_links:
                print(f"\n🌐 FOLLOWING SELECTED LINKS:")
                print("=" * 60)
                
                for i, link in enumerate(selected_links, 1):
                    print(f"\n📍 Following Link {i}: {link['title']}")
                    print(f"🔗 URL: {link['url']}")
                    print("-" * 40)
                    
                    try:
                        # Navigate to the page
                        driver.get(link['url'])
                        time.sleep(5)  # Wait for page to load
                        
                        # Get the raw page source
                        page_source = driver.page_source
                        print(f"📊 Page loaded: {len(page_source)} characters")
                        
                        # Search for zoning-related documents and capture results
                        found_docs = self._search_zoning_documents(driver, page_source, link['url'])
                        if found_docs:
                            discovered_documents.extend(found_docs)
                            print(f"✅ Found {len(found_docs)} zoning documents from this page")
                            # Early termination: Stop processing after finding successful documents
                            print(f"🎉 SUCCESS: Stopping search after finding {len(found_docs)} document(s)")
                            break
                        else:
                            print(f"⚠️ No zoning-related links found on this page")
                            
                    except Exception as e:
                        print(f"❌ Failed to process link {link['url']}: {str(e)}")
                        continue
            
            return discovered_documents
            
        except Exception as e:
            self.logger.error(f"❌ Selection logic failed: {str(e)}", exc_info=True)
            return []

    def _select_exact_matches(self, anchor_tags, search_term: str, website_url: str, base_domain: str, normalize_domain) -> List[Dict[str, Any]]:
        """
        Select links that exactly match the search term (Planning Board logic)
        """
        from urllib.parse import urljoin, urlparse
        exact_links = []
        
        for anchor in anchor_tags:
            href = anchor.get('href')
            text = anchor.get_text(strip=True)
            
            if href and text:
                full_url = urljoin(website_url, href)
                link_domain = urlparse(full_url).netloc
                
                # Normalize domains
                normalized_link_domain = normalize_domain(link_domain)
                normalized_base_domain = normalize_domain(base_domain)
                
                # Check for exact match and same domain
                if (normalized_link_domain == normalized_base_domain and 
                    text.strip().lower() == search_term.lower()):
                    exact_links.append({
                        'title': text,
                        'url': full_url,
                        'href': href
                    })
                    print(f"   ✅ EXACT MATCH: {text} -> {full_url}")
        
        return exact_links

    def _select_zboa_matches(self, anchor_tags, search_term: str, website_url: str, base_domain: str, normalize_domain) -> List[Dict[str, Any]]:
        """
        Select links for Zoning Board of Appeals: exact match preferred, otherwise first partial match
        """
        from urllib.parse import urljoin, urlparse
        exact_matches = []
        partial_matches = []
        search_term_lower = search_term.lower()
        
        for anchor in anchor_tags:
            href = anchor.get('href')
            text = anchor.get_text(strip=True)
            
            if href and text:
                full_url = urljoin(website_url, href)
                link_domain = urlparse(full_url).netloc
                
                # Normalize domains
                normalized_link_domain = normalize_domain(link_domain)
                normalized_base_domain = normalize_domain(base_domain)
                
                # Only consider same-domain links
                if normalized_link_domain == normalized_base_domain:
                    text_lower = text.strip().lower()
                    
                    # Check for exact match
                    if text_lower == search_term_lower:
                        exact_matches.append({
                            'title': text,
                            'url': full_url,
                            'href': href
                        })
                        print(f"   ✅ EXACT MATCH: {text} -> {full_url}")
                    
                    # Check for partial match (contains the whole phrase)
                    elif search_term_lower in text_lower:
                        partial_matches.append({
                            'title': text,
                            'url': full_url,
                            'href': href
                        })
                        print(f"   🔸 PARTIAL MATCH: {text} -> {full_url}")
        
        # Return exact matches if found, otherwise return first partial match
        if exact_matches:
            print(f"   🎯 Using {len(exact_matches)} exact match(es)")
            return exact_matches
        elif partial_matches:
            print(f"   🔸 No exact matches, using first partial match from {len(partial_matches)} found")
            return [partial_matches[0]]  # Return only the first partial match
        else:
            print(f"   ❌ No matches found for '{search_term}'")
            return []

    def _safe_search_interaction(self, driver: webdriver.Chrome, search_input, search_term: str) -> bool:
        """
        Safely interact with search input using multiple strategies to handle common issues
        
        Args:
            driver: Chrome WebDriver instance
            search_input: The search input element
            search_term: Term to search for
            
        Returns:
            bool: True if interaction succeeded, False otherwise
        """
        strategies = [
            self._strategy_basic_interaction,
            self._strategy_click_then_type,
            self._strategy_dismiss_overlays,
            self._strategy_scroll_into_view,
            self._strategy_javascript_interaction
        ]
        
        for i, strategy in enumerate(strategies, 1):
            try:
                self.logger.info(f"🔄 Trying interaction strategy {i}/{len(strategies)}")
                if strategy(driver, search_input, search_term):
                    self.logger.info(f"✅ Strategy {i} succeeded")
                    return True
            except Exception as e:
                self.logger.warning(f"⚠️ Strategy {i} failed: {str(e)}")
                continue
        
        self.logger.error("❌ All search interaction strategies failed")
        return False

    def _strategy_basic_interaction(self, driver: webdriver.Chrome, search_input, search_term: str) -> bool:
        """Strategy 1: Basic clear and type (original method)"""
        search_input.clear()
        search_input.send_keys(search_term)
        time.sleep(1)
        return True

    def _strategy_click_then_type(self, driver: webdriver.Chrome, search_input, search_term: str) -> bool:
        """Strategy 2: Click to focus, then type"""
        search_input.click()
        time.sleep(0.5)
        search_input.clear()
        search_input.send_keys(search_term)
        time.sleep(1)
        return True

    def _strategy_dismiss_overlays(self, driver: webdriver.Chrome, search_input, search_term: str) -> bool:
        """Strategy 3: Dismiss common overlays, then interact"""
        # Common overlay dismissal patterns
        overlay_selectors = [
            '[class*="cookie"] button[class*="accept"]',
            '[class*="cookie"] button[class*="agree"]',
            '[class*="consent"] button',
            '.modal-close', '.popup-close',
            '[aria-label*="close"]',
            'button:contains("Accept")',
            'button:contains("OK")',
            'button:contains("Continue")'
        ]
        
        for selector in overlay_selectors:
            try:
                overlay = driver.find_element(By.CSS_SELECTOR, selector)
                if overlay.is_displayed():
                    overlay.click()
                    time.sleep(1)
                    self.logger.info(f"✅ Dismissed overlay: {selector}")
                    break
            except:
                continue
        
        # Try basic interaction after dismissing overlays
        search_input.click()
        search_input.clear()
        search_input.send_keys(search_term)
        time.sleep(1)
        return True

    def _strategy_scroll_into_view(self, driver: webdriver.Chrome, search_input, search_term: str) -> bool:
        """Strategy 4: Scroll element into view, then interact"""
        driver.execute_script("arguments[0].scrollIntoView(true);", search_input)
        time.sleep(1)
        search_input.click()
        search_input.clear()
        search_input.send_keys(search_term)
        time.sleep(1)
        return True

    def _strategy_javascript_interaction(self, driver: webdriver.Chrome, search_input, search_term: str) -> bool:
        """Strategy 5: Use JavaScript to set value directly"""
        # Clear and set value via JavaScript
        driver.execute_script("arguments[0].value = '';", search_input)
        driver.execute_script(f"arguments[0].value = '{search_term}';", search_input)
        
        # Trigger input events that JavaScript frameworks expect
        driver.execute_script("""
            var element = arguments[0];
            var event = new Event('input', { bubbles: true });
            element.dispatchEvent(event);
            
            var changeEvent = new Event('change', { bubbles: true });
            element.dispatchEvent(changeEvent);
        """, search_input)
        
        time.sleep(1)
        return True

    def _search_zoning_documents(self, driver: webdriver.Chrome, page_source: str, current_url: str) -> List[Dict[str, Any]]:
        """
        Search for zoning-related documents on a page and handle both page links and PDF downloads
        
        Args:
            driver: Chrome WebDriver instance
            page_source (str): HTML content of the page
            current_url (str): Current page URL
            
        Returns:
            List[Dict[str, Any]]: List of found zoning documents with metadata
        """
        try:
            print(f"\n🔍 SEARCHING FOR ZONING DOCUMENTS ON: {current_url}")
            print("=" * 60)
            
            # Define zoning-related keywords to search for
            zoning_keywords = [
                "zoning code",
                "zoning bylaw", 
                "zoning by-law",
                "zoning bylaws",  # Added for Fairhaven-style buttons
                "zoning ordinance",
                "unified development ordinance (udo)",
                "unified development ordinance", 
                "form-based code",
                "zoning regulation",  # lowercase version
                "Zoning Regulation",  # Added for Franklin-style buttons (capitalized, singular)
                "zoning regulations",
                "zoning act",
                "zoning law"
            ]
            
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse
            import re
            
            soup = BeautifulSoup(page_source, 'html.parser')
            base_domain = urlparse(current_url).netloc
            
            found_elements = []
            
            # Enhanced search for elements containing zoning keywords
            for keyword in zoning_keywords:
                print(f"\n🔍 Searching for: '{keyword}'")
                
                # STRATEGY 1: Find text elements containing the keyword (original method)
                text_elements = soup.find_all(text=re.compile(keyword, re.IGNORECASE))
                print(f"   📝 Found {len(text_elements)} text matches")
                
                for element in text_elements:
                    parent = element.parent
                    
                    # Check if it's inside a link
                    link_parent = parent.find_parent('a')
                    if link_parent and link_parent.get('href'):
                        href = link_parent.get('href')
                        full_url = urljoin(current_url, href)
                        link_domain = urlparse(full_url).netloc
                        
                        # Accept internal links OR ecode360 external links
                        is_internal = self._normalize_domain(link_domain) == self._normalize_domain(base_domain)
                        is_ecode360 = self._is_ecode360_link(full_url)
                        
                        if is_internal or is_ecode360:
                            element_info = {
                                'keyword': keyword,
                                'text': element.strip()[:100],
                                'link_text': link_parent.get_text(strip=True),
                                'url': full_url,
                                'href': href,
                                'is_pdf': self._is_pdf_link(full_url, link_parent.get_text())
                            }
                            found_elements.append(element_info)
                            
                            link_type = "internal" if is_internal else "ecode360 external"
                            print(f"  ✅ Found in link ({link_type}): '{link_parent.get_text(strip=True)[:60]}'")
                            print(f"     URL: {full_url}")
                            print(f"     PDF: {'Yes' if element_info['is_pdf'] else 'No'}")
                        else:
                            print(f"  ⚠️ Rejected external link: '{link_parent.get_text(strip=True)[:30]}' -> {full_url}")
                
                # STRATEGY 2: Direct search for clickable elements (buttons, divs, etc.)
                print(f"   🔍 Strategy 2: Searching for buttons/clickable elements")
                
                # Find all potentially clickable elements containing the keyword
                clickable_selectors = ['a', 'button', 'div', 'span', 'input']
                
                for selector in clickable_selectors:
                    elements = soup.find_all(selector, string=re.compile(keyword, re.IGNORECASE))
                    
                    if elements:
                        print(f"     📍 Found {len(elements)} {selector} elements with keyword")
                    
                    for elem in elements:
                        elem_text = elem.get_text(strip=True)
                        print(f"     🔍 Checking {selector}: '{elem_text}'")
                        
                        # For anchor tags
                        if elem.name == 'a' and elem.get('href'):
                            href = elem.get('href')
                            full_url = urljoin(current_url, href)
                            link_domain = urlparse(full_url).netloc
                            
                            # Accept internal links OR ecode360 external links
                            is_internal = self._normalize_domain(link_domain) == self._normalize_domain(base_domain)
                            is_ecode360 = self._is_ecode360_link(full_url)
                            
                            if is_internal or is_ecode360:
                                element_info = {
                                    'keyword': keyword,
                                    'text': elem_text[:100],
                                    'link_text': elem_text,
                                    'url': full_url,
                                    'href': href,
                                    'is_pdf': self._is_pdf_link(full_url, elem_text)
                                }
                                found_elements.append(element_info)
                                link_type = "internal" if is_internal else "ecode360 external"
                                print(f"     ✅ Found direct link ({link_type}): '{elem_text[:60]}' -> {full_url}")
                            else:
                                print(f"     ⚠️ Rejected external link: '{elem_text[:30]}' -> {full_url}")
                        
                        # For buttons and other clickable elements
                        elif elem.name in ['button', 'div', 'span']:
                            # Check for various click attributes
                            onclick = elem.get('onclick', '')
                            data_href = elem.get('data-href', '')
                            data_url = elem.get('data-url', '')
                            
                            url = data_href or data_url
                            
                            # Extract URL from onclick if present
                            if onclick and not url:
                                # Look for common onclick patterns
                                onclick_patterns = [
                                    r"window\.location\s*=\s*['\"]([^'\"]+)['\"]",
                                    r"location\.href\s*=\s*['\"]([^'\"]+)['\"]",
                                    r"window\.open\s*\(\s*['\"]([^'\"]+)['\"]",
                                    r"['\"]([^'\"]*(?:\.pdf|ecode360|bylaws)[^'\"]*)['\"]"
                                ]
                                
                                for pattern in onclick_patterns:
                                    match = re.search(pattern, onclick, re.IGNORECASE)
                                    if match:
                                        url = match.group(1)
                                        print(f"     🔍 Extracted URL from onclick: {url}")
                                        break
                            
                            if url and (url.startswith('http') or url.startswith('/')):
                                full_url = urljoin(current_url, url)
                                element_info = {
                                    'keyword': keyword,
                                    'text': elem_text[:100],
                                    'link_text': elem_text,
                                    'url': full_url,
                                    'href': url,
                                    'is_pdf': self._is_pdf_link(full_url, elem_text)
                                }
                                found_elements.append(element_info)
                                print(f"     ✅ Found clickable element: '{elem_text[:60]}' -> {full_url}")
                            else:
                                print(f"     ⚠️ Clickable element '{elem_text[:30]}' has no extractable URL")
                                # Debug: print the element to see what we're missing
                                print(f"     🔧 Debug - Element: {str(elem)[:200]}...")
            
            print(f"\n📊 Total elements found across all strategies: {len(found_elements)}")
            
            # Remove duplicates based on URL
            unique_elements = []
            seen_urls = set()
            for element in found_elements:
                if element['url'] not in seen_urls:
                    seen_urls.add(element['url'])
                    unique_elements.append(element)
            
            print(f"\n📊 Found {len(unique_elements)} unique zoning-related links")
            
            downloaded_documents = []
            
            if unique_elements:
                print(f"\n📋 PROCESSING ZONING LINKS WITH PRIORITY:")
                print("-" * 40)
                
                # Separate elements by priority
                pdf_elements = [e for e in unique_elements if e['is_pdf']]
                ecode360_elements = [e for e in unique_elements if not e['is_pdf'] and self._is_ecode360_link(e['url'])]
                page_elements = [e for e in unique_elements if not e['is_pdf'] and not self._is_ecode360_link(e['url'])]
                
                print(f"📊 Found: {len(pdf_elements)} PDFs, {len(ecode360_elements)} ecode360 links, {len(page_elements)} page links")
                
                # PRIORITY 1: Process PDF documents first
                if pdf_elements:
                    print(f"\n🎯 PRIORITY 1: Processing {len(pdf_elements)} PDF document(s)")
                    print("=" * 50)
                    
                    for i, element in enumerate(pdf_elements, 1):
                        print(f"\n📄 PDF {i}: {element['link_text'][:60]}")
                        print(f"   Keyword: {element['keyword']}")
                        print(f"   URL: {element['url']}")
                        print(f"   📥 DOWNLOADING PDF...")
                        
                        success = self._download_pdf(element['url'], element['link_text'], current_url)
                        if success:
                            downloaded_documents.append({
                                'title': element['link_text'],
                                'url': element['url'],
                                'keyword': element['keyword'],
                                'type': 'pdf',
                                'source_page': current_url
                            })
                
                # PRIORITY 2: If no PDFs found, process ecode360 links
                if not downloaded_documents and ecode360_elements:
                    print(f"\n🎯 PRIORITY 2: No PDFs found, processing {len(ecode360_elements)} ecode360 link(s)")
                    print("=" * 50)
                    
                    for i, element in enumerate(ecode360_elements, 1):
                        print(f"\n🌐 ecode360 {i}: {element['link_text'][:60]}")
                        print(f"   Keyword: {element['keyword']}")
                        print(f"   URL: {element['url']}")
                        print(f"   🌐 ECODE360 LINK DETECTED...")
                        
                        # Use fresh WebDriver methodology like Method 1
                        ecode360_element = {'href': element['url'], 'text': element['link_text']}
                        ecode_docs = self._apply_fresh_webdriver_ecode360_methodology(ecode360_element, current_url)
                        if ecode_docs:
                            downloaded_documents.extend(ecode_docs)
                
                # PRIORITY 3: If no PDFs or ecode360 success, follow page links
                if not downloaded_documents and page_elements:
                    print(f"\n🎯 PRIORITY 3: No direct documents found, following {len(page_elements)} page link(s)")
                    print("=" * 50)
                    
                    zoning_keywords_for_nested = [
                        "zoning code",
                        "zoning bylaw", 
                        "zoning by-law",
                        "zoning bylaws",
                        "zoning ordinance",
                        "unified development ordinance (udo)",
                        "unified development ordinance", 
                        "form-based code",
                        "zoning regulation",
                        "Zoning Regulation",
                        "zoning regulations",
                        "zoning act",
                        "zoning law"
                    ]
                    
                    for i, element in enumerate(page_elements, 1):
                        print(f"\n🌐 Page {i}: {element['link_text'][:60]}")
                        print(f"   Keyword: {element['keyword']}")
                        print(f"   URL: {element['url']}")
                        print(f"   🌐 FOLLOWING PAGE LINK...")
                        
                        nested_docs = self._follow_page_for_pdfs(driver, element['url'], zoning_keywords_for_nested)
                        if nested_docs:
                            downloaded_documents.extend(nested_docs)
                            # Stop after first successful page link to avoid duplicates
                            break
                
                # Summary
                if downloaded_documents:
                    print(f"\n✅ PRIORITY PROCESSING COMPLETE:")
                    print(f"📊 Successfully processed {len(downloaded_documents)} document(s)")
                    for doc in downloaded_documents:
                        doc_type = doc.get('type', 'unknown')
                        print(f"   - {doc['title']} ({doc_type})")
                else:
                    print(f"\n⚠️ PRIORITY PROCESSING COMPLETE: No documents found")
            else:
                print(f"\n⚠️ No zoning-related links found on this page")
            
            return downloaded_documents
                
        except Exception as e:
            print(f"❌ Error searching for zoning documents: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain by removing www prefix"""
        return domain.replace('www.', '') if domain.startswith('www.') else domain

    def _is_ecode360_link(self, url: str) -> bool:
        """Check if a URL points to ecode360.com"""
        return 'ecode360.com' in url.lower()
    
    def _is_pdf_link(self, url: str, link_text: str) -> bool:
        """Check if a URL or link text indicates a PDF"""
        url_lower = url.lower()
        text_lower = link_text.lower()
        
        # More comprehensive PDF detection
        pdf_indicators = [
            # Direct URL indicators
            url_lower.endswith('.pdf'),
            '.pdf' in url_lower,
            'pdf' in url_lower,
            'document' in url_lower,
            'download' in url_lower,
            'wp-content/uploads' in url_lower,  # WordPress uploads often contain PDFs
            
            # Text indicators
            'pdf' in text_lower,
            'download' in text_lower,
            'complete' in text_lower,  # "Complete" often indicates full document
            
            # Zoning-specific indicators for comprehensive documents
            ('zoning code complete' in text_lower),
            ('zoning ordinance complete' in text_lower),
            ('current version' in text_lower),
            ('latest version' in text_lower),
            ('full document' in text_lower)
        ]
        
        is_pdf = any(pdf_indicators)
        
        # Debug logging for PDF detection
        if any(['zoning' in text_lower, 'ordinance' in text_lower, 'code' in text_lower]):
            print(f"      🔍 PDF Detection Debug:")
            print(f"         URL: {url}")
            print(f"         Text: {link_text}")
            print(f"         Ends with .pdf: {url_lower.endswith('.pdf')}")
            print(f"         Contains .pdf: {'.pdf' in url_lower}")
            print(f"         wp-content/uploads: {'wp-content/uploads' in url_lower}")
            print(f"         'complete' in text: {'complete' in text_lower}")
            print(f"         Final decision: {is_pdf}")
        
        return is_pdf

    def _download_pdf(self, pdf_url: str, pdf_name: str, source_page: str = None) -> bool:
        """Download a PDF file and return success status, with duplicate detection"""
        try:
            import os
            import requests
            
            # Check if this PDF has already been downloaded
            if pdf_url in self.downloaded_pdfs:
                existing_info = self.downloaded_pdfs[pdf_url]
                existing_filename = existing_info['filename']
                existing_sources = existing_info['source_pages']
                
                print(f"📄 PDF Already Downloaded: {pdf_name[:50]}")
                print(f"🔗 URL: {pdf_url}")
                print(f"📁 Previously saved as: {existing_filename}")
                print(f"📍 Originally found on: {existing_sources[0]}")
                
                if source_page and source_page not in existing_sources:
                    existing_sources.append(source_page)
                    print(f"📍 Also found on: {source_page}")
                    print(f"✅ PDF exists on {len(existing_sources)} different pages")
                else:
                    print(f"✅ Same PDF found again (no duplicate download needed)")
                
                return True
            
            print(f"📥 Downloading PDF: {pdf_name[:50]}")
            print(f"🔗 URL: {pdf_url}")
            
            # Create downloads directory
            download_dir = "pdf_downloads"
            os.makedirs(download_dir, exist_ok=True)
            
            # Clean filename
            safe_name = "".join(c for c in pdf_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_name = safe_name[:50]  # Limit length
            if not safe_name.endswith('.pdf'):
                safe_name += '.pdf'
            
            file_path = os.path.join(download_dir, safe_name)
            
            # Download the file
            response = requests.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Downloaded to: {file_path}")
            print(f"📊 File size: {len(response.content)} bytes")
            
            # Track this download
            source_pages = [source_page] if source_page else []
            self.downloaded_pdfs[pdf_url] = {
                'filename': file_path,
                'source_pages': source_pages
            }
            
            return True
            
        except Exception as e:
            print(f"❌ Download failed: {str(e)}")
            return False

    def _follow_page_for_pdfs(self, driver: webdriver.Chrome, page_url: str, zoning_keywords: list) -> List[Dict[str, Any]]:
        """Follow a page link and search specifically for PDF links, returning downloaded documents"""
        try:
            print(f"🌐 Navigating to: {page_url}")
            driver.get(page_url)
            time.sleep(3)
            
            page_source = driver.page_source
            
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse
            import re
            
            soup = BeautifulSoup(page_source, 'html.parser')
            
            print(f"\n🔍 SEARCHING FOR ZONING PDFs ON: {page_url}")
            print("-" * 40)
            
            # First, find ALL links on the page for debugging
            all_links = soup.find_all('a', href=True)
            print(f"📊 Total links found on page: {len(all_links)}")
            
            pdf_links = []
            potential_links = []
            
            # Check every link for zoning keywords and PDF indicators
            for i, link in enumerate(all_links):
                href = link.get('href')
                link_text = link.get_text(strip=True)
                full_url = urljoin(page_url, href)
                
                if not href or not link_text:
                    continue
                    
                # Check if link contains any zoning keywords
                contains_zoning_keyword = False
                matched_keyword = None
                
                for keyword in zoning_keywords:
                    if re.search(keyword, link_text, re.IGNORECASE):
                        contains_zoning_keyword = True
                        matched_keyword = keyword
                        break
                
                if contains_zoning_keyword:
                    potential_links.append({
                        'text': link_text,
                        'url': full_url,
                        'keyword': matched_keyword,
                        'is_pdf': self._is_pdf_link(full_url, link_text)
                    })
                    
                    print(f"   🔍 Found zoning link: '{link_text[:60]}'")
                    print(f"      Keyword: {matched_keyword}")
                    print(f"      URL: {full_url}")
                    print(f"      PDF: {'Yes' if self._is_pdf_link(full_url, link_text) else 'No'}")
                    print()
            
            print(f"📊 Found {len(potential_links)} potential zoning links")
            
            # Apply priority processing to nested pages as well
            downloaded_documents = []
            
            if potential_links:
                # Separate by priority (same as main logic)
                pdf_links = [link for link in potential_links if link['is_pdf']]
                ecode360_links = [link for link in potential_links if not link['is_pdf'] and self._is_ecode360_link(link['url'])]
                
                print(f"📊 Nested page priority breakdown: {len(pdf_links)} PDFs, {len(ecode360_links)} ecode360 links")
                
                # PRIORITY 1: Process PDFs first
                if pdf_links:
                    print(f"\n🎯 NESTED PRIORITY 1: Processing {len(pdf_links)} PDF(s)")
                    print("=" * 40)
                    
                    for link in pdf_links:
                        print(f"   ✅ Confirmed PDF: '{link['text'][:50]}'")
                        print(f"      URL: {link['url']}")
                    
                    if len(pdf_links) == 1:
                        # Only one PDF found, download it directly
                        print(f"\n📥 DOWNLOADING SINGLE ZONING PDF:")
                        success = self._download_pdf(pdf_links[0]['url'], pdf_links[0]['text'], page_url)
                        if success:
                            downloaded_documents.append({
                                'title': pdf_links[0]['text'],
                                'url': pdf_links[0]['url'],
                                'keyword': pdf_links[0]['keyword'],
                                'type': 'pdf',
                                'source_page': page_url
                            })
                    else:
                        # Multiple PDFs found, use LLM to select the most recent
                        print(f"\n🤖 MULTIPLE PDFs FOUND ({len(pdf_links)}), USING LLM TO SELECT MOST RECENT:")
                        selected_pdf = self._select_most_recent_pdf(pdf_links)
                        
                        if selected_pdf:
                            print(f"\n📥 DOWNLOADING SELECTED PDF:")
                            print(f"   ✅ Selected: '{selected_pdf['text']}'")
                            print(f"   📅 Reason: Most recent version identified by LLM")
                            success = self._download_pdf(selected_pdf['url'], selected_pdf['text'], page_url)
                            if success:
                                downloaded_documents.append({
                                    'title': selected_pdf['text'],
                                    'url': selected_pdf['url'],
                                    'keyword': selected_pdf.get('keyword', 'selected_by_llm'),
                                    'type': 'pdf',
                                    'source_page': page_url
                                })
                        else:
                            print(f"\n❌ LLM selection failed, downloading the first PDF as fallback:")
                            success = self._download_pdf(pdf_links[0]['url'], pdf_links[0]['text'], page_url)
                            if success:
                                downloaded_documents.append({
                                    'title': pdf_links[0]['text'],
                                    'url': pdf_links[0]['url'],
                                    'keyword': pdf_links[0]['keyword'],
                                    'type': 'pdf',
                                    'source_page': page_url
                                })
                
                # PRIORITY 2: If no PDFs found, process ecode360 links
                elif ecode360_links:
                    print(f"\n🎯 NESTED PRIORITY 2: No PDFs found, processing {len(ecode360_links)} ecode360 link(s)")
                    print("=" * 40)
                    
                    for ecode_link in ecode360_links:
                        print(f"🌐 ECODE360 LINK DETECTED: '{ecode_link['text'][:50]}'")
                        # Use fresh WebDriver methodology like Method 1
                        ecode360_element = {'href': ecode_link['url'], 'text': ecode_link['text']}
                        ecode_docs = self._apply_fresh_webdriver_ecode360_methodology(ecode360_element, page_url)
                        if ecode_docs:
                            downloaded_documents.extend(ecode_docs)
                            break  # Stop after first successful ecode360 processing
                
                else:
                    print(f"\n⚠️ No direct zoning documents (PDFs or ecode360) found on this nested page")
                    print(f"📋 Found {len(potential_links)} zoning links but none were PDFs or ecode360:")
                    for link in potential_links:
                        print(f"   - '{link['text'][:50]}' -> {link['url']}")
            else:
                print(f"\n⚠️ No zoning-related links found on this nested page")
            
            return downloaded_documents
                
        except Exception as e:
            print(f"❌ Error following page link: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def _select_most_recent_pdf(self, pdf_links: list) -> dict:
        """
        Use LLM to select the most recent PDF from multiple candidates
        
        Args:
            pdf_links (list): List of PDF link dictionaries
            
        Returns:
            dict: Selected PDF link dictionary or None if selection fails
        """
        try:
            print(f"\n🤖 ANALYZING {len(pdf_links)} PDFs TO FIND MOST RECENT:")
            print("-" * 50)
            
            # Prepare the candidate list for LLM analysis
            candidates_text = "Available zoning PDFs:\n\n"
            for i, pdf in enumerate(pdf_links, 1):
                candidates_text += f"{i}. {pdf['text']}\n"
                candidates_text += f"   URL: {pdf['url']}\n\n"
            
            # Create prompt for LLM analysis
            prompt = f"""You are analyzing multiple zoning code PDFs to identify the most recent version.

{candidates_text}

Please analyze the titles and dates to identify which PDF represents the MOST RECENT version of the zoning code.

Look for:
- Date patterns in titles (e.g. "as of 8-4-2025", "as of 4-10-2024")
- Version indicators
- "Complete" or "Current" keywords

Return ONLY a JSON object with:
{{
  "selected_number": <number of the most recent PDF (1-{len(pdf_links)})>,
  "selected_title": "<exact title of selected PDF>",
  "reasoning": "<brief explanation of why this is the most recent>"
}}

Example:
{{
  "selected_number": 1,
  "selected_title": "Woburn Zoning Code Complete as of 8-4-2025",
  "reasoning": "Contains the most recent date (August 4, 2025)"
}}"""

            print(f"🤖 Sending {len(candidates_text)} characters to LLM for analysis...")
            
            # Call LLM using existing classification method
            response = self._call_llm_classification_for_selection(prompt)
            
            if response:
                print(f"🤖 LLM Response: {response}")
                
                # Parse JSON response
                import json
                import re
                
                # Handle potential markdown wrapper
                if '```json' in response:
                    json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                    if json_match:
                        response = json_match.group(1)
                
                try:
                    result = json.loads(response)
                    
                    selected_number = result.get('selected_number')
                    selected_title = result.get('selected_title', '')
                    reasoning = result.get('reasoning', '')
                    
                    if selected_number and 1 <= selected_number <= len(pdf_links):
                        selected_pdf = pdf_links[selected_number - 1]
                        
                        print(f"✅ LLM Selection:")
                        print(f"   📄 PDF #{selected_number}: {selected_title}")
                        print(f"   💭 Reasoning: {reasoning}")
                        print(f"   🔗 URL: {selected_pdf['url']}")
                        
                        return selected_pdf
                    else:
                        print(f"❌ Invalid selection number: {selected_number}")
                        return None
                        
                except json.JSONDecodeError as je:
                    print(f"❌ Failed to parse LLM JSON response: {str(je)}")
                    return None
            else:
                print("❌ No response from LLM")
                return None
                
        except Exception as e:
            print(f"❌ Error in LLM PDF selection: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def _call_llm_classification_for_selection(self, prompt: str) -> str:
        """Call LLM for PDF selection using gemini-1.5-flash with structured outputs"""
        try:
            import requests
            import os
            from dotenv import load_dotenv
            
            load_dotenv()
            api_key = os.getenv('OPENROUTER_API_KEY')
            
            if not api_key:
                self.logger.error("OPENROUTER_API_KEY not found in environment")
                return None
            
            url = "https://openrouter.ai/api/v1/chat/completions"
            
            # Define JSON Schema for structured outputs (per OpenRouter docs)
            json_schema = {
                "name": "pdf_selection",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "selected_number": {
                            "type": "integer",
                            "description": "The number of the most recent PDF (starting from 1)",
                            "minimum": 1
                        },
                        "selected_title": {
                            "type": "string",
                            "description": "The exact title of the selected PDF"
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Brief explanation of why this PDF is the most recent"
                        }
                    },
                    "required": ["selected_number", "selected_title", "reasoning"],
                    "additionalProperties": False
                }
            }
            
            payload = {
                "model": "google/gemini-flash-1.5",
                "messages": [
                    {
                        "role": "system", 
                        "content": "You are a document analyst specializing in identifying the most recent versions of municipal documents. Analyze the provided documents and return your selection in the specified JSON format."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "max_tokens": 300,
                "temperature": 0.1,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": json_schema
                }
            }
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            self.logger.debug(f"🤖 LLM selection request with structured outputs: {len(prompt)} chars")
            print(f"🤖 Using OpenRouter Structured Outputs for reliable JSON response")
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].strip()
                self.logger.debug(f"🤖 LLM structured response: {content}")
                print(f"✅ Received structured JSON response from LLM")
                return content
            else:
                self.logger.error("Invalid LLM response structure")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ LLM structured outputs call failed: {str(e)}")
            print(f"❌ Structured outputs failed, attempting fallback...")
            
            # Fallback to regular JSON prompting if structured outputs not supported
            return self._call_llm_fallback_selection(prompt)

    def _call_llm_fallback_selection(self, prompt: str) -> str:
        """Fallback LLM call without structured outputs"""
        try:
            import requests
            import os
            from dotenv import load_dotenv
            
            load_dotenv()
            api_key = os.getenv('OPENROUTER_API_KEY')
            
            url = "https://openrouter.ai/api/v1/chat/completions"
            
            payload = {
                "model": "google/gemini-flash-1.5",
                "messages": [
                    {
                        "role": "system", 
                        "content": "You are a document analyst specializing in identifying the most recent versions of municipal documents. Respond only with valid JSON."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "max_tokens": 300,
                "temperature": 0.1
            }
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            print(f"🔄 Using fallback JSON prompting method")
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].strip()
                return content
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"❌ LLM fallback call failed: {str(e)}")
            return None

    def _apply_fresh_webdriver_ecode360_methodology(self, ecode360_element: Dict[str, Any], source_page: str) -> List[Dict[str, Any]]:
        """
        Apply ecode360 methodology with fresh WebDriver (enhanced processing approach)
        
        This uses an optimal approach for ecode360 processing:
        1. Initialize fresh WebDriver with clean session
        2. Navigate directly to ecode360 page
        3. Apply ecode360 handler methodology
        """
        fresh_driver = None
        try:
            print(f"\n🧪 ENHANCED METHODOLOGY: Fresh WebDriver for ecode360")
            print("=" * 70)
            
            ecode_url = ecode360_element['href']
            link_text = ecode360_element['text']
            
            print(f"📍 Processing: {ecode_url}")
            print(f"📝 Link text: {link_text}")
            
            # Initialize fresh WebDriver (enhanced processing approach)
            print(f"🔧 Initializing fresh WebDriver for clean session...")
            
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            
            # Use same initialization approach as main driver
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            
            try:
                # Try ChromeDriverManager first
                service = Service(ChromeDriverManager().install())
                fresh_driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                print(f"⚠️ ChromeDriverManager failed, trying system Chrome...")
                # Fallback to system Chrome
                chrome_paths = [
                    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                    '/usr/bin/google-chrome',
                    '/usr/local/bin/google-chrome'
                ]
                
                for chrome_path in chrome_paths:
                    if os.path.exists(chrome_path):
                        chrome_options.binary_location = chrome_path
                        fresh_driver = webdriver.Chrome(options=chrome_options)
                        break
                
                if not fresh_driver:
                    raise Exception("Could not initialize fresh WebDriver")
            
            print(f"✅ Fresh WebDriver initialized successfully")
            
            # Pre-processing debug (enhanced methodology)
            print(f"\n🔍 Pre-processing debug - checking ecode360 page structure")
            print("-" * 30)
            
            print(f"🌐 Navigating to ecode360 page for inspection...")
            fresh_driver.get(ecode_url)
            time.sleep(8)  # Extended wait for optimal processing
            
            # Debug the page content (enhanced processing debug)
            current_page = fresh_driver.page_source
            print(f"📄 Ecode360 page loaded: {len(current_page)} characters")
            
            # Check for 'Download' text (enhanced processing check)
            if 'verify you are human' in current_page.lower():
                print("🤖 CAPTCHA detected on ecode360 page")
            elif 'download' in current_page.lower():
                print("📥 'Download' text found in page content")
            else:
                print("⚠️ No obvious download elements found")
            
            # Show page title and URL for confirmation (enhanced processing debug)
            print(f"📍 Current URL: {fresh_driver.current_url}")
            try:
                page_title = fresh_driver.title
                print(f"📄 Page title: {page_title}")
            except:
                print("📄 Could not get page title")
            
            print(f"\n🎯 Now calling ecode360 handler with debug info")
            print("-" * 30)
            
            # Use the ecode360 handler (enhanced processing)
            ecode_docs = self._handle_ecode360_link(fresh_driver, ecode_url, link_text, source_page)
            
            if ecode_docs:
                print(f"\n🎉 ENHANCED METHODOLOGY SUCCESS!")
                print("=" * 70) 
                print(f"✅ Successfully processed ecode360 document using enhanced approach")
                return ecode_docs
            else:
                print(f"❌ Enhanced methodology found ecode360 link but processing failed")
                return []
                
        except Exception as e:
            print(f"❌ Error in fresh WebDriver ecode360 methodology: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
        
        finally:
            # Always cleanup fresh WebDriver
            if fresh_driver:
                try:
                    fresh_driver.quit()
                    print(f"🧹 Fresh WebDriver cleaned up")
                except:
                    pass

    def _handle_ecode360_link(self, driver: webdriver.Chrome, ecode_url: str, link_text: str, source_page: str) -> List[Dict[str, Any]]:
        """
        Handle ecode360.com links by navigating to the page, finding the Download button,
        and scraping the download version content as PDF with anti-bot bypass strategies
        
        Args:
            driver: Chrome WebDriver instance
            ecode_url: URL to ecode360 page
            link_text: Original link text
            source_page: Source page URL
            
        Returns:
            list: List of processed ecode360 documents
        """
        try:
            # Check if we're already on the target ecode360 page
            current_url = driver.current_url
            
            if ecode_url in current_url or current_url == ecode_url:
                print(f"✅ Already on ecode360 page: {current_url}")
                print(f"🔍 Checking current page for Download button directly...")
                
                # Check page content to ensure it's not a CAPTCHA page
                current_page = driver.page_source
                if 'verify you are human' in current_page.lower() or 'just a moment' in current_page.lower():
                    print(f"🤖 Current page is CAPTCHA, need to navigate fresh")
                    need_navigation = True
                else:
                    print(f"✅ Current page looks valid ({len(current_page)} chars)")
                    need_navigation = False
            else:
                print(f"🌐 Need to navigate to ecode360 page")
                need_navigation = True
            
            if need_navigation:
                # Strategy 1: Establish session with human-like behavior
                print(f"🤖 Implementing anti-bot bypass strategies for ecode360")
                
                # First, visit the main ecode360 site to establish session
                print(f"🌐 Step 1: Establishing session with ecode360.com")
                driver.get("https://ecode360.com")
                time.sleep(3)
                
                # Add some human-like behavior
                print(f"🎭 Step 2: Simulating human behavior")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(2)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
                
                # Now navigate to the target URL
                print(f"🌐 Step 3: Navigating to target ecode360 page: {ecode_url}")
                driver.get(ecode_url)
                time.sleep(8)  # Extended wait for ecode360 to load fully
            else:
                print(f"🎯 Using current session - skipping navigation")
            
            # Look for Download button
            print(f"🔍 Looking for Download button...")
            download_button = None
            
            # Specific selectors for ecode360 download buttons (based on exact HTML structure from user)
            download_selectors = [
                # Exact selectors from the user's HTML inspection
                'a[role="button"][id="downloadButton"]',        # <a role="button" id="downloadButton"
                'a#downloadButton[role="button"]',              # More specific combination
                'a.toolbarButton.downloadLink',                 # class="toolbarButton downloadLink"
                '#downloadButton',                              # Just the ID
                'a#downloadButton',                             # Standard ID selector
                '.toolbarButton.downloadLink',                  # Combined class selector
                'a[class="toolbarButton downloadLink"]',        # Exact class match
                # Additional fallbacks
                'a.downloadLink',
                '.downloadLink', 
                'a[id="downloadButton"]',
                'a[class*="downloadLink"]',
                'a[class*="toolbarButton"]',
                'a[href*="/output/"]',
                'a[href*="download"]',
                '[class*="download"]',
                '[id*="download"]'
            ]
            
            for selector in download_selectors:
                try:
                    print(f"🔍 Trying selector: {selector}")
                    download_button = driver.find_element(By.CSS_SELECTOR, selector)
                    if download_button.is_displayed() and download_button.is_enabled():
                        print(f"✅ Found Download button: {selector}")
                        print(f"   📍 Element: {download_button.tag_name} | ID: {download_button.get_attribute('id')} | Class: {download_button.get_attribute('class')}")
                        print(f"   🔗 Href: {download_button.get_attribute('href')}")
                        break
                    else:
                        print(f"   ⚠️ Element found but not displayed/enabled: {selector}")
                        download_button = None
                except Exception as e:
                    print(f"   ❌ Selector failed: {selector} | Error: {str(e)}")
                    continue
                
                if download_button:
                    break
            
            # Additional text-based search as fallback
            if not download_button:
                print(f"🔍 Trying text-based search for 'Download'...")
                try:
                    # Search for any clickable element containing "Download" text
                    xpath_selectors = [
                        "//a[contains(.,'Download')]",
                        "//button[contains(.,'Download')]", 
                        "//a[contains(@title,'Download')]",
                        "//a[contains(@aria-label,'Download')]",
                        "//*[@role='button' and contains(.,'Download')]"
                    ]
                    
                    for xpath in xpath_selectors:
                        try:
                            elements = driver.find_elements(By.XPATH, xpath)
                            for element in elements:
                                if element.is_displayed() and element.is_enabled():
                                    download_button = element
                                    print(f"✅ Found Download button via XPath: {xpath}")
                                    print(f"   📍 Element: {element.tag_name} | Text: '{element.text}' | Href: {element.get_attribute('href')}")
                                    break
                            if download_button:
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"❌ Text-based search failed: {str(e)}")
            
            if not download_button:
                print(f"⚠️ No Download button found on ecode360 page")
                
                # Enhanced debugging when download button not found
                print(f"🔍 DEBUG: Analyzing page structure for debugging...")
                current_url = driver.current_url
                page_source = driver.page_source
                
                print(f"📍 Current URL: {current_url}")
                print(f"📄 Page source length: {len(page_source)} characters")
                
                # Check for CAPTCHA indicators
                captcha_found = any(indicator in page_source.lower() for indicator in [
                    'verify you are human', 'captcha', 'cloudflare', 'checking your browser'
                ])
                print(f"🤖 CAPTCHA detected: {captcha_found}")
                
                # Show page preview
                preview = page_source[:500].replace('\n', ' ')
                print(f"📄 Page preview: {preview}...")
                
                # Try to find any elements with 'download' in text
                soup_debug = BeautifulSoup(page_source, 'html.parser')
                download_elements = soup_debug.find_all(text=lambda text: text and 'download' in text.lower())
                print(f"🔍 Found {len(download_elements)} text elements containing 'download'")
                
                for i, elem in enumerate(download_elements[:3]):
                    print(f"   {i+1}. '{elem.strip()[:50]}...'")
                
                return []
            
            # Click the download button and process the result
            print(f"🖱️ Clicking Download button...")
            original_url = driver.current_url
            
            # Check if it's a link that opens in new tab/window
            href = download_button.get_attribute('href')
            target = download_button.get_attribute('target')
            
            # Handle the download - navigate to the download URL to get content
            if href:
                print(f"🔗 Download button points to: {href}")
                if href.startswith('/'):
                    # Convert relative URL to absolute
                    from urllib.parse import urljoin
                    full_download_url = urljoin(original_url, href)
                else:
                    full_download_url = href
                
                print(f"🌐 Navigating to download URL: {full_download_url}")
                driver.get(full_download_url)
                time.sleep(5)  # Wait for content to load
                
                new_url = driver.current_url
                print(f"✅ Navigated to download page: {new_url}")
                
                # Get the content from the download page
                page_content = driver.page_source
                print(f"📄 Downloaded content: {len(page_content)} characters")
                
                # Validate that we got meaningful zoning content by checking the page source
                zoning_keywords = ['zoning', 'district', 'bylaw', 'ordinance', 'use', 'setback', 'coverage']
                keyword_count = sum(1 for keyword in zoning_keywords if keyword.lower() in page_content.lower())
                
                if keyword_count >= 2 and len(page_content) > 10000:
                    print(f"✅ Downloaded meaningful zoning content ({keyword_count} keywords found)")
                    
                    # Generate PDF using Chrome's built-in PDF generator
                    # Ensure pdf_downloads directory exists
                    pdf_downloads_dir = os.path.join(os.getcwd(), 'pdf_downloads')
                    os.makedirs(pdf_downloads_dir, exist_ok=True)
                    
                    # Extract district name from source page URL
                    district_name = "Unknown"
                    if source_page:
                        try:
                            from urllib.parse import urlparse
                            parsed_url = urlparse(source_page)
                            domain = parsed_url.netloc.lower()
                            
                            # Extract district name from domain (e.g., fairhaven-ma.gov -> Fairhaven)
                            if domain:
                                # Remove common prefixes and suffixes
                                domain_parts = domain.replace('www.', '').replace('.gov', '').replace('.org', '').replace('.com', '')
                                # Handle cases like "fairhaven-ma" -> "fairhaven"
                                if '-ma' in domain_parts:
                                    district_name = domain_parts.replace('-ma', '').replace('-', ' ')
                                elif 'ma.' in domain_parts:
                                    district_name = domain_parts.replace('ma.', '').replace('-', ' ')
                                else:
                                    district_name = domain_parts.replace('-', ' ').replace('.', ' ')
                                
                                # Capitalize first letter of each word
                                district_name = district_name.title().strip()
                                
                                # Clean up any remaining special characters
                                district_name = "".join(c for c in district_name if c.isalnum() or c == ' ').strip()
                                
                        except Exception as e:
                            print(f"⚠️ Could not extract district name from {source_page}: {str(e)}")
                            district_name = "Unknown"
                    
                    if not district_name or district_name == "Unknown":
                        district_name = "Unknown"
                    
                    filename = f"{district_name}_Zoning_ecode.pdf"
                    filepath = os.path.join(pdf_downloads_dir, filename)
                    
                    print(f"📝 Generating PDF for district: {district_name}")
                    print(f"📄 Filename: {filename}")
                    
                    try:
                        # Use Chrome's print to PDF functionality
                        print(f"🖨️ Converting page to PDF using Chrome...")
                        
                        # Use Chrome DevTools Protocol to generate PDF
                        result = driver.execute_cdp_cmd('Page.printToPDF', {
                            'printBackground': True,
                            'landscape': False,
                            'paperWidth': 8.5,
                            'paperHeight': 11,
                            'marginTop': 0.4,
                            'marginBottom': 0.4,
                            'marginLeft': 0.4,
                            'marginRight': 0.4,
                            'displayHeaderFooter': True,
                            'headerTemplate': f'<div style="font-size:10px; text-align:center; width:100%;">{district_name} Zoning Bylaws (ecode360)</div>',
                            'footerTemplate': '<div style="font-size:10px; text-align:center; width:100%;"><span class="pageNumber"></span> of <span class="totalPages"></span></div>',
                            'preferCSSPageSize': False,
                            'generateTaggedPDF': False
                        })
                        
                        # Save the PDF
                        import base64
                        with open(filepath, 'wb') as f:
                            f.write(base64.b64decode(result['data']))
                        
                        print(f"💾 Saved ecode360 content as PDF: {filepath}")
                        print(f"📁 PDF saved to directory: {pdf_downloads_dir}")
                        
                        # Get file size for verification
                        file_size = os.path.getsize(filepath)
                        print(f"📄 PDF file size: {file_size:,} bytes")
                        
                        return [{
                            'type': 'ecode360_pdf',
                            'title': f"Zoning Bylaws ({link_text})",
                            'url': ecode_url,
                            'download_url': full_download_url,
                            'filepath': filepath,
                            'source_page': source_page,
                            'file_size': file_size
                        }]
                        
                    except Exception as e:
                        print(f"❌ Failed to generate PDF: {str(e)}")
                        print(f"🔄 Falling back to HTML file save...")
                        
                        # Fallback: Save as HTML file if PDF generation fails
                        html_filename = f"{district_name}_Zoning_ecode.html"
                        html_filepath = os.path.join(pdf_downloads_dir, html_filename)
                        
                        try:
                            with open(html_filepath, 'w', encoding='utf-8') as f:
                                f.write(f"<!-- Zoning Bylaws from {ecode_url} -->\n")
                                f.write(f"<!-- Downloaded from: {full_download_url} -->\n")
                                f.write(f"<!-- Source page: {source_page} -->\n")
                                f.write(f"<!-- Downloaded on: {time.strftime('%Y-%m-%d %H:%M:%S')} -->\n")
                                f.write(page_content)
                            
                            print(f"💾 Saved ecode360 content as HTML: {html_filepath}")
                            
                            return [{
                                'type': 'ecode360_html',
                                'title': f"Zoning Bylaws ({link_text})",
                                'url': ecode_url,
                                'download_url': full_download_url,
                                'filepath': html_filepath,
                                'source_page': source_page,
                                'content_length': len(page_content)
                            }]
                            
                        except Exception as html_e:
                            print(f"❌ Failed to save HTML file: {str(html_e)}")
                            return []
                else:
                    print(f"⚠️ Downloaded content doesn't appear to be meaningful zoning content")
                    print(f"   Keywords found: {keyword_count}, Content length: {len(page_content)}")
                    return []
            else:
                print(f"❌ No href found in download button")
                return []
                
        except Exception as e:
            print(f"❌ Error handling ecode360 link: {str(e)}")
            import traceback
            traceback.print_exc()
            return []


# =====================================
# 4. COMBINED ZONING AGENT (Orchestrates Both)
# =====================================

class CombinedZoningAgent:
    """
    Unified agent that orchestrates both ZoningMapAgent and ZoningBylawsAgent
    
    Maintains the original interface for backward compatibility while using 
    the specialized agents internally for better modularity.
    """
    
    def __init__(self):
        configure_logging()
        self.logger = logging.getLogger("bylaws_iq.combined_zoning_agent")
        
        # Initialize specialized agents
        self.map_agent = ZoningMapAgent()
        self.bylaws_agent = ZoningBylawsAgent()
        
        # Shared resources (delegate to map_agent for consistency)
        self.model = self.map_agent.model
        self.classification_model = self.map_agent.classification_model
        self.downloaded_pdfs = self.map_agent.downloaded_pdfs
        
    @property 
    def driver(self):
        """Delegate driver access to map agent"""
        return self.map_agent.driver
        
    def _cleanup_webdriver(self):
        """Cleanup WebDriver resources for both agents"""
        self.map_agent._cleanup_webdriver()
        self.bylaws_agent._cleanup_webdriver()

    def find_zoning_district(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Complete workflow to find zoning district for an address
        
        Delegates to ZoningMapAgent for actual implementation.
        
        Args:
            address (str): Full address to analyze
            
        Returns:
            dict: Zoning district information including code, name, overlays, and source URL
                  or None if discovery fails
        """
        with span(self.logger, "combined_agent.find_zoning_district"):
            self.logger.info(f"🎯 Delegating zoning district discovery to ZoningMapAgent for: {address}")
            return self.map_agent.find_zoning_district(address)
    
    def find_zoning_bylaws(self, address: str, official_website: str = None, zoning_district: str = None) -> Optional[List[Dict[str, Any]]]:
        """
        Find zoning bylaws documents for an address
        
        Delegates to ZoningBylawsAgent for actual implementation, optionally reusing
        previously discovered information to avoid duplicate lookups.
        
        Args:
            address (str): Full address to analyze
            official_website (str, optional): Official website URL if already discovered
            zoning_district (str, optional): Zoning district if already determined
            
        Returns:
            list: List of discovered bylaws documents or None if discovery fails
        """
        with span(self.logger, "combined_agent.find_zoning_bylaws"):
            self.logger.info(f"📋 Delegating bylaws discovery to ZoningBylawsAgent for: {address}")
            
            # Reuse the official website found by the map agent to avoid duplicate lookups
            if not official_website:
                cached_website = getattr(self.map_agent, '_last_official_website', None)
                if cached_website:
                    official_website = cached_website
                    self.logger.info(f"♻️ Reusing official website from map discovery: {official_website}")
                else:
                    self.logger.warning("⚠️ No cached official website available from map discovery")
            
            return self.bylaws_agent.find_zoning_bylaws(address, official_website, zoning_district)
    
    def discover_complete_zoning_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Complete end-to-end zoning discovery and analysis pipeline
        
        Efficiently combines:
        1. Zoning Map discovery & analysis 
        2. Zoning district determination
        3. Zoning bylaws PDF discovery (reusing official website)
        4. Zoning bylaws analysis for specific district metrics
        
        Args:
            address (str): The address to analyze
            
        Returns:
            Optional[Dict[str, Any]]: Complete zoning information including map analysis and bylaws
        """
        try:
            self.logger.info(f"🎯 Starting complete zoning discovery pipeline for: {address}")
            
            complete_result = {
                'address': address,
                'zoning_map_info': None,
                'zoning_bylaws_info': None,
                'success': False,
                'error': None
            }
            
            # Step 1: Discover and analyze zoning map to determine district
            self.logger.info("🗺️ STEP 1: Zoning map discovery & analysis")
            zoning_map_result = self.find_zoning_district(address)
            
            if not zoning_map_result:
                complete_result['error'] = "Failed to discover zoning map or determine zoning district"
                return complete_result
            
            complete_result['zoning_map_info'] = zoning_map_result
            zoning_district = zoning_map_result.get('zoning_code') or zoning_map_result.get('zoning_name')
            
            if not zoning_district:
                complete_result['error'] = "Zoning district could not be determined from map analysis"
                return complete_result
            
            self.logger.info(f"✅ Determined Zoning District: {zoning_district}")
            
            # Extract the official website that was already discovered by the map agent
            # This avoids duplicate MMA lookups
            official_website = None
            if hasattr(self.map_agent, '_last_official_website'):
                official_website = self.map_agent._last_official_website
                self.logger.info(f"♻️ Reusing official website from map discovery: {official_website}")
            
            # Step 2: Discover zoning bylaws PDF (reusing official website)
            self.logger.info("📋 STEP 2: Zoning bylaws PDF discovery")
            bylaws_results = self.find_zoning_bylaws(address, official_website, zoning_district)
            
            if not bylaws_results or len(bylaws_results) == 0:
                complete_result['error'] = "Failed to discover zoning bylaws PDF"
                return complete_result
            
            # Use the first discovered bylaws PDF
            bylaws_pdf = bylaws_results[0]
            complete_result['zoning_bylaws_info'] = bylaws_pdf
            complete_result['success'] = True
            
            self.logger.info(f"✅ Complete zoning discovery successful!")
            return complete_result
            
        except Exception as e:
            self.logger.error(f"❌ Complete zoning discovery failed: {str(e)}", exc_info=True)
            complete_result['error'] = f"Pipeline error: {str(e)}"
            return complete_result



# =====================================
# 5. COMPLETED MODULAR ARCHITECTURE
# =====================================
# 
# The specialized agents above now handle all functionality:
# - BaseZoningAgent: Shared infrastructure (WebDriver, LLM calls, utilities)
# - ZoningMapAgent: Map discovery and analysis 
# - ZoningBylawsAgent: Bylaws discovery and analysis
# - CombinedZoningAgent: Orchestrates both with unified interface
#


def create_zoning_agent() -> CombinedZoningAgent:
    """
    Create a new combined zoning agent
    
    Returns a CombinedZoningAgent that orchestrates both ZoningMapAgent 
    and ZoningBylawsAgent while maintaining the original interface.
    """
    return CombinedZoningAgent()
