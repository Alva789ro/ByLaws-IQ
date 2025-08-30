import sys
import pathlib
import json
import time
from typing import List

import streamlit as st
from dotenv import load_dotenv

# Ensure root is on sys.path so `bylaws_iq` is importable when running via Streamlit
project_root = pathlib.Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from bylaws_iq.pipeline import run_query, run_query_fallback

load_dotenv()
st.set_page_config(page_title="ByLaws-IQ", layout="wide")

st.title("ByLaws-IQ — Zoning By-Laws AI Search")

address = st.text_input("US Address", placeholder="55 Constitution Blvd, Franklin, MA")

st.subheader("Metrics (fixed)")
st.caption("Parking Summary: Car parking 90°; Ratio required for offices; Driveway width. Zoning Analysis: Required minimum lot area; Minimum front/side/rear setbacks; Minimum lot frontage; Minimum lot width.")
requested_metrics = [
    # Parking Summary
    "carParking90Deg",
    "officesParkingRatio",
    "drivewayWidth",
    # Zoning Analysis
    "minLotArea",
    "minFrontSetback",
    "minSideSetback",
    "minRearSetback",
    "minLotFrontage",
    "minLotWidth",
]

progress_area = st.empty()
zoning_display_area = st.empty()


def ui_progress(msg: str) -> None:
    progress_area.info(msg)
    
    # Special handling for zoning district discovery results
    if "Found zoning district:" in msg:
        zoning_info = msg.replace("✅ Found zoning district: ", "").strip()
        zoning_display_area.success(f"🗺️ **Zoning District Discovered:** {zoning_info}")
    elif "Zoning district discovery failed" in msg:
        zoning_display_area.warning("⚠️ **Zoning District:** Could not determine from official sources")
    elif "Discovering official bylaws for district" in msg:
        zoning_display_area.info("📋 **Finding Official Bylaws...**")
    elif "Found official bylaws:" in msg:
        zoning_display_area.success("✅ **Official Bylaws Found**")
    elif "Could not find official bylaws for" in msg:
        zoning_display_area.warning("⚠️ **Bylaws:** Could not find official bylaws")
    elif "Adding official bylaws to document analysis" in msg:
        zoning_display_area.info("🔍 **Analyzing Official Bylaws for Metrics...**")
    elif "Using official bylaws document only" in msg:
        zoning_display_area.success("🎯 **Using Official Document Only**")
    elif "Primary method failed" in msg:
        zoning_display_area.warning("⚠️ **Primary Method Failed**")
    elif "Using fallback:" in msg:
        zoning_display_area.info("🔄 **Using Fallback Method**")
    elif "Accessing official document (may try multiple strategies)" in msg:
        zoning_display_area.info("🔄 **Accessing PDF (trying multiple strategies)...**")
    elif "Successfully accessed official document" in msg:
        zoning_display_area.success("✅ **PDF Access Successful**")
    elif "Extracted" in msg and "characters from official document" in msg:
        zoning_display_area.success("✅ **Document Processed Successfully**")


# Initialize session state for fallback handling
if 'fallback_data' not in st.session_state:
    st.session_state.fallback_data = None
if 'show_fallback_choice' not in st.session_state:
    st.session_state.show_fallback_choice = False

# Handle fallback permission choice
if st.session_state.show_fallback_choice and st.session_state.fallback_data:
    st.warning("⚠️ **Primary Method Failed**")
    st.write(st.session_state.fallback_data["message"])
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("✅ Continue with Fallback", type="primary"):
            st.session_state.show_fallback_choice = False
            progress_area.info("🔄 Using fallback search method...")
            
            # Run fallback query
            start = time.time()
            result = run_query_fallback(
                address=st.session_state.fallback_data["address"],
                requested_metrics=st.session_state.fallback_data["requested_metrics"],
                zoning_district_info=st.session_state.fallback_data.get("zoning_district_info"),
                geo=st.session_state.fallback_data.get("geo"),
                on_progress=ui_progress
            )
            latency_ms = int((time.time() - start) * 1000)
            
            st.caption(f"Latency: {latency_ms} ms (Fallback Method)")
            st.session_state.fallback_data = None
            
            # Display fallback results
            st.info("🔄 **Results from Fallback Method** - These may be less accurate than our primary method.")
            
            # Continue with normal result display logic below
    
    with col2:
        if st.button("❌ Stop", type="secondary"):
            st.session_state.show_fallback_choice = False
            st.session_state.fallback_data = None
            st.error("😔 **We're sorry we couldn't help you this time.**")
            st.write("Our primary method couldn't find the official bylaws document for your address. Please try again later or contact support.")
            st.stop()

else:
    if st.button("Search (Synthesis)", type="primary"):
        if not address.strip():
            st.warning("Please enter a valid US address.")
            st.stop()

        # requested_metrics is fixed above
        start = time.time()
        result = run_query(address=address, requested_metrics=requested_metrics, on_progress=ui_progress)
        
        # Check if we need fallback permission
        if isinstance(result, dict) and result.get("status") == "fallback_permission_required":
            st.session_state.fallback_data = result
            st.session_state.show_fallback_choice = True
            st.rerun()
        
        latency_ms = int((time.time() - start) * 1000)
        st.caption(f"Latency: {latency_ms} ms")

# Only display results if we have them and we're not in fallback choice mode
if not st.session_state.show_fallback_choice and 'result' in locals() and isinstance(result, dict) and result.get("status") != "fallback_permission_required":
    # Display discovered zoning district prominently if available
    if "discoveredZoningDistrict" in result and result["discoveredZoningDistrict"]["code"]:
        zoning_info = result["discoveredZoningDistrict"]
        st.subheader("🗺️ Discovered Zoning District")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Zoning Code", zoning_info["code"])
            st.metric("Discovery Method", zoning_info["discoveryMethod"])
        with col2:
            st.metric("Zoning Name", zoning_info["name"])
            if zoning_info["overlays"]:
                st.write("**Overlays:**", ", ".join(zoning_info["overlays"]))
        
        if zoning_info["sourceUrl"]:
            st.markdown(f"**Source:** [Official Zoning Map]({zoning_info['sourceUrl']})")
        
        st.divider()

    # Display official bylaws source if available
    if "officialBylawsSource" in result and result["officialBylawsSource"]:
        bylaws_source = result["officialBylawsSource"]
        st.subheader("📋 Official Bylaws Source")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Document", bylaws_source["title"])
        with col2:
            st.metric("Discovery Method", bylaws_source["discoveryMethod"])
        
        st.markdown(f"**Source:** [Official Bylaws Document]({bylaws_source['url']})")
        st.info("✅ **Metrics analysis used this official document as the primary source**")
        
        st.divider()

    st.subheader("Metrics Results")
    st.code(json.dumps(result, indent=2), language="json")

    st.write("\n")
    st.download_button(
        "Export JSON",
        data=json.dumps(result, indent=2),
        file_name="bylaws_iq_result.json",
        mime="application/json",
    )

    if result.get("citations"):
        st.write("Citations:")
        for c in result["citations"]:
            st.markdown(f"- [{c.get('label','Source')}]({c.get('url')})")
        st.button("Copy citations", on_click=lambda: st.write("Copied above list."))
