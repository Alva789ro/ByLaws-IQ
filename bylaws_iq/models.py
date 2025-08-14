from __future__ import annotations

from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class MetricValue(BaseModel):
	value: str
	verified: bool = False
	source: Optional[str] = ""
	quote: Optional[str] = ""
	note: Optional[str] = ""


class Jurisdiction(BaseModel):
	city: Optional[str] = None
	county: Optional[str] = None
	state: Optional[str] = None


class ZoningDistrict(BaseModel):
	name: str
	overlays: List[str] = Field(default_factory=list)
	source: str


class OutputResult(BaseModel):
	address: str
	jurisdiction: Jurisdiction
	zoningDistricts: List[ZoningDistrict]
	parkingSummary: Dict[str, MetricValue] = Field(default_factory=dict)
	zoningAnalysis: Dict[str, MetricValue] = Field(default_factory=dict)
	confidence: float = 0.0
	citations: List[Dict[str, str]] = Field(default_factory=list)
	mode: Literal["synthesis"] = "synthesis"
	latencyMs: int = 0


# Canonical metric keys (strict set as requested)
PARKING_KEYS = [
	"carParking90Deg",
	"officesParkingRatio",  # Ratio required for offices
	"drivewayWidth",
]

ZONING_KEYS = [
	"minLotArea",
	"minFrontSetback",
	"minSideSetback",
	"minRearSetback",
	"minLotFrontage",
	"minLotWidth",
]
