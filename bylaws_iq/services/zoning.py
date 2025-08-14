from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import logging
from ..logging_config import configure_logging, span
from . import scrape

from ..models import MetricValue, ZoningDistrict, PARKING_KEYS, ZONING_KEYS


def discover_zoning_districts(latitude: float, longitude: float, jurisdiction: Dict[str, Any]) -> List[ZoningDistrict]:
	configure_logging()
	logger = logging.getLogger("bylaws_iq.zoning")
	with span(logger, "zoning.discover"):
		city = jurisdiction.get("city") or "Unknown City"
		district = ZoningDistrict(
			name=f"General District - {city}", overlays=[], source="https://example.com/zoning-map"
		)
		return [district]


def _snippet(text: str, start: int, end: int, pad: int = 120) -> str:
	s = max(0, start - pad)
	e = min(len(text), end + pad)
	snippet = text[s:e].strip()
	return " ".join(snippet.split())


def _find_front_setback(text: str) -> Optional[Tuple[str, str]]:
	import re

	patterns = [
		r"min(?:imum)?\s+front(?:yard)?\s+setback[s]?[^^\d]{0,40}?(\d{1,3})\s*(?:feet|ft)",
		r"front(?:yard)?\s+setback[s]?[^^\d]{0,40}?(\d{1,3})\s*(?:feet|ft)",
	]
	for pat in patterns:
		m = re.search(pat, text, flags=re.IGNORECASE)
		if m:
			value = f"{m.group(1)} ft"
			return value, _snippet(text, m.start(1), m.end(1))
	return None


def _find_rd_ratio(text: str) -> Optional[Tuple[str, str]]:
	import re

	pats = [
		r"office[^\n]{0,120}?1\s*/\s*(\d{2,4})",
		r"parking[^\n]{0,120}?1\s*/\s*(\d{2,4})\s*(?:sq\.?\s*ft|square\s*feet|sf|gfa)",
	]
	for pat in pats:
		m = re.search(pat, text, flags=re.IGNORECASE)
		if m:
			denom = m.group(1)
			value = f"1/{denom} GFA"
			return value, _snippet(text, m.start(1), m.end(1))
	return None


def _find_car_90(text: str) -> Optional[Tuple[str, str]]:
	import re

	stall = re.search(r"(9)\s*[x×]\s*(18)\s*(?:feet|ft)?", text, flags=re.IGNORECASE)
	aisle = re.search(r"aisle[s]?[^^\d]{0,20}?(\d{2})\s*(?:feet|ft)", text, flags=re.IGNORECASE)
	if stall and aisle:
		value = f"9x18 ft; {aisle.group(1)} ft aisles"
		start = min(stall.start(1), aisle.start(1))
		end = max(stall.end(2), aisle.end(1))
		return value, _snippet(text, start, end)
	if stall:
		value = "9x18 ft"
		return value, _snippet(text, stall.start(1), stall.end(2))
	return None


def extract_metrics(
	zoning_districts: List[ZoningDistrict],
	search_results: List[Dict[str, Any]],
	requested_metrics: List[str],
) -> Dict[str, Dict[str, MetricValue]]:
	configure_logging()
	logger = logging.getLogger("bylaws_iq.zoning")
	with span(logger, "zoning.extract"):
		parking: Dict[str, MetricValue] = {}
		zoning: Dict[str, MetricValue] = {}

		for key in requested_metrics:
			found: Optional[MetricValue] = None
			for item in search_results:
				url = item.get("url")
				if not url:
					continue
				try:
					html = scrape.fetch_html(url)
					if not html:
						continue
					text = scrape.parse_text_from_html(html)
				except Exception:
					logger.debug("scrape.failed: %s", url, exc_info=True)
					continue

				if key == "minFrontSetback":
					res = _find_front_setback(text)
				elif key == "officesParkingRatio":
					res = _find_rd_ratio(text)
				elif key == "carParking90Deg":
					res = _find_car_90(text)
				else:
					res = None

				if res:
					value, quote = res
					found = MetricValue(value=value, verified=False, source=url, quote=quote, note="heuristic parse")
					break

			if key in PARKING_KEYS:
				parking[key] = found or MetricValue(value="Unknown", verified=False, source="", quote="", note="not found")
			elif key in ZONING_KEYS:
				zoning[key] = found or MetricValue(value="Unknown", verified=False, source="", quote="", note="not found")

		logger.info("extracted.metrics: parking=%d zoning=%d", len(parking), len(zoning))
		return {"parkingSummary": parking, "zoningAnalysis": zoning}
