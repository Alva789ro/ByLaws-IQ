from __future__ import annotations

import time
import os
import requests
import PyPDF2
import io
from typing import Any, Dict, List, Optional, Callable
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .models import OutputResult
from .logging_config import configure_logging, span
import logging
from .services import geocode as geocode_service
from .services import zoning as zoning_service
from .services import search as search_service
from .services import scrape as scrape_service
from .services import llm as llm_service
from .services.zoning_agent import create_zoning_agent


def _transform_to_metric_values(raw_data: dict, source_title: str, allowed_keys: set = None) -> dict:
	"""Transform raw LLM data to MetricValue objects with optional filtering"""
	from .models import MetricValue
	transformed = {}
	
	for key, value in raw_data.items():
		# Skip keys not in allowed list if filtering is enabled
		if allowed_keys and key not in allowed_keys:
			continue
			
		if isinstance(value, dict) and all(k in value for k in ['value', 'quote', 'source']):
			# Already in the correct LLM format, convert to MetricValue
			transformed[key] = MetricValue(
				value=str(value.get('value', 'Unknown')),
				verified=True,
				source=value.get('source', source_title),
				quote=value.get('quote', ''),
				note=value.get('note', 'Extracted from zoning bylaws')
			)
		elif isinstance(value, (str, list, int, float)):
			# Convert raw values to MetricValue (fallback for old format)
			str_value = str(value) if not isinstance(value, list) else "; ".join(map(str, value))
			transformed[key] = MetricValue(
				value=str_value,
				verified=True,
				source=source_title,
				quote="",
				note="Extracted from zoning bylaws"
			)
		else:
			# If already a MetricValue-like dict, keep as is
			transformed[key] = value
	return transformed


def robust_fetch_pdf(pdf_url: str, referrer_url: str = None, logger=None) -> bytes:
	"""
	Robustly fetch a PDF with multiple strategies to bypass access restrictions
	
	Args:
		pdf_url (str): URL of the PDF to fetch
		referrer_url (str, optional): URL of the page where the PDF link was found
		logger: Logger instance for debugging
		
	Returns:
		bytes: PDF content
		
	Raises:
		Exception: If all strategies fail
	"""
	if logger:
		logger.info(f"🔄 Attempting robust PDF fetch: {pdf_url}")
	
	# Strategy 1: Full browser simulation with session
	try:
		session = requests.Session()
		
		# Set comprehensive browser-like headers
		browser_headers = {
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
			'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
			'Accept-Language': 'en-US,en;q=0.9',
			'Accept-Encoding': 'gzip, deflate, br',
			'Connection': 'keep-alive',
			'Upgrade-Insecure-Requests': '1',
			'Sec-Fetch-Dest': 'document',
			'Sec-Fetch-Mode': 'navigate',
			'Sec-Fetch-Site': 'same-origin',
			'Cache-Control': 'max-age=0'
		}
		
		# Add referrer if provided
		if referrer_url:
			browser_headers['Referer'] = referrer_url
			domain = urlparse(referrer_url).netloc
			# Use the same scheme as the referrer URL
			scheme = urlparse(referrer_url).scheme or 'https'
			browser_headers['Origin'] = f"{scheme}://{domain}"
		
		session.headers.update(browser_headers)
		
		# First, visit the referrer page to establish session
		if referrer_url:
			if logger:
				logger.info(f"🌐 Visiting referrer page first: {referrer_url}")
			try:
				session.get(referrer_url, timeout=15)
			except:
				pass  # Continue even if referrer visit fails
		
		# Now try to fetch the PDF
		if logger:
			logger.info(f"📄 Strategy 1: Full browser simulation")
		
		response = session.get(pdf_url, timeout=30, stream=True)
		response.raise_for_status()
		
		# Verify it's actually a PDF
		content_type = response.headers.get('content-type', '').lower()
		if 'pdf' in content_type or pdf_url.lower().endswith('.pdf'):
			content = response.content
			if logger:
				logger.info(f"✅ Strategy 1 successful: {len(content)} bytes")
			return content
	
	except Exception as e:
		if logger:
			logger.warning(f"❌ Strategy 1 failed: {str(e)}")
	
	# Strategy 2: Direct download with minimal headers
	try:
		if logger:
			logger.info(f"📄 Strategy 2: Direct download")
		
		simple_headers = {
			'User-Agent': 'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; WOW64; Trident/6.0)',
			'Accept': '*/*'
		}
		
		response = requests.get(pdf_url, headers=simple_headers, timeout=30)
		response.raise_for_status()
		
		content = response.content
		if logger:
			logger.info(f"✅ Strategy 2 successful: {len(content)} bytes")
		return content
	
	except Exception as e:
		if logger:
			logger.warning(f"❌ Strategy 2 failed: {str(e)}")
	
	# Strategy 3: Try with different User-Agent (mobile)
	try:
		if logger:
			logger.info(f"📄 Strategy 3: Mobile user agent")
		
		mobile_headers = {
			'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
			'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
		}
		
		response = requests.get(pdf_url, headers=mobile_headers, timeout=30)
		response.raise_for_status()
		
		content = response.content
		if logger:
			logger.info(f"✅ Strategy 3 successful: {len(content)} bytes")
		return content
	
	except Exception as e:
		if logger:
			logger.warning(f"❌ Strategy 3 failed: {str(e)}")
	
	# Strategy 4: Government website navigation (for sites like Woburn)
	try:
		if logger:
			logger.info(f"📄 Strategy 4: Government website navigation")
		
		session = requests.Session()
		session.headers.update({
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
			'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
			'Accept-Language': 'en-US,en;q=0.9',
			'Connection': 'keep-alive',
			'Upgrade-Insecure-Requests': '1'
		})
		
		# Extract domain from PDF URL and visit main site first
		parsed = urlparse(pdf_url)
		main_site = f"{parsed.scheme}://{parsed.netloc}/"
		
		if logger:
			logger.info(f"🌐 Visiting main site first: {main_site}")
		
		# Visit main site
		try:
			session.get(main_site, timeout=15)
		except:
			pass
		
		# Try planning board or government page
		potential_pages = [
			f"{parsed.scheme}://{parsed.netloc}/government/planning-board/",
			f"{parsed.scheme}://{parsed.netloc}/planning-board/",
			f"{parsed.scheme}://{parsed.netloc}/government/",
			f"{parsed.scheme}://{parsed.netloc}/documents/"
		]
		
		for page in potential_pages:
			try:
				if logger:
					logger.info(f"🌐 Trying navigation page: {page}")
				session.get(page, timeout=10)
				break
			except:
				continue
		
		# Now try the PDF
		response = session.get(pdf_url, timeout=30)
		response.raise_for_status()
		
		content = response.content
		if logger:
			logger.info(f"✅ Strategy 4 successful: {len(content)} bytes")
		return content
	
	except Exception as e:
		if logger:
			logger.warning(f"❌ Strategy 4 failed: {str(e)}")
	
	# Strategy 5: Try HTTP instead of HTTPS if URL is HTTPS
	if pdf_url.startswith('https://'):
		try:
			http_url = pdf_url.replace('https://', 'http://')
			if logger:
				logger.info(f"📄 Strategy 5: HTTP fallback to {http_url}")
			
			response = requests.get(http_url, headers={
				'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
			}, timeout=30)
			response.raise_for_status()
			
			content = response.content
			if logger:
				logger.info(f"✅ Strategy 5 successful: {len(content)} bytes")
			return content
		
		except Exception as e:
			if logger:
				logger.warning(f"❌ Strategy 5 failed: {str(e)}")
	
	# All strategies failed
	raise Exception(f"All PDF fetch strategies failed for {pdf_url}")


def run_query_fallback(
	address: str,
	requested_metrics: List[str],
	zoning_district_info: Optional[Dict[str, Any]] = None,
	geo: Optional[Dict[str, Any]] = None,
	on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
	"""Fallback query using search results when official bylaws not found"""
	configure_logging()
	logger = logging.getLogger("bylaws_iq.pipeline")
	start_time = time.time()

	def progress(msg: str) -> None:
		logger.info("progress: %s", msg)
		if on_progress:
			try:
				on_progress(msg)
			except Exception:
				logger.debug("progress callback failed", exc_info=True)

	# If geo wasn't provided, do geocoding
	if not geo:
		with span(logger, "geocode"):
			progress("Geocoding address")
			geo = geocode_service.geocode_address(address)

	# Use legacy zoning discovery
	zoning_districts = []
	if not zoning_district_info:
		with span(logger, "discover_zoning_legacy"):
			progress("🔄 Using fallback: Discovering zoning districts")
		zoning_districts = zoning_service.discover_zoning_districts(
			latitude=geo["lat"], longitude=geo["lon"], jurisdiction=geo["jurisdiction"]
		)

	allowlist = [".gov", ".us", "municode.com", "ecode360.com", "arcgis.com", "mapgeo.io"]

	with span(logger, "search_documents"):
		progress("🔄 Using fallback: Searching public code sources")
		
		# Build enhanced search query with zoning district information
		base_query = f"zoning code parking setbacks height {geo['jurisdiction'].get('city','')} {geo['jurisdiction'].get('state','')}"
		
		# Add zoning district information to search if available
		if zoning_district_info:
			zoning_code = zoning_district_info.get('zoning_code', '')
			zoning_name = zoning_district_info.get('zoning_name', '')
			overlays = zoning_district_info.get('overlays', [])
			
			# Enhanced search with specific zoning district
			enhanced_query = f"{base_query} {zoning_code} \"{zoning_name}\""
			if overlays:
				enhanced_query += f" {' '.join(overlays)}"
			
			logger.info(f"🔍 Fallback search with zoning district: {zoning_code}")
			progress(f"🔄 Fallback: Searching for {zoning_code} regulations")
		else:
			enhanced_query = base_query
			logger.info("🔍 Using basic fallback search")
		
		search_results = search_service.search_documents(
			query=enhanced_query,
			allowed_domains=allowlist,
		)

	with span(logger, "fetch_and_prepare_docs"):
		progress("🔄 Fallback: Fetching and preparing source documents")
		documents = []
		target_city = (geo["jurisdiction"].get("city") or "").lower()
		target_state = (geo["jurisdiction"].get("state") or "").lower()
		from rapidfuzz import fuzz
		for item in search_results[:8]:
			url = item.get("url")
			title = item.get("title") or ""
			if not url:
				continue
			try:
				text_html, raw_bytes, ctype = scrape_service.fetch(url)
				if ctype and "pdf" in ctype and raw_bytes:
					pdf_text = scrape_service.try_extract_pdf_text(url, raw_bytes)
					text = pdf_text or ""
				else:
					if not text_html:
						continue
					text = scrape_service.parse_text_from_html(text_html)
			except Exception:
				logger.debug("doc.fetch.failed: %s", url, exc_info=True)
				continue
			text_lc = text.lower()
			city_ok = True
			state_ok = True
			if target_city:
				candidates = [target_city, url.lower(), title.lower(), text_lc[:5000]]
				city_ok = any(fuzz.partial_ratio(target_city, c) >= 70 for c in candidates)
			if target_state:
				candidates = [target_state, url.lower(), title.lower(), text_lc[:5000]]
				state_ok = any(fuzz.partial_ratio(target_state, c) >= 70 for c in candidates)
			if not (city_ok and state_ok):
				logger.info("doc.filtered.jurisdiction: %s", url)
				continue
			excerpt = text[:8000]
			documents.append({"url": url, "title": title, "excerpt": excerpt})
		logger.info("docs.prepared: %d", len(documents))

	with span(logger, "synthesize_metrics"):
		progress("🔄 Fallback: Synthesizing metric candidates with LLM")
		
		# Add discovered zoning district
		enhanced_zoning_districts = []
		if zoning_district_info:
			from .models import ZoningDistrict
			discovered_district = ZoningDistrict(
				code=zoning_district_info.get('zoning_code', ''),
				name=zoning_district_info.get('zoning_name', ''),
				overlays=zoning_district_info.get('overlays', []),
				source=zoning_district_info.get('zoning_map_url', 'Official Zoning Map Analysis')
			)
			enhanced_zoning_districts = [discovered_district]
		else:
			enhanced_zoning_districts = []
		
		extraction = llm_service.synthesize_metrics(
			address=address,
			jurisdiction=geo["jurisdiction"],
			zoning_districts=enhanced_zoning_districts,
			requested_metrics=requested_metrics,
			documents=documents,
		)

	verified = extraction

	with span(logger, "collect_citations"):
		citations = search_service.collect_citations(search_results)

	# Prepare final zoning districts output (prioritize discovered district)
	final_zoning_districts = enhanced_zoning_districts if zoning_district_info else zoning_districts
	
	# Transform raw LLM data to MetricValue objects with proper filtering
	source_title = "Fallback Search Results"
	
	# Define allowed metrics (matching old implementation)
	allowed_parking = {"carParking90Deg", "officesParkingRatio", "drivewayWidth"}
	allowed_zoning = {"minLotArea", "minFrontSetback", "minSideSetback", "minRearSetback", "minLotFrontage", "minLotWidth"}
	
	transformed_zoning_analysis = _transform_to_metric_values(verified.get("zoningAnalysis", {}), source_title, allowed_zoning)
	transformed_parking_summary = _transform_to_metric_values(verified.get("parkingSummary", {}), source_title, allowed_parking)
	
	output = OutputResult(
		address=address,
		jurisdiction=geo["jurisdiction"],
		zoningDistricts=final_zoning_districts,
		parkingSummary=transformed_parking_summary,
		zoningAnalysis=transformed_zoning_analysis,
		confidence=llm_service.estimate_confidence(verified),
		citations=citations,
		mode="fallback_synthesis",
		latencyMs=int((time.time() - start_time) * 1000),
	)
	
	# Add zoning district discovery metadata to output if available
	output_dict = output.model_dump()
	if zoning_district_info:
		output_dict["discoveredZoningDistrict"] = {
			"code": zoning_district_info.get('zoning_code'),
			"name": zoning_district_info.get('zoning_name'),
			"overlays": zoning_district_info.get('overlays', []),
			"sourceUrl": zoning_district_info.get('zoning_map_url'),
			"discoveryMethod": "Official Zoning Map Analysis"
		}
	
	output_dict["fallbackUsed"] = True
	logger.info("result.latencyMs=%d confidence=%.3f mode=%s", output.latencyMs, output.confidence, output.mode)
	return output_dict


def run_query_with_manual_zoning(
	address: str,
	requested_metrics: List[str],
	zoning_district_name: str,
	zoning_district_code: str,
	geo: Dict[str, Any],
	official_website: Optional[str] = None,
	zoning_agent = None,
	on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
	"""Run query pipeline with manually provided zoning district information"""
	configure_logging()
	logger = logging.getLogger("bylaws_iq.pipeline")
	start_time = time.time()

	def progress(msg: str) -> None:
		logger.info("progress: %s", msg)
		if on_progress:
			try:
				on_progress(msg)
			except Exception:
				logger.debug("progress callback failed", exc_info=True)

	# Create zoning district info from manual input
	zoning_district_info = {
		'zoning_code': zoning_district_code.strip(),
		'zoning_name': zoning_district_name.strip(),
		'overlays': [],
		'zoning_map_url': None,
		'discovery_method': 'Manual User Input'
	}
	
	logger.info(f"✅ Using manual zoning district: {zoning_district_code} - {zoning_district_name}")
	progress(f"✅ Using manual zoning district: {zoning_district_code} - {zoning_district_name}")

	# Use the existing zoning agent if provided, otherwise create new one
	if zoning_agent is None:
		zoning_agent = create_zoning_agent()
		logger.info("🔧 Created new zoning agent for manual zoning processing")
	else:
		logger.info("🔧 Reusing existing zoning agent from map discovery")
	
	# Log the preserved official website
	if official_website:
		logger.info(f"🌐 Using preserved official website: {official_website}")
	else:
		logger.warning("⚠️ No official website preserved from map discovery")
	
	# Discover official bylaws PDF for the manually provided zoning district
	official_bylaws_documents = []
	use_fallback_system = False
	
	with span(logger, "discover_zoning_bylaws"):
		zoning_code = zoning_district_info.get('zoning_code', '')
		progress(f"📋 Discovering official bylaws for district {zoning_code}")
		try:
			# Call bylaws discovery with zoning district context and preserved official website
			bylaws_results = zoning_agent.find_zoning_bylaws(
				address, 
				zoning_district=zoning_code,
				official_website=official_website
			)
			if bylaws_results and len(bylaws_results) > 0:
				bylaws_pdf = bylaws_results[0]  # Use the best discovered PDF
				
				# Convert to document format for synthesis, preserving all needed fields
				doc_info = {
					'url': bylaws_pdf['url'],
					'title': bylaws_pdf['title'],
					'content': f"Official Zoning Bylaws: {bylaws_pdf['title']}",
					'score': 1.0,  # Highest priority
					'source': 'official_bylaws_discovery'
				}
				
				# Preserve essential fields for document processing
				if 'type' in bylaws_pdf:
					doc_info['type'] = bylaws_pdf['type']
				
				if 'filepath' in bylaws_pdf:
					doc_info['filepath'] = bylaws_pdf['filepath']
				
				if 'download_url' in bylaws_pdf:
					doc_info['download_url'] = bylaws_pdf['download_url']
				
				# Add source page if available for referrer header
				if 'source_page' in bylaws_pdf:
					doc_info['source_page'] = bylaws_pdf['source_page']
				
				official_bylaws_documents.append(doc_info)
				
				logger.info(f"✅ Found official bylaws: {bylaws_pdf['title']}")
				progress(f"✅ Found official bylaws: {bylaws_pdf['title']}")
			else:
				logger.warning(f"⚠️ No official bylaws found for {zoning_code}")
				progress(f"⚠️ Could not find official bylaws using primary method")
				use_fallback_system = True
		except Exception as e:
			logger.error(f"❌ Bylaws discovery error: {str(e)}", exc_info=True)
			progress(f"⚠️ Official bylaws discovery failed")
			use_fallback_system = True

	# If we need fallback, ask user for permission
	if use_fallback_system:
		progress("🤔 Primary method failed - requesting fallback permission")
		# This will be handled by the UI - we'll return a special status
		return {
			"status": "fallback_permission_required",
			"message": "We couldn't find official bylaws using our primary method. Would you like us to try our fallback search method instead?",
			"address": address,
			"zoning_district_info": zoning_district_info,
			"geo": geo,
			"requested_metrics": requested_metrics
		}

	# Continue with the same logic as the main run_query function
	# Since we have official bylaws, skip general search
	logger.info("🎯 Using official bylaws only - skipping general search")
	progress("🎯 Using official bylaws document only")
	search_results = []

	with span(logger, "fetch_and_prepare_docs"):
		progress("Preparing official bylaws document")
		documents = []
		
		# Use ONLY the official bylaws document we discovered
		progress("🏛️ Fetching official bylaws document")
		for official_doc in official_bylaws_documents:
			try:
				doc_type = official_doc.get('type', 'pdf')
				url = official_doc['url']
				logger.info(f"🏛️ Processing official bylaws ({doc_type}): {url}")
				logger.info(f"📄 Document metadata: {list(official_doc.keys())}")
				
				text = ""
				
				if doc_type == 'ecode360_pdf':
					# Handle ecode360 PDF file
					progress("📄 Processing ecode360 PDF document")
					pdf_file_path = official_doc.get('filepath')
					
					logger.info(f"🔍 Looking for PDF file at: {pdf_file_path}")
					logger.info(f"📁 File exists: {os.path.exists(pdf_file_path) if pdf_file_path else 'No filepath provided'}")
					
					if pdf_file_path and os.path.exists(pdf_file_path):
						logger.info(f"📖 Reading ecode360 PDF file: {pdf_file_path}")
						
						try:
							with open(pdf_file_path, 'rb') as f:
								pdf_reader = PyPDF2.PdfReader(f)
								text = ""
								page_count = len(pdf_reader.pages)
								logger.info(f"📄 PDF has {page_count} pages")
								
								for i, page in enumerate(pdf_reader.pages):
									page_text = page.extract_text()
									text += page_text + "\n"
									logger.info(f"📄 Page {i+1}: extracted {len(page_text)} characters")
							
							logger.info(f"✅ Loaded {len(text):,} characters from ecode360 PDF document")
							progress("✅ Ecode360 PDF Document Processed Successfully")
						except Exception as pdf_error:
							logger.error(f"❌ Error reading PDF file: {str(pdf_error)}")
							raise Exception(f"Failed to read PDF file {pdf_file_path}: {str(pdf_error)}")
					else:
						raise Exception(f"ecode360 PDF file not found: {pdf_file_path}")
				
				elif doc_type == 'ecode360_html':
					# Handle ecode360 HTML file (fallback)
					progress("📄 Processing ecode360 HTML document")
					html_file_path = official_doc.get('filepath')
					
					if html_file_path and os.path.exists(html_file_path):
						logger.info(f"📖 Reading ecode360 HTML file: {html_file_path}")
						
						with open(html_file_path, 'r', encoding='utf-8') as f:
							html_content = f.read()
						
						# Extract text from HTML using BeautifulSoup
						soup = BeautifulSoup(html_content, 'html.parser')
						
						# Remove script, style, and other non-content elements
						for script in soup(["script", "style", "nav", "header", "footer"]):
							script.decompose()
						
						# Get text content
						text_content = soup.get_text()
						lines = (line.strip() for line in text_content.splitlines())
						chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
						text = '\n'.join(chunk for chunk in chunks if chunk)
						
						logger.info(f"✅ Loaded {len(text):,} characters from ecode360 HTML document")
						progress("✅ Ecode360 HTML Document Processed Successfully")
					else:
						raise Exception(f"ecode360 HTML file not found: {html_file_path}")
				
				elif doc_type == 'ecode360_txt':
					# Handle legacy ecode360 .txt file (for backward compatibility)
					progress("📄 Processing ecode360 text document")
					txt_file_path = official_doc.get('txt_file_path') or official_doc.get('filepath')
					
					if txt_file_path and os.path.exists(txt_file_path):
						logger.info(f"📖 Reading ecode360 text file: {txt_file_path}")
						
						with open(txt_file_path, 'r', encoding='utf-8') as f:
							text = f.read()
						
						logger.info(f"✅ Loaded {len(text):,} characters from ecode360 document")
						progress("✅ Ecode360 Document Processed Successfully")
					else:
						raise Exception(f"ecode360 text file not found: {txt_file_path}")
				
				else:
					# Handle standard PDF document
					progress("🔄 Accessing official document (may try multiple strategies)")
					
					# Try to get the referrer URL (the page where we found this PDF)
					referrer_url = None
					# Look for "source_page" in the official_doc metadata if available
					if 'source_page' in official_doc:
						referrer_url = official_doc['source_page']
					else:
						# Generate a reasonable referrer based on the domain
						from urllib.parse import urlparse
						parsed = urlparse(url)
						referrer_url = f"{parsed.scheme}://{parsed.netloc}/"
					
					# Use robust PDF fetching with multiple strategies
					pdf_content = robust_fetch_pdf(url, referrer_url, logger)
					progress("✅ Successfully accessed official document")
					
					# Extract text from PDF
					pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
					for page in pdf_reader.pages:  # Use all pages for official document
						text += page.extract_text() + "\n"
				
				# Add the official document as the ONLY source
				documents.append({
					"url": official_doc.get('url', url),  # Use URL from document
					"title": official_doc['title'],
					"text": text,  # Use full text for official document
					"score": 1.0,
					"source": "official_bylaws",
					"city_match": 1.0,
					"domain_priority": 1.0
				})
				
				logger.info(f"✅ Using official bylaws document only: {len(text)} chars")
				progress(f"✅ Extracted {len(text):,} characters from official document")
				
			except Exception as e:
				logger.error(f"❌ Failed to fetch official bylaws {url}: {str(e)}")
				# If we can't fetch the official document, we need fallback
				return {
					"status": "fallback_permission_required",
					"message": "We found the official bylaws document but couldn't access it. Would you like us to try our fallback search method instead?",
					"address": address,
					"zoning_district_info": zoning_district_info,
					"geo": geo,
					"requested_metrics": requested_metrics
				}
		
		logger.info("docs.prepared: %d (official only)", len(documents))

	with span(logger, "synthesize_metrics"):
		progress("Synthesizing metric candidates with LLM")
		
		try:
			# Add discovered zoning district
			enhanced_zoning_districts = []
			if zoning_district_info and isinstance(zoning_district_info, dict):
				from .models import ZoningDistrict
				
				# Safely extract values with proper None checks
				zoning_code = zoning_district_info.get('zoning_code') or ''
				zoning_name = zoning_district_info.get('zoning_name') or ''
				overlays = zoning_district_info.get('overlays') or []
				source = zoning_district_info.get('zoning_map_url') or 'Manual User Input'
				
				# Only create district if we have at least a name or code
				if zoning_code or zoning_name:
					discovered_district = ZoningDistrict(
						code=zoning_code,
						name=zoning_name,
						overlays=overlays,
						source=source
					)
					enhanced_zoning_districts = [discovered_district]
					logger.info(f"🎯 Synthesizing metrics for manually provided zoning district: {discovered_district.code} - {discovered_district.name}")
				else:
					logger.warning(f"⚠️ Zoning district info found but missing code and name")
					enhanced_zoning_districts = []
			else:
				enhanced_zoning_districts = []
				logger.info(f"🎯 Synthesizing metrics without specific zoning district")
			
			logger.info(f"📊 Documents for synthesis: {len(documents)}")
			logger.info(f"📋 Requested metrics: {requested_metrics}")
			
			extraction = llm_service.synthesize_metrics(
				address=address,
				jurisdiction=geo["jurisdiction"],
				zoning_districts=enhanced_zoning_districts,
				requested_metrics=requested_metrics,
				documents=documents,
			)
			
			logger.info(f"✅ LLM synthesis completed successfully")
			progress("✅ Metrics synthesis completed successfully")
			
		except Exception as e:
			logger.error(f"❌ Error during LLM synthesis: {str(e)}", exc_info=True)
			progress(f"❌ Error during metrics synthesis: {str(e)}")
			raise e

	verified = extraction

	with span(logger, "collect_citations"):
		# Create citation from the official bylaws document only
		citations = [
			{
				"label": official_bylaws_documents[0]['title'],
				"url": official_bylaws_documents[0]['url'],
				"type": "official_bylaws"
			}
		]
		logger.info("citations.source: official_bylaws_only")

	# Prepare final zoning districts output
	final_zoning_districts = enhanced_zoning_districts
	
	# Transform raw LLM data to MetricValue objects with proper filtering
	source_title = official_bylaws_documents[0]['title'] if official_bylaws_documents else "Official Bylaws"
	
	# Define allowed metrics (matching old implementation)
	allowed_parking = {"carParking90Deg", "officesParkingRatio", "drivewayWidth"}
	allowed_zoning = {"minLotArea", "minFrontSetback", "minSideSetback", "minRearSetback", "minLotFrontage", "minLotWidth"}
	
	transformed_zoning_analysis = _transform_to_metric_values(verified.get("zoningAnalysis", {}), source_title, allowed_zoning)
	transformed_parking_summary = _transform_to_metric_values(verified.get("parkingSummary", {}), source_title, allowed_parking)

	output = OutputResult(
		address=address,
		jurisdiction=geo["jurisdiction"],
		parkingSummary=transformed_parking_summary,
		zoningAnalysis=transformed_zoning_analysis,
		confidence=llm_service.estimate_confidence(verified),
		citations=citations,
		mode="synthesis",
		latencyMs=int((time.time() - start_time) * 1000),
		zoningDistricts=final_zoning_districts,
	)
	
	# Add zoning district discovery metadata to output if available
	output_dict = output.model_dump()
	if zoning_district_info:
		output_dict["discoveredZoningDistrict"] = {
			"code": zoning_district_info.get('zoning_code'),
			"name": zoning_district_info.get('zoning_name'),
			"overlays": zoning_district_info.get('overlays', []),
			"sourceUrl": zoning_district_info.get('zoning_map_url'),
			"discoveryMethod": zoning_district_info.get('discovery_method', 'Manual User Input')
		}
	
	# Add official bylaws source if available
	if official_bylaws_documents:
		output_dict["officialBylawsSource"] = {
			"title": official_bylaws_documents[0]['title'],
			"url": official_bylaws_documents[0]['url'],
			"discoveryMethod": "Official Website Search"
		}
	logger.info("result.latencyMs=%d confidence=%.3f mode=%s", output.latencyMs, output.confidence, output.mode)
	return output_dict


def run_query(
	address: str,
	requested_metrics: List[str],
	on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
	configure_logging()
	logger = logging.getLogger("bylaws_iq.pipeline")
	start_time = time.time()

	def progress(msg: str) -> None:
		logger.info("progress: %s", msg)
		if on_progress:
			try:
				on_progress(msg)
			except Exception:
				logger.debug("progress callback failed", exc_info=True)

	with span(logger, "geocode"):
		progress("Geocoding address")
		geo = geocode_service.geocode_address(address)

	# Initialize our new zoning discovery system
	zoning_agent = create_zoning_agent()
	zoning_district_info = None
	zoning_map_failed = False
	official_website_from_map_discovery = None
	
	with span(logger, "discover_zoning_district"):
		progress("🗺️ Discovering zoning district for address")
		try:
			# Use our new proven zoning discovery system
			zoning_district_info = zoning_agent.find_zoning_district(address)
			
			# Try to preserve the official website URL even if zoning district discovery failed
			try:
				if hasattr(zoning_agent, 'zoning_map_agent') and hasattr(zoning_agent.zoning_map_agent, 'official_website'):
					official_website_from_map_discovery = zoning_agent.zoning_map_agent.official_website
					if official_website_from_map_discovery:
						logger.info(f"🌐 Preserved official website from map discovery: {official_website_from_map_discovery}")
			except Exception:
				logger.debug("Could not extract official website from zoning map agent")
			
			if zoning_district_info:
				# Debug: Check for None values in zoning district data
				zoning_code = zoning_district_info.get('zoning_code')
				zoning_name = zoning_district_info.get('zoning_name')
				if zoning_code is None or zoning_name is None:
					logger.warning(f"🔍 DEBUG: Zoning district has None values - keys: {list(zoning_district_info.keys())}")
				
				logger.info(f"✅ Zoning district found: {zoning_code} - {zoning_name}")
				progress(f"✅ Found zoning district: {zoning_code} - {zoning_name}")
			else:
				logger.warning("⚠️ No zoning district found using new system")
				progress("⚠️ Zoning district discovery failed")
				zoning_map_failed = True
		except Exception as e:
			logger.error(f"❌ Zoning discovery error: {str(e)}", exc_info=True)
			progress("⚠️ Zoning district discovery failed")
			zoning_map_failed = True

	# Discover official bylaws PDF for the zoning district
	official_bylaws_documents = []
	use_fallback_system = False
	
	if zoning_district_info:
		with span(logger, "discover_zoning_bylaws"):
			zoning_code = zoning_district_info.get('zoning_code', '')
			progress(f"📋 Discovering official bylaws for district {zoning_code}")
			try:
				# Call bylaws discovery with zoning district context for better targeting
				bylaws_results = zoning_agent.find_zoning_bylaws(address, zoning_district=zoning_code)
				if bylaws_results and len(bylaws_results) > 0:
					bylaws_pdf = bylaws_results[0]  # Use the best discovered PDF
					
					# Convert to document format for synthesis, preserving all needed fields
					doc_info = {
						'url': bylaws_pdf['url'],
						'title': bylaws_pdf['title'],
						'content': f"Official Zoning Bylaws: {bylaws_pdf['title']}",
						'score': 1.0,  # Highest priority
						'source': 'official_bylaws_discovery'
					}
					
					# Preserve essential fields for document processing
					if 'type' in bylaws_pdf:
						doc_info['type'] = bylaws_pdf['type']
					
					if 'filepath' in bylaws_pdf:
						doc_info['filepath'] = bylaws_pdf['filepath']
					
					if 'download_url' in bylaws_pdf:
						doc_info['download_url'] = bylaws_pdf['download_url']
					
					# Add source page if available for referrer header
					if 'source_page' in bylaws_pdf:
						doc_info['source_page'] = bylaws_pdf['source_page']
					
					official_bylaws_documents.append(doc_info)
					
					logger.info(f"✅ Found official bylaws: {bylaws_pdf['title']}")
					progress(f"✅ Found official bylaws: {bylaws_pdf['title']}")
				else:
					logger.warning(f"⚠️ No official bylaws found for {zoning_code}")
					progress(f"⚠️ Could not find official bylaws using primary method")
					use_fallback_system = True
			except Exception as e:
				logger.error(f"❌ Bylaws discovery error: {str(e)}", exc_info=True)
				progress(f"⚠️ Official bylaws discovery failed")
				use_fallback_system = True
	else:
		logger.warning("⚠️ No zoning district found - will need fallback")
		progress("⚠️ No zoning district found - will need fallback")
		use_fallback_system = True

	# Check if specifically the zoning map discovery failed
	if zoning_map_failed:
		progress("🤔 Zoning map discovery failed - requesting manual district entry")
		# Extract city name from the geocoded information for the UI message
		city_name = geo.get("jurisdiction", {}).get("city", "this")
		return {
			"status": "manual_zoning_district_required",
			"message": f"We couldn't find an accurate Zoning Map for the {city_name} Jurisdiction. You can provide the Zoning District to continue",
			"city_name": city_name,
			"address": address,
			"geo": geo,
			"requested_metrics": requested_metrics,
			"official_website": official_website_from_map_discovery,
			"zoning_agent": zoning_agent  # Pass the existing agent instance
		}

	# If we need fallback for other reasons, ask user for permission
	if use_fallback_system:
		progress("🤔 Primary method failed - requesting fallback permission")
		# This will be handled by the UI - we'll return a special status
		return {
			"status": "fallback_permission_required",
			"message": "We couldn't find official bylaws using our primary method. Would you like us to try our fallback search method instead?",
			"address": address,
			"zoning_district_info": zoning_district_info,
			"geo": geo,
			"requested_metrics": requested_metrics
		}

	# Since we have official bylaws, skip general search
	logger.info("🎯 Using official bylaws only - skipping general search")
	progress("🎯 Using official bylaws document only")
	search_results = []

	with span(logger, "fetch_and_prepare_docs"):
		progress("Preparing official bylaws document")
		documents = []
		
		# Use ONLY the official bylaws document we discovered
		progress("🏛️ Fetching official bylaws document")
		for official_doc in official_bylaws_documents:
			try:
				doc_type = official_doc.get('type', 'pdf')
				url = official_doc['url']
				logger.info(f"🏛️ Processing official bylaws ({doc_type}): {url}")
				logger.info(f"📄 Document metadata: {list(official_doc.keys())}")
				
				text = ""
				
				if doc_type == 'ecode360_pdf':
					# Handle ecode360 PDF file
					progress("📄 Processing ecode360 PDF document")
					pdf_file_path = official_doc.get('filepath')
					
					logger.info(f"🔍 Looking for PDF file at: {pdf_file_path}")
					logger.info(f"📁 File exists: {os.path.exists(pdf_file_path) if pdf_file_path else 'No filepath provided'}")
					
					if pdf_file_path and os.path.exists(pdf_file_path):
						logger.info(f"📖 Reading ecode360 PDF file: {pdf_file_path}")
						
						try:
							with open(pdf_file_path, 'rb') as f:
								pdf_reader = PyPDF2.PdfReader(f)
								text = ""
								page_count = len(pdf_reader.pages)
								logger.info(f"📄 PDF has {page_count} pages")
								
								for i, page in enumerate(pdf_reader.pages):
									page_text = page.extract_text()
									text += page_text + "\n"
									logger.info(f"📄 Page {i+1}: extracted {len(page_text)} characters")
							
							logger.info(f"✅ Loaded {len(text):,} characters from ecode360 PDF document")
							progress("✅ Ecode360 PDF Document Processed Successfully")
						except Exception as pdf_error:
							logger.error(f"❌ Error reading PDF file: {str(pdf_error)}")
							raise Exception(f"Failed to read PDF file {pdf_file_path}: {str(pdf_error)}")
					else:
						raise Exception(f"ecode360 PDF file not found: {pdf_file_path}")
				
				elif doc_type == 'ecode360_html':
					# Handle ecode360 HTML file (fallback)
					progress("📄 Processing ecode360 HTML document")
					html_file_path = official_doc.get('filepath')
					
					if html_file_path and os.path.exists(html_file_path):
						logger.info(f"📖 Reading ecode360 HTML file: {html_file_path}")
						
						with open(html_file_path, 'r', encoding='utf-8') as f:
							html_content = f.read()
						
						# Extract text from HTML using BeautifulSoup
						soup = BeautifulSoup(html_content, 'html.parser')
						
						# Remove script, style, and other non-content elements
						for script in soup(["script", "style", "nav", "header", "footer"]):
							script.decompose()
						
						# Get text content
						text_content = soup.get_text()
						lines = (line.strip() for line in text_content.splitlines())
						chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
						text = '\n'.join(chunk for chunk in chunks if chunk)
						
						logger.info(f"✅ Loaded {len(text):,} characters from ecode360 HTML document")
						progress("✅ Ecode360 HTML Document Processed Successfully")
					else:
						raise Exception(f"ecode360 HTML file not found: {html_file_path}")
				
				elif doc_type == 'ecode360_txt':
					# Handle legacy ecode360 .txt file (for backward compatibility)
					progress("📄 Processing ecode360 text document")
					txt_file_path = official_doc.get('txt_file_path') or official_doc.get('filepath')
					
					if txt_file_path and os.path.exists(txt_file_path):
						logger.info(f"📖 Reading ecode360 text file: {txt_file_path}")
						
						with open(txt_file_path, 'r', encoding='utf-8') as f:
							text = f.read()
						
						logger.info(f"✅ Loaded {len(text):,} characters from ecode360 document")
						progress("✅ Ecode360 Document Processed Successfully")
					else:
						raise Exception(f"ecode360 text file not found: {txt_file_path}")
				
				else:
					# Handle standard PDF document
					progress("🔄 Accessing official document (may try multiple strategies)")
					
					# Try to get the referrer URL (the page where we found this PDF)
					referrer_url = None
					# Look for "source_page" in the official_doc metadata if available
					if 'source_page' in official_doc:
						referrer_url = official_doc['source_page']
					else:
						# Generate a reasonable referrer based on the domain
						from urllib.parse import urlparse
						parsed = urlparse(url)
						referrer_url = f"{parsed.scheme}://{parsed.netloc}/"
					
					# Use robust PDF fetching with multiple strategies
					pdf_content = robust_fetch_pdf(url, referrer_url, logger)
					progress("✅ Successfully accessed official document")
					
					# Extract text from PDF
					pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
					for page in pdf_reader.pages:  # Use all pages for official document
						text += page.extract_text() + "\n"
				
				# Add the official document as the ONLY source
				documents.append({
					"url": official_doc.get('url', url),  # Use URL from document
					"title": official_doc['title'],
					"text": text,  # Use full text for official document
					"score": 1.0,
					"source": "official_bylaws",
					"city_match": 1.0,
					"domain_priority": 1.0
				})
				
				logger.info(f"✅ Using official bylaws document only: {len(text)} chars")
				progress(f"✅ Extracted {len(text):,} characters from official document")
				
			except Exception as e:
				logger.error(f"❌ Failed to fetch official bylaws {url}: {str(e)}")
				# If we can't fetch the official document, we need fallback
				return {
					"status": "fallback_permission_required",
					"message": "We found the official bylaws document but couldn't access it. Would you like us to try our fallback search method instead?",
					"address": address,
					"zoning_district_info": zoning_district_info,
					"geo": geo,
					"requested_metrics": requested_metrics
				}
		
		logger.info("docs.prepared: %d (official only)", len(documents))

	with span(logger, "synthesize_metrics"):
		progress("Synthesizing metric candidates with LLM")
		
		try:
			# Add discovered zoning district
			enhanced_zoning_districts = []
			if zoning_district_info and isinstance(zoning_district_info, dict):
				from .models import ZoningDistrict
				
				# Safely extract values with proper None checks
				zoning_code = zoning_district_info.get('zoning_code') or ''
				zoning_name = zoning_district_info.get('zoning_name') or ''
				overlays = zoning_district_info.get('overlays') or []
				source = zoning_district_info.get('zoning_map_url') or 'Official Zoning Map Analysis'
				
				# Only create district if we have at least a name or code
				if zoning_code or zoning_name:
					discovered_district = ZoningDistrict(
						code=zoning_code,
						name=zoning_name,
						overlays=overlays,
						source=source
					)
					enhanced_zoning_districts = [discovered_district]
					logger.info(f"🎯 Synthesizing metrics for zoning district: {discovered_district.code} - {discovered_district.name}")
				else:
					logger.warning(f"⚠️ Zoning district info found but missing code and name")
					enhanced_zoning_districts = []
			else:
				enhanced_zoning_districts = []
				logger.info(f"🎯 Synthesizing metrics without specific zoning district")
			
			logger.info(f"📊 Documents for synthesis: {len(documents)}")
			logger.info(f"📋 Requested metrics: {requested_metrics}")
			
			extraction = llm_service.synthesize_metrics(
				address=address,
				jurisdiction=geo["jurisdiction"],
				zoning_districts=enhanced_zoning_districts,
				requested_metrics=requested_metrics,
				documents=documents,
			)
			
			logger.info(f"✅ LLM synthesis completed successfully")
			progress("✅ Metrics synthesis completed successfully")
			
		except Exception as e:
			logger.error(f"❌ Error during LLM synthesis: {str(e)}", exc_info=True)
			progress(f"❌ Error during metrics synthesis: {str(e)}")
			raise e

	verified = extraction

	with span(logger, "collect_citations"):
		# Create citation from the official bylaws document only
		citations = [
			{
				"label": official_bylaws_documents[0]['title'],
				"url": official_bylaws_documents[0]['url'],
				"type": "official_bylaws"
			}
		]
		logger.info("citations.source: official_bylaws_only")

	# Prepare final zoning districts output
	final_zoning_districts = enhanced_zoning_districts
	
	# Transform raw LLM data to MetricValue objects with proper filtering
	source_title = official_bylaws_documents[0]['title'] if official_bylaws_documents else "Official Bylaws"
	
	# Define allowed metrics (matching old implementation)
	allowed_parking = {"carParking90Deg", "officesParkingRatio", "drivewayWidth"}
	allowed_zoning = {"minLotArea", "minFrontSetback", "minSideSetback", "minRearSetback", "minLotFrontage", "minLotWidth"}
	
	transformed_zoning_analysis = _transform_to_metric_values(verified.get("zoningAnalysis", {}), source_title, allowed_zoning)
	transformed_parking_summary = _transform_to_metric_values(verified.get("parkingSummary", {}), source_title, allowed_parking)

	output = OutputResult(
		address=address,
		jurisdiction=geo["jurisdiction"],
		zoningDistricts=final_zoning_districts,
		parkingSummary=transformed_parking_summary,
		zoningAnalysis=transformed_zoning_analysis,
		confidence=llm_service.estimate_confidence(verified),
		citations=citations,
		mode="synthesis",
		latencyMs=int((time.time() - start_time) * 1000),
	)
	
	# Add zoning district discovery metadata to output if available
	output_dict = output.model_dump()
	if zoning_district_info:
		output_dict["discoveredZoningDistrict"] = {
			"code": zoning_district_info.get('zoning_code'),
			"name": zoning_district_info.get('zoning_name'),
			"overlays": zoning_district_info.get('overlays', []),
			"sourceUrl": zoning_district_info.get('zoning_map_url'),
			"discoveryMethod": "Official Zoning Map Analysis"
		}
	
	# Add official bylaws source if available
	if official_bylaws_documents:
		output_dict["officialBylawsSource"] = {
			"title": official_bylaws_documents[0]['title'],
			"url": official_bylaws_documents[0]['url'],
			"discoveryMethod": "Official Website Search"
		}
	logger.info("result.latencyMs=%d confidence=%.3f mode=%s", output.latencyMs, output.confidence, output.mode)
	return output_dict
