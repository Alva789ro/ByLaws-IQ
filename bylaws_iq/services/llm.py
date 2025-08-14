from __future__ import annotations

import re
from typing import Any, Dict, List
import logging
from ..logging_config import configure_logging, span

from ..models import MetricValue, Jurisdiction, ZoningDistrict
import os
from dotenv import load_dotenv
import httpx


def _value_quote_consistent(value_text: str, quote_text: str) -> bool:
	if not value_text or not quote_text:
		return False
	# Check for shared numeric tokens
	nums = re.findall(r"\d+(?:\.\d+)?", value_text)
	if any(n in quote_text for n in nums if n):
		return True
	# Fallback: shared keywords >= 4 chars
	tokens = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", value_text)]
	return any(tok in quote_text.lower() for tok in tokens)


def verify_metrics(extraction: Dict[str, Dict[str, MetricValue]]) -> Dict[str, Dict[str, MetricValue]]:
	configure_logging()
	logger = logging.getLogger("bylaws_iq.llm")
	with span(logger, "verify.metrics.local"):
		verified: Dict[str, Dict[str, MetricValue]] = {"parkingSummary": {}, "zoningAnalysis": {}}
		for section in ["parkingSummary", "zoningAnalysis"]:
			for key, mv in extraction.get(section, {}).items():
				mv.verified = bool(mv.source and mv.quote and _value_quote_consistent(mv.value, mv.quote))
				verified[section][key] = mv
		logger.info(
			"verification.summary: parking=%d zoning=%d",
			len(verified.get("parkingSummary", {})),
			len(verified.get("zoningAnalysis", {})),
		)
		return verified


def _openrouter_request(model: str, system: str, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
	load_dotenv()
	api_key = os.getenv("OPENROUTER_API_KEY")
	if not api_key:
		raise RuntimeError("OPENROUTER_API_KEY not set")
	headers = {
		"Authorization": f"Bearer {api_key}",
		"HTTP-Referer": "https://bylaws-iq.local",
		"X-Title": "ByLaws-IQ",
		"Content-Type": "application/json",
	}
	payload = {
		"model": model,
		"temperature": temperature,
		"messages": messages,
		"response_format": {"type": "json_object"},
	}
	with httpx.Client(timeout=60) as client:
		r = client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
		r.raise_for_status()
		js = r.json()
	return js["choices"][0]["message"]["content"]


def synth_prompt(address: str, jurisdiction: Jurisdiction, districts: List[ZoningDistrict], requested_metrics: List[str], documents: List[Dict[str, str]]) -> List[Dict[str, str]]:
	sys = (
		"You are a Zoning Analyst / Zoning Research Analyst. Extract only these metrics and nothing else: "
		"Parking Summary: carParking90Deg, officesParkingRatio, drivewayWidth. "
		"Zoning Analysis: minLotArea, minFrontSetback, minSideSetback, minRearSetback, minLotFrontage, minLotWidth. "
		"Always respond in strict JSON with exactly two top-level keys: 'parkingSummary' and 'zoningAnalysis'. "
		"Each metric key must be present if requested, with an object {value, verified, source, quote, note}. "
		"Use direct quotes from the provided documents and include the precise source URL. If uncertain, set value='Unknown' and leave quote empty."
	)
	doc_lines = []
	for d in documents:
		doc_lines.append(f"Source: {d.get('title','')} | URL: {d.get('url','')}\n{d.get('excerpt','')}")
	user = (
		f"Address: {address}\n"
		f"Jurisdiction: {jurisdiction.model_dump()}\n"
		f"Districts: {[dd.model_dump() for dd in districts]}\n"
		f"Requested: {requested_metrics}\n"
		"Documents:\n" + "\n\n".join(doc_lines)
	)
	return [
		{"role": "system", "content": sys},
		{"role": "user", "content": user},
	]


def synthesize_metrics(
	address: str,
	jurisdiction: Dict[str, Any],
	zoning_districts: List[ZoningDistrict],
	requested_metrics: List[str],
	documents: List[Dict[str, str]],
) -> Dict[str, Dict[str, MetricValue]]:
	configure_logging()
	logger = logging.getLogger("bylaws_iq.llm")
	load_dotenv()
	model = os.getenv("BLIQ_SYNTH_MODEL", "google/gemini-2.5-pro")
	with span(logger, "llm.synthesize"):
		try:
			messages = synth_prompt(
				address,
				Jurisdiction(**jurisdiction),
				zoning_districts,
				requested_metrics,
				documents,
			)
			content = _openrouter_request(model=model, system=messages[0]["content"], messages=messages)
		except Exception:
			logger.debug("llm.synthesis.failed", exc_info=True)
			return {"parkingSummary": {}, "zoningAnalysis": {}}

	# Parse JSON response
	import json
	try:
		data = json.loads(content)
	except Exception:
		logger.debug("llm.json.parse.failed: %s", content[:400], exc_info=True)
		return {"parkingSummary": {}, "zoningAnalysis": {}}

	def to_mv(obj: Dict[str, Any]) -> MetricValue:
		return MetricValue(
			value=str(obj.get("value", "Unknown")),
			verified=False,
			source=obj.get("source") or "",
			quote=obj.get("quote") or "",
			note=obj.get("note") or "",
		)

	allowed_parking = {"carParking90Deg", "officesParkingRatio", "drivewayWidth"}
	allowed_zoning = {"minLotArea", "minFrontSetback", "minSideSetback", "minRearSetback", "minLotFrontage", "minLotWidth"}
	parking = {k: to_mv(v) for k, v in (data.get("parkingSummary") or {}).items() if k in allowed_parking}
	zoning = {k: to_mv(v) for k, v in (data.get("zoningAnalysis") or {}).items() if k in allowed_zoning}

	logger.info("llm.synthesize.results: parking=%d zoning=%d", len(parking), len(zoning))
	return {"parkingSummary": parking, "zoningAnalysis": zoning}


def estimate_confidence(data: Dict[str, Dict[str, MetricValue]]) -> float:
	total = 0
	good = 0
	for section in ["parkingSummary", "zoningAnalysis"]:
		for mv in data.get(section, {}).values():
			total += 1
			if mv.verified:
				good += 1
	return round(good / total, 3) if total else 0.0
