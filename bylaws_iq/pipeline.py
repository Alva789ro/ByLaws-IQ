from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Callable

from .models import OutputResult
from .logging_config import configure_logging, span
import logging
from .services import geocode as geocode_service
from .services import zoning as zoning_service
from .services import search as search_service
from .services import scrape as scrape_service
from .services import llm as llm_service


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

	with span(logger, "discover_zoning"):
		progress("Discovering zoning districts")
		zoning_districts = zoning_service.discover_zoning_districts(
			latitude=geo["lat"], longitude=geo["lon"], jurisdiction=geo["jurisdiction"]
		)

	allowlist = [".gov", ".us", "municode.com", "ecode360.com", "arcgis.com", "mapgeo.io"]

	with span(logger, "search_documents"):
		progress("Searching recent municipal code sources")
		search_results = search_service.search_documents(
			query=(
				f"zoning code parking setbacks height "
				f"{geo['jurisdiction'].get('city','')} {geo['jurisdiction'].get('state','')}"
			),
			allowed_domains=allowlist,
		)

	with span(logger, "fetch_and_prepare_docs"):
		progress("Fetching and preparing source documents")
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
		progress("Synthesizing metric candidates with LLM")
		extraction = llm_service.synthesize_metrics(
			address=address,
			jurisdiction=geo["jurisdiction"],
			zoning_districts=zoning_districts,
			requested_metrics=requested_metrics,
			documents=documents,
		)

	verified = extraction

	with span(logger, "collect_citations"):
		citations = search_service.collect_citations(search_results)

	output = OutputResult(
		address=address,
		jurisdiction=geo["jurisdiction"],
		zoningDistricts=zoning_districts,
		parkingSummary=verified.get("parkingSummary", {}),
		zoningAnalysis=verified.get("zoningAnalysis", {}),
		confidence=llm_service.estimate_confidence(verified),
		citations=citations,
		mode="synthesis",
		latencyMs=int((time.time() - start_time) * 1000),
	)
	logger.info("result.latencyMs=%d confidence=%.3f mode=%s", output.latencyMs, output.confidence, output.mode)
	return output.model_dump()
