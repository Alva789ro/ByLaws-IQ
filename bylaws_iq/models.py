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


# Legacy ZoningDistrict for backward compatibility
class ZoningDistrict(BaseModel):
	code: str = ""  # Zoning district code (e.g., "R-1", "CB")
	name: str
	overlays: List[str] = Field(default_factory=list)
	source: str


# New detailed zoning models
class Parcel(BaseModel):
	id: str
	geometry_source: str
	notes: str = ""


class ZoneCode(BaseModel):
	code: str
	label: str


class ZoningMap(BaseModel):
	edition: str
	source_url: str


class ZoningCodeVerification(BaseModel):
	verified: bool = False
	amendments_checked: bool = False
	latest_amendment_date: Optional[str] = None


class ZoningEvidence(BaseModel):
	services_checked: List[str] = Field(default_factory=list)
	parcel_layer: Optional[str] = None
	zoning_layer: Optional[str] = None


class DetailedZoning(BaseModel):
	base: List[ZoneCode] = Field(default_factory=list)
	overlays: List[ZoneCode] = Field(default_factory=list)
	map: Optional[ZoningMap] = None


class ZoningResult(BaseModel):
	"""Comprehensive zoning determination result"""
	address: str
	jurisdiction: Jurisdiction
	parcel: Optional[Parcel] = None
	zoning: Optional[DetailedZoning] = None
	zoning_code: Optional[ZoningCodeVerification] = None
	confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
	evidence: Optional[ZoningEvidence] = None
	notes: str = ""


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
