from __future__ import annotations

from typing import Any, Dict, List
import logging
from ..logging_config import configure_logging, span
from ..models import ZoningDistrict


def discover_zoning_districts(latitude: float, longitude: float, jurisdiction: Dict[str, Any]) -> List[ZoningDistrict]:
	"""
	Legacy function for backward compatibility
	
	NOTE: This function is now deprecated in favor of ZoningMapAgent.find_zoning_district()
	Returns empty list since the comprehensive zoning discovery system has been replaced
	by the more reliable ZoningMapAgent workflow.
	"""
	
	configure_logging()
	logger = logging.getLogger("bylaws_iq.zoning")
	
	logger.warning("⚠️ discover_zoning_districts() is deprecated. Use ZoningMapAgent.find_zoning_district() instead.")
	logger.info(f"📍 Fallback zoning discovery for: {latitude}, {longitude} in {jurisdiction.get('city', 'Unknown')}")
	
	# Return empty list - the new ZoningMapAgent system handles zoning discovery
	# If this fallback is reached, it means the primary system failed
	return []