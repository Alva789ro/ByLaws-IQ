"""
========================================================================================================
ZONING BYLAWS AGENT - Specialized Bylaws Discovery & Analysis
========================================================================================================

Provides specialized functionality for finding and analyzing municipal zoning bylaws:

CORE CAPABILITIES:
- Multi-method bylaws discovery (Zoning Board of Appeals, Planning Board)
- Ecode360 integration with bot detection bypass
- Selenium-based web automation for dynamic content
- LLM-powered document selection and classification
- Direct PDF analysis and comprehensive metrics extraction

This agent inherits from BaseZoningAgent for shared infrastructure (WebDriver, LLM calls, etc.)
while providing specialized logic for zoning bylaws discovery and analysis workflows.

Key methods:
- find_zoning_bylaws(): Main discovery workflow
- analyze_zoning_bylaws_pdf(): Extract metrics from bylaws PDFs
- Multi-method search strategies with fallback mechanisms
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
from .base_zoning_agent import BaseZoningAgent

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

