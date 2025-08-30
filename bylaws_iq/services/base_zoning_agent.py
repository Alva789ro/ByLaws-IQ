"""
========================================================================================================
BASE ZONING AGENT - Shared Infrastructure for All Zoning Agents
========================================================================================================

Provides shared infrastructure and utilities for all specialized zoning agents:

SHARED CAPABILITIES:
- WebDriver management with multi-strategy initialization
- LLM integration (OpenRouter/Gemini models)
- MMA database lookup for official websites
- Domain normalization and URL utilities
- PDF download and text extraction
- Robust error handling and logging

This base class eliminates code duplication and provides consistent behavior
across all specialized zoning agents (ZoningMapAgent, ZoningBylawsAgent).

All agents inherit from this base to ensure consistent functionality and
shared resource management.
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

    def _call_llm_classification(self, prompt: str) -> str:
        """Call LLM for classification tasks using cheaper model"""
        try:
            load_dotenv()
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY not set")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://bylaws-iq.local", 
                "X-Title": "ByLaws-IQ Classification",
                "Content-Type": "application/json",
            }
            
            messages = [
                {"role": "system", "content": "You are a classification agent that selects the best option from multiple choices. Be precise and follow the output format exactly."},
                {"role": "user", "content": prompt}
            ]
            
            payload = {
                "model": self.classification_model,  # Use cheaper model for classification
                "temperature": 0.0,  # Lower temperature for consistent classification
                "messages": messages,
                "max_tokens": 500  # Classification shouldn't need many tokens
            }
            
            self.logger.debug(f"llm.classification_start: model={self.classification_model}")
            
            import httpx
            with httpx.Client(timeout=30) as client:
                r = client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                r.raise_for_status()
                js = r.json()
            
            response = js["choices"][0]["message"]["content"]
            self.logger.debug(f"llm.classification_success: response_length={len(response)}")
            return response
            
        except Exception as e:
            self.logger.error(f"llm.classification_failed: {str(e)}", exc_info=True)
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

    # SHARED PDF UTILITIES
    def _fetch_pdf_content(self, pdf_url: str) -> Optional[str]:
        """
        Fetch PDF content and extract text
        
        Args:
            pdf_url (str): URL to the PDF file
            
        Returns:
            str or None: Extracted text content
        """
        try:
            self.logger.info(f"pdf.fetch_start: Downloading from {pdf_url}")
            
            # Download PDF with proper headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(pdf_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Extract text using PyPDF2
            try:
                import PyPDF2
                import io
                
                pdf_file = io.BytesIO(response.content)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                
                text_content = ""
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text_content += page.extract_text() + "\n"
                
                self.logger.info(f"pdf.extraction_success: Extracted {len(text_content)} characters")
                return text_content
                
            except ImportError:
                self.logger.warning("pdf.pypdf2_missing: PyPDF2 not available, cannot extract text")
                return None
                
        except Exception as e:
            self.logger.error(f"pdf.fetch_failed: {str(e)}", exc_info=True)
            return None

    # SHARED DOMAIN UTILITIES
    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain by removing www prefix and common variations"""
        if not domain:
            return ""
        return domain.replace('www.', '').replace('www1.', '').replace('www2.', '').lower()
    
    def _same_domain(self, url1: str, url2: str) -> bool:
        """Check if two URLs are from the same domain"""
        try:
            domain1 = urlparse(url1).netloc
            domain2 = urlparse(url2).netloc
            return self._normalize_domain(domain1) == self._normalize_domain(domain2)
        except:
            return False
