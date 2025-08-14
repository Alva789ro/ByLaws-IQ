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

from bylaws_iq.pipeline import run_query

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


def ui_progress(msg: str) -> None:
    progress_area.info(msg)


if st.button("Search (Synthesis)", type="primary"):
    if not address.strip():
        st.warning("Please enter a valid US address.")
        st.stop()

    # requested_metrics is fixed above
    start = time.time()
    result = run_query(address=address, requested_metrics=requested_metrics, on_progress=ui_progress)
    latency_ms = int((time.time() - start) * 1000)

    st.caption(f"Latency: {latency_ms} ms")

    st.subheader("Results")
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
