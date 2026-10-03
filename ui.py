"""Optional Streamlit UI for the autonomous worker."""

from __future__ import annotations

import asyncio

import streamlit as st

from agent.config import get_settings, reset_settings
from agent.loop import run

st.set_page_config(page_title="Nexora AI Worker", page_icon="⚙", layout="centered")
st.title("Nexora Autonomous AI Worker")
st.caption("Narrow prototype — real tools against the local mock company app.")

task = st.text_area(
    "Task",
    value=(
        "Find the latest invoice from Acme Corp in the mail app, extract amount and "
        "due date, enter it into the finance system, and confirm it's saved."
    ),
    height=120,
)

if st.button("Run agent", type="primary"):
    reset_settings()
    settings = get_settings()
    with st.spinner("Agent running..."):
        result = asyncio.run(run(task, settings=settings))
    st.subheader(f"Status: {result.status}")
    st.write(result.summary)
    if result.verification:
        st.write(
            "Verification:",
            "passed" if result.verification.passed else "failed",
            result.verification.checks,
        )
    st.json(result.model_dump(mode="json"))
