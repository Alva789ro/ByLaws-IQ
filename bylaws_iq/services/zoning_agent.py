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
from .base_zoning_agent import BaseZoningAgent
from .zoning_map_agent import ZoningMapAgent
from .zoning_bylaws_agent import ZoningBylawsAgent

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
# 1. COMBINED ZONING AGENT (Orchestrates Both)
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
