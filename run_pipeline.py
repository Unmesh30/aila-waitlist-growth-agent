#!/usr/bin/env python3
"""
Main pipeline runner.

Orchestrates the complete lead discovery and reply generation workflow:
1. Discovery: Find and score recent travel discussions
2. Drafting: Generate one final reply per selected lead using Ollama
3. Storage: Save leads to database
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

import argparse

if "--demo" in sys.argv:
    # Offline demo: must point settings at the demo database before config is imported.
    from demo import configure_env

    configure_env()

from src.pipeline.discovery_pipeline import run_discovery_pipeline
from src.pipeline.drafting_pipeline import run_drafting_pipeline
from src.storage.repository import LeadRepository
from src.utils.logger import get_logger
from config.settings import MAX_LEADS_TO_DRAFT, DEFAULT_MAX_POSTS_TO_ENRICH, TARGET_FINAL_LEADS, TEST_MODE

logger = get_logger(__name__)


def main():
    """Run the complete pipeline."""
    parser = argparse.ArgumentParser(description="Aila Waitlist Agent - Lead Discovery Pipeline")

    parser.add_argument(
        "--skip-comments",
        action="store_true",
        help="Skip fetching comments (faster but less context)",
    )

    parser.add_argument(
        "--skip-drafting",
        action="store_true",
        help="Skip reply generation (discovery only)",
    )

    parser.add_argument(
        "--max-drafts",
        type=int,
        default=MAX_LEADS_TO_DRAFT,
        help=f"Maximum number of leads to generate replies for (default: {MAX_LEADS_TO_DRAFT})",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run offline on bundled sample data (no Reddit, X, search or Ollama calls)",
    )

    parser.add_argument(
        "--max-comments",
        type=int,
        default=DEFAULT_MAX_POSTS_TO_ENRICH,
        help=f"Maximum number of posts to enrich with comments (default: {DEFAULT_MAX_POSTS_TO_ENRICH})",
    )

    args = parser.parse_args()

    if args.demo:
        from demo import install_stubs, reset_database

        install_stubs()
        reset_database()
        logger.info("DEMO MODE: bundled sample data, stub model, no network calls")

    logger.info("=" * 80)
    logger.info("AILA WAITLIST AGENT - PIPELINE START")
    logger.info("=" * 80)
    if TEST_MODE:
        logger.info("TEST MODE ACTIVE")
        logger.info(f"Target: {TARGET_FINAL_LEADS}")
    logger.info(f"Overnight target: {TARGET_FINAL_LEADS} selected opportunities with one reply each")

    try:
        # Step 1: Discovery
        top_leads = run_discovery_pipeline(
            enrich_comments=not args.skip_comments,
            max_posts_to_enrich=args.max_comments,
        )

        if not top_leads:
            logger.warning("No qualified leads found. Exiting.")
            return 0

        # Step 2: Drafting (optional)
        if not args.skip_drafting:
            top_leads = run_drafting_pipeline(
                top_leads,
                max_leads_to_draft=args.max_drafts,
            )
        else:
            logger.info("Skipping reply generation (--skip-drafting)")

        # Step 3: Save to database
        logger.info("\n" + "=" * 60)
        logger.info("SAVING TO DATABASE")
        logger.info("=" * 60)

        repository = LeadRepository()
        new_count = repository.save_discovered_leads(top_leads)

        logger.info(f"Saved {new_count} new leads to database")
        logger.info(f"Database location: {repository.db.db_path}")

        # Print stats
        stats = repository.get_statistics()
        logger.info(f"\nDatabase Stats:")
        logger.info(f"  Total leads: {stats['total_leads']}")
        logger.info(f"  Avg score: {stats['avg_lead_score']:.1f}")

        repository.close()

        logger.info("\n" + "=" * 80)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 80)
        logger.info("\nNext steps:")
        logger.info("  1. Review leads in dashboard: python3 launch_dashboard.py" + (" --demo" if args.demo else ""))
        logger.info("  2. Approve leads you want to reply to")
        logger.info("  3. Manually post approved replies to Reddit")

        return 0

    except KeyboardInterrupt:
        logger.info("\n\nPipeline interrupted by user")
        return 1

    except Exception as e:
        logger.error(f"\n\nPipeline failed with error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
