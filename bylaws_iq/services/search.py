from __future__ import annotations

import os
from typing import Any, Dict, List
import logging
from ..logging_config import configure_logging, span

from tavily import TavilyClient  # type: ignore
from dotenv import load_dotenv


def _domain_allowed(url: str, allowed_domains: List[str]) -> bool:
	return any(part in url for part in allowed_domains)


def search_documents(query: str, allowed_domains: List[str]) -> List[Dict[str, Any]]:
	configure_logging()
	logger = logging.getLogger("bylaws_iq.search")
	try:
		load_dotenv()
	except Exception:
		pass
	api_key = os.getenv("TAVILY_API_KEY")
	if not api_key:
		logger.info("tavily.disabled: no API key present")
		return []
	client = TavilyClient(api_key=api_key)
	with span(logger, "tavily.search"):
		res = client.search(query=query, topic="general", include_raw_content=True, max_results=8)
	items = res.get("results", [])
	filtered = [i for i in items if _domain_allowed(i.get("url", ""), allowed_domains)]
	logger.info("tavily.results: total=%d filtered=%d", len(items), len(filtered))
	return filtered


def collect_citations(results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
	citations: List[Dict[str, str]] = []
	for r in results[:6]:
		url = r.get("url")
		title = r.get("title") or "Source"
		if url:
			citations.append({"label": title, "url": url})
	return citations
