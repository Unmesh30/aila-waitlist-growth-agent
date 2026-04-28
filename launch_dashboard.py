#!/usr/bin/env python3
"""
Dashboard launcher.

Launches the Streamlit dashboard for lead review.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    """Launch the Streamlit dashboard."""
    app_path = Path(__file__).parent / "app" / "streamlit_app.py"

    print("=" * 60)
    print("AILA WAITLIST AGENT - DASHBOARD")
    print("=" * 60)
    print(f"\nLaunching dashboard at: http://localhost:8501")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60)

    # Launch Streamlit
    os.system(f"streamlit run {app_path}")


if __name__ == "__main__":
    main()
