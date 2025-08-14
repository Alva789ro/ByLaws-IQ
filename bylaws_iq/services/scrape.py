from __future__ import annotations

from typing import Optional, Tuple
import logging
from ..logging_config import configure_logging, span

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from pdfminer.high_level import extract_text as pdf_extract_text


HEADERS = {"User-Agent": "ByLaws-IQ/0.1 (contact: dev@example.com)"}


@retry(wait=wait_exponential(multiplier=0.5, min=1, max=8), stop=stop_after_attempt(3))
def fetch(url: str, timeout: int = 30) -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
	"""Fetch a URL and return (text, content_bytes, content_type).

	- For HTML we return text and raw bytes
	- For PDFs we return (None, bytes, 'application/pdf')
	"""
	configure_logging()
	logger = logging.getLogger("bylaws_iq.scrape")
	with span(logger, "http.get"):
		r = requests.get(url, headers=HEADERS, timeout=timeout)
		r.raise_for_status()
		ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
		logger.info("http.status: %s %s", r.status_code, url)
		if ctype.startswith("text/") or "html" in ctype:
			return r.text, r.content, ctype
		return None, r.content, ctype or None


@retry(wait=wait_exponential(multiplier=0.5, min=1, max=8), stop=stop_after_attempt(3))
def fetch_html(url: str, timeout: int = 20) -> Optional[str]:
	configure_logging()
	logger = logging.getLogger("bylaws_iq.scrape")
	with span(logger, "http.get"):
		r = requests.get(url, headers=HEADERS, timeout=timeout)
		r.raise_for_status()
		logger.info("http.status: %s %s", r.status_code, url)
		return r.text


def parse_text_from_html(html: str) -> str:
	soup = BeautifulSoup(html, "lxml")
	for tag in soup(["script", "style", "noscript"]):
		tag.decompose()
	return soup.get_text(" ", strip=True)


def try_extract_pdf_text(url: str, content_bytes: bytes) -> Optional[str]:
	if not url.lower().endswith(".pdf"):
		return None
	try:
		from io import BytesIO

		return pdf_extract_text(BytesIO(content_bytes))
	except Exception:
		return None
