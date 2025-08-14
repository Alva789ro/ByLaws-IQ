from __future__ import annotations

import os
import urllib.parse
from typing import Dict, Any
import logging
from ..logging_config import configure_logging, span

import httpx
from dotenv import load_dotenv


USER_AGENT = "ByLaws-IQ/0.1 (contact: dev@example.com)"


def geocode_address(address: str) -> Dict[str, Any]:
	configure_logging()
	logger = logging.getLogger("bylaws_iq.geocode")
	try:
		load_dotenv()
	except Exception:
		logger.debug("dotenv.load failed", exc_info=True)

	mapbox = os.getenv("MAPBOX_TOKEN")
	geoapify = os.getenv("GEOAPIFY_KEY")

	if mapbox:
		with span(logger, "mapbox.geocode"):
			data = _geocode_mapbox(address, mapbox)
	elif geoapify:
		with span(logger, "geoapify.geocode"):
			data = _geocode_geoapify(address, geoapify)
	else:
		with span(logger, "nominatim.geocode"):
			data = _geocode_nominatim(address)

	return data


def _geocode_mapbox(address: str, token: str) -> Dict[str, Any]:
	url = (
		"https://api.mapbox.com/geocoding/v5/mapbox.places/"
		+ urllib.parse.quote(address)
		+ f".json?access_token={token}&limit=1"
	)
	with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
		r = client.get(url)
		r.raise_for_status()
		js = r.json()
	if not js.get("features"):
		return _geocode_nominatim(address)
	f = js["features"][0]
	lon, lat = f["center"]
	ctx = f.get("context", [])
	jurisdiction = _parse_mapbox_context(ctx)
	return {"lat": lat, "lon": lon, "jurisdiction": jurisdiction}


def _parse_mapbox_context(ctx):
	city = county = state = None
	for item in ctx:
		tid = item.get("id", "")
		text = item.get("text")
		if tid.startswith("place."):
			city = text
		elif tid.startswith("region."):
			state = text
		elif tid.startswith("district.") or tid.startswith("neighborhood."):
			county = county or text
	return {"city": city, "county": county, "state": state}


def _geocode_geoapify(address: str, key: str) -> Dict[str, Any]:
	url = (
		"https://api.geoapify.com/v1/geocode/search?text="
		+ urllib.parse.quote(address)
		+ f"&apiKey={key}"
	)
	with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
		r = client.get(url)
		r.raise_for_status()
		js = r.json()
	feats = js.get("features", [])
	if not feats:
		return _geocode_nominatim(address)
	props = feats[0]["properties"]
	lat = props.get("lat")
	lon = props.get("lon")
	jurisdiction = {
		"city": props.get("city"),
		"county": props.get("county"),
		"state": props.get("state"),
	}
	return {"lat": lat, "lon": lon, "jurisdiction": jurisdiction}


def _geocode_nominatim(address: str) -> Dict[str, Any]:
	url = "https://nominatim.openstreetmap.org/search"
	params = {"q": address, "format": "json", "limit": 1, "addressdetails": 1}
	headers = {"User-Agent": USER_AGENT}
	with httpx.Client(headers=headers, timeout=20) as client:
		r = client.get(url, params=params)
		r.raise_for_status()
		data = r.json()
	if not data:
		raise ValueError("Geocoding failed: no results")
	d = data[0]
	lat = float(d["lat"])
	lon = float(d["lon"])
	addr = d.get("address", {})
	jurisdiction = {
		"city": addr.get("city") or addr.get("town") or addr.get("village"),
		"county": addr.get("county"),
		"state": addr.get("state"),
	}
	return {"lat": lat, "lon": lon, "jurisdiction": jurisdiction}
