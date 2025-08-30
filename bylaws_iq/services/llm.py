from __future__ import annotations

import os
import json
import logging
import httpx
from typing import Dict, List, Optional, Any
from ..logging_config import configure_logging, span

logger = logging.getLogger(__name__)


def synthesize_metrics(
    address: str,
    jurisdiction: Dict[str, Any], 
    zoning_districts: List[Any],
    requested_metrics: List[str],
    documents: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Synthesize zoning metrics from documents using LLM analysis
    
    Args:
        address: The address being analyzed
        jurisdiction: Jurisdiction information (city, state, etc.)
        zoning_districts: List of zoning districts for the address
        requested_metrics: List of metrics to extract
        documents: List of document dictionaries with content and metadata
        
    Returns:
        Dict containing extracted metrics with parkingSummary and zoningAnalysis keys
    """
    try:
        with span(logger, "llm_synthesis"):
            logger.info(f"🤖 Starting LLM synthesis for {address}")
            logger.info(f"📍 Jurisdiction: {jurisdiction}")
            logger.info(f"🏘️ Zoning districts: {len(zoning_districts)}")
            logger.info(f"📋 Requested metrics: {requested_metrics}")
            logger.info(f"📄 Documents: {len(documents)}")
            
            # Prepare document content
            document_content = ""
            for i, doc in enumerate(documents):
                content = doc.get('content', '')
                title = doc.get('title', f'Document {i+1}')
                document_content += f"\n\n=== {title} ===\n{content}"
            
            # Prepare zoning context
            zoning_context = ""
            if zoning_districts:
                for district in zoning_districts:
                    if hasattr(district, 'code') and hasattr(district, 'name'):
                        zoning_context += f"Zoning District: {district.code} - {district.name}\n"
                    elif isinstance(district, dict):
                        code = district.get('code', '')
                        name = district.get('name', '')
                        zoning_context += f"Zoning District: {code} - {name}\n"
            
            # Create LLM prompt following the expected structure
            prompt = f"""You are a zoning law expert. Analyze the provided zoning documents to extract specific metrics for the address: {address}

Address: {address}
Jurisdiction: {jurisdiction.get('city', '')}, {jurisdiction.get('state', '')}
{zoning_context}

Requested Metrics: {', '.join(requested_metrics)}

Extract ONLY the following specific numeric/measurable zoning metrics from the documents:

PARKING METRICS (for parkingSummary):
- carParking90Deg: Parking space dimensions for 90-degree parking
- officesParkingRatio: Required parking spaces per square foot for offices  
- drivewayWidth: Minimum driveway width requirement

ZONING METRICS (for zoningAnalysis):
- minLotArea: Minimum lot area requirement (sq ft or acres)
- minFrontSetback: Minimum front yard setback (feet)
- minSideSetback: Minimum side yard setback (feet) 
- minRearSetback: Minimum rear yard setback (feet)
- minLotFrontage: Minimum lot frontage requirement (feet)
- minLotWidth: Minimum lot width requirement (feet)

Documents to analyze:
{document_content}

Return ONLY metrics that are explicitly found with specific values. For each metric, provide:
- value: The specific numeric value with units (e.g., "25 feet", "5000 sq ft", "2 spaces per 1000 sq ft")
- quote: Direct quote from the source document showing this requirement
- source: Document name or section reference
- note: Any additional context or conditions

Return your analysis as a JSON object with this EXACT structure:
{{
    "parkingSummary": {{
        "carParking90Deg": {{"value": "9x18 feet", "quote": "direct quote", "source": "section reference", "note": "context"}},
        "officesParkingRatio": {{"value": "1 space per 300 sq ft", "quote": "direct quote", "source": "section reference", "note": "context"}},
        "drivewayWidth": {{"value": "12 feet", "quote": "direct quote", "source": "section reference", "note": "context"}}
    }},
    "zoningAnalysis": {{
        "minLotArea": {{"value": "5000 sq ft", "quote": "direct quote", "source": "section reference", "note": "context"}},
        "minFrontSetback": {{"value": "25 feet", "quote": "direct quote", "source": "section reference", "note": "context"}},
        "minSideSetback": {{"value": "10 feet", "quote": "direct quote", "source": "section reference", "note": "context"}},
        "minRearSetback": {{"value": "30 feet", "quote": "direct quote", "source": "section reference", "note": "context"}},
        "minLotFrontage": {{"value": "75 feet", "quote": "direct quote", "source": "section reference", "note": "context"}},
        "minLotWidth": {{"value": "75 feet", "quote": "direct quote", "source": "section reference", "note": "context"}}
    }}
}}

IMPORTANT: 
- Only include metrics where you find explicit numeric requirements
- Do NOT include general analysis or district information
- Do NOT make up values - only use what's explicitly stated in the documents
- If a metric is not found, do not include that key in the response"""

            # Call LLM API
            result = _call_openrouter_llm(prompt)
            
            if result:
                logger.info("✅ LLM synthesis completed successfully")
                return result
            else:
                logger.warning("⚠️ LLM synthesis returned empty result")
                return _create_empty_result()
                
    except Exception as e:
        logger.error(f"❌ LLM synthesis failed: {str(e)}", exc_info=True)
        return _create_empty_result()


def estimate_confidence(verified_data: Dict[str, Any]) -> float:
    """
    Estimate confidence score for the verified data
    
    Args:
        verified_data: Dictionary containing the synthesized metrics and analysis
        
    Returns:
        Float confidence score between 0.0 and 1.0
    """
    try:
        # Extract confidence from the LLM response if available
        if isinstance(verified_data, dict):
            if 'confidence' in verified_data:
                return float(verified_data['confidence'])
            
            # Calculate confidence based on available metrics in both categories
            parking_metrics = verified_data.get('parkingSummary', {})
            zoning_metrics = verified_data.get('zoningAnalysis', {})
            
            total_metrics = len(parking_metrics) + len(zoning_metrics)
            if total_metrics == 0:
                return 0.0
            
            # Count metrics with actual values (not "Not specified")
            valid_metrics = 0
            
            for metric_data in list(parking_metrics.values()) + list(zoning_metrics.values()):
                if isinstance(metric_data, dict):
                    value = metric_data.get('value', '')
                    if value and value != "Not specified" and value.strip():
                        valid_metrics += 1
                elif metric_data and str(metric_data) != "Not specified":
                    valid_metrics += 1
            
            # Base confidence on percentage of found metrics
            base_confidence = valid_metrics / max(1, total_metrics)
            
            # Boost confidence if we have both parking and zoning metrics
            if parking_metrics and zoning_metrics:
                base_confidence = min(0.95, base_confidence + 0.1)
            
            return round(base_confidence, 2)
        
        return 0.5  # Default moderate confidence
        
    except Exception as e:
        logger.error(f"❌ Confidence estimation failed: {str(e)}", exc_info=True)
        return 0.3  # Low confidence on error


def _call_openrouter_llm(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Call OpenRouter API for LLM analysis
    
    Args:
        prompt: The prompt to send to the LLM
        
    Returns:
        Parsed JSON response or None on failure
    """
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("❌ OPENROUTER_API_KEY not found in environment variables")
            return None
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-org/bylaws-iq",
            "X-Title": "Bylaws-IQ"
        }
        
        payload = {
            "model": "google/gemini-2.5-pro",  # Using stable Gemini model
            "messages": [
                {"role": "system", "content": "You are a zoning law expert specializing in municipal zoning code analysis. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 4000,
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        logger.info("🌐 Calling OpenRouter API for LLM analysis...")
        
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                # Parse JSON response
                try:
                    result = json.loads(content)
                    logger.info("✅ Successfully parsed LLM JSON response")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Failed to parse LLM JSON response: {e}")
                    logger.error(f"Raw content: {content}")
                    return None
            else:
                logger.error(f"❌ OpenRouter API error: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"❌ OpenRouter API call failed: {str(e)}", exc_info=True)
        return None


def _create_empty_result() -> Dict[str, Any]:
    """Create an empty result structure for fallback"""
    return {
        "parkingSummary": {},
        "zoningAnalysis": {}
    }