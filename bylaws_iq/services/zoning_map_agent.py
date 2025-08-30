"""
========================================================================================================
ZONING MAP AGENT - Specialized Zoning Map Discovery & Analysis
========================================================================================================

Provides specialized functionality for finding and analyzing municipal zoning maps:

CORE CAPABILITIES:
- Official website discovery via MMA database lookup
- Dynamic map search using municipal website search tools  
- LLM-powered map selection and validation
- Direct PDF analysis for zoning district determination
- Selenium-based web automation for JavaScript content
- Fallback search strategies for comprehensive coverage

This agent inherits from BaseZoningAgent for shared infrastructure (WebDriver, LLM calls, etc.)
while providing specialized logic for zoning map discovery and analysis workflows.

Key methods:
- find_zoning_district(): Complete workflow for address-to-zoning-district mapping
- find_official_zoning_map(): Discover most recent official zoning maps
- analyze_zoning_district(): LLM analysis of zoning maps to extract district information

The agent handles diverse municipal website structures and provides robust error handling
with multiple fallback strategies to maximize success rate across different jurisdictions.
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
