"""
NASA VIIRS Nighttime Lights Explorer (VNP46A2)
Run:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Nighttime Lights", page_icon="🌙", layout="wide")

from nightlights.core.reader import load_dataset  # noqa: E402
from ui.kpis import render_kpis  # noqa: E402
from ui.listing import render_listing  # noqa: E402
from ui.sidebar import render_sidebar  # noqa: E402
from ui.tabs import render_tabs  # noqa: E402

st.title("🌙 NASA VIIRS Nighttime Lights")
st.caption("VNP46A2 · daily gap-filled, BRDF-corrected nighttime radiance")

settings = render_sidebar()
render_listing()

if not settings.file_path:
    st.info("Choose a region and date in the sidebar, then click **Fetch from NASA**.")
    st.stop()

try:
    dataset = load_dataset(settings.file_path, settings.layer, settings.step, settings.mask_quality)
except KeyError as e:
    st.error(e.args[0])
    st.stop()
except Exception as e:
    st.error(f"Could not read file: {e}")
    st.stop()

if dataset.valid.size == 0:
    st.warning("No valid pixels with the current settings.")
    st.stop()

render_kpis(dataset, settings)
render_tabs(dataset, settings)
