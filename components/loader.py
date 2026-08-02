"""
TRadar Full-Viewport Loading Overlay Component
Provides a full-screen fixed overlay loader that covers the viewport during page rendering
and unmounts cleanly once rendering completes.
"""

import streamlit as st

TR_LARGE_SPINNER_SVG = '<svg width="64" height="64" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 20px; display: block; margin-left: auto; margin-right: auto;"><circle cx="12" cy="12" r="9" fill="none" stroke="#1e293b" stroke-width="3"/><circle cx="12" cy="12" r="9" fill="none" stroke="#38bdf8" stroke-width="3" stroke-dasharray="14 42" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.8s" repeatCount="indefinite"/></circle></svg>'


def start_full_screen_loader(title="Loading TRadar Intelligence...", subtitle="Downloading real-time market data & technical indicators..."):
    """
    Mounts a full-screen fixed overlay loader covering 100% of the viewport.
    Returns the st.empty() placeholder object so it can be unmounted via placeholder.empty().
    """
    placeholder = st.empty()
    placeholder.markdown(f"""
    <div style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background-color: #0b0f19; background-image: radial-gradient(circle at 50% 40%, rgba(30, 41, 59, 0.95) 0%, #0b0f19 80%); z-index: 9999999; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; box-sizing: border-box;">
        <div style="background: rgba(15, 23, 42, 0.95); border: 1px solid #334155; border-radius: 20px; padding: 48px 56px; text-align: center; max-width: 540px; width: 90%; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8); backdrop-filter: blur(16px);">
            {TR_LARGE_SPINNER_SVG}
            <h2 style="margin: 0 0 10px 0; font-size: 1.5rem; font-weight: 800; background: linear-gradient(135deg, #38bdf8 0%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                TRadar Intelligence
            </h2>
            <div style="font-size: 1.1rem; font-weight: 700; color: #f8fafc; margin-bottom: 12px;">
                {title}
            </div>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                {subtitle}
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    return placeholder


class TRadarLoader:
    def __init__(self, title="Loading TRadar Intelligence...", subtitle="Downloading real-time price quotes, 50/200-SMA indicators, and candlestick setup history..."):
        self.title = title
        self.subtitle = subtitle
        self.placeholder = None

    def __enter__(self):
        self.placeholder = start_full_screen_loader(self.title, self.subtitle)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.placeholder:
            self.placeholder.empty()


def render_full_screen_loader(title="Loading TRadar Intelligence...", subtitle="Downloading real-time market data..."):
    """Backwards compatible loader function"""
    return TRadarLoader(title=title, subtitle=subtitle)
