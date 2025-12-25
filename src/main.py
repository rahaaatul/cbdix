"""Main entry point for CBDIX"""

import argparse
import asyncio

from src.lib.core import check_bdix_connectivity
from src.lib.logging import cli_logger, color_highlight, setup_logging
from src.lib.utils import load_bdix_urls


async def handle_run(args):
    """Handle simplified run command: single comprehensive connectivity test."""
    cli_logger.info("BDIX test Started")
    cli_logger.debug(
        f"handle_run: Arguments - limit={args.limit}, concurrency={args.concurrency}"
    )

    cli_logger.debug("Loading BDIX URLs from data file")
    urls = load_bdix_urls()
    cli_logger.debug(f"Loaded {len(urls)} BDIX URLs from data file")
    if not urls:
        cli_logger.error("No BDIX URLs found in data file")
        return

    if args.limit:
        cli_logger.debug(f"handle_run: Applying limit of {args.limit} URLs")
        urls = urls[: args.limit]
        cli_logger.debug(f"Limited to {args.limit} URLs for testing")

    cli_logger.debug(f"Using concurrency of {args.concurrency} for HTTP connections")

    cli_logger.debug(
        f"Starting connectivity check with {len(urls)} URLs using {args.concurrency} concurrent connections"
    )
    result = await check_bdix_connectivity(urls, concurrency=args.concurrency)
    cli_logger.debug("handle_run: Connectivity check completed")

    cli_logger.info(
        f"Working URLs: {result['working_count']}/{result['total_urls_tested']}"
    )
    cli_logger.info(
        f"Success rate: {color_highlight(f'{result["success_rate"]:.1f}%', 'SUCCESS' if result['success_rate'] == 100.0 else 'WARNING' if result['success_rate'] < 50.0 else 'INFO')}"
    )
    cli_logger.info(f"Unique pingable hosts found: {result['total_hosts']}")

    # Save working URLs to file only if any exist (deduplicated)
    cli_logger.debug("Processing working URLs for file output")
    working_urls_deduped = list(
        set(result["working_urls"])
    )  # Remove any potential duplicates
    cli_logger.debug(
        f"Found {len(working_urls_deduped)} unique working URLs after deduplication"
    )

    if working_urls_deduped:
        import pathlib

        working_urls_file = pathlib.Path("working-urls.txt").resolve()
        cli_logger.debug(f"Writing working URLs to file {working_urls_file}")
        with open("working-urls.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(working_urls_deduped))
        cli_logger.debug("File write operation completed")
        cli_logger.debug(
            f"Saved {len(working_urls_deduped)} working URLs to {working_urls_file}"
        )
    else:
        cli_logger.debug("No working URLs found, skipping file creation")

    # Determine final status
    cli_logger.debug("Evaluating overall connectivity status")
    if result["success_rate"] == 0.0:
        cli_logger.error("No BDIX services are working")
    elif result["success_rate"] < 100.0:
        cli_logger.warning(
            f"{result['working_count']} out of {result['total_urls_tested']} services working"
        )
    else:
        cli_logger.log(25, "All BDIX services are working")


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    cli_logger.debug("create_parser: Creating CLI argument parser")
    parser = argparse.ArgumentParser(
        prog="cbdix",
        description="BDIX Network Connectivity Tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cbdix run                          # Run full connectivity test (quick check + working URLs)
  cbdix run -l 10                    # Limit to first 10 URLs
  cbdix run -c 5                     # Use only 5 concurrent HTTP connections
  cbdix run -l 50 -c 10              # Test 50 URLs with 10 concurrent connections
  cbdix run -v                       # Show detailed debug information
        """,
    )

    cli_logger.debug("create_parser: Adding subparsers for commands")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    cli_logger.debug("create_parser: Creating 'run' subcommand parser")
    run_parser = subparsers.add_parser("run", help="Run connectivity test")
    run_parser.add_argument(
        "-l", "--limit", type=int, default=None, help="Limit number of URLs to test"
    )
    run_parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=20,
        help="Maximum number of concurrent HTTP connections (default: 20)",
    )
    run_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed debug information"
    )

    cli_logger.debug("create_parser: Parser creation completed")
    return parser


async def main():
    """Main CLI entry point."""
    cli_logger.debug("main: Starting CLI application")

    cli_logger.debug("main: Creating argument parser")
    parser = create_parser()
    cli_logger.debug("main: Parsing command line arguments")
    args = parser.parse_args()

    cli_logger.debug(f"main: Parsed command: {args.command}")
    cli_logger.debug(f"main: Verbose mode: {getattr(args, 'verbose', False)}")

    # Setup logging based on verbose flag
    cli_logger.debug("main: Setting up logging configuration")
    setup_logging(verbose=getattr(args, "verbose", False))

    if args.command == "run":
        cli_logger.debug("main: Executing 'run' command")
        await handle_run(args)
        cli_logger.debug("main: 'run' command completed")
    else:
        cli_logger.debug("main: No command specified, showing help")
        parser.print_help()

    cli_logger.debug("main: CLI application execution completed")


def sync_main():
    """Synchronous entry point for CLI."""
    cli_logger.debug("sync_main: Starting synchronous main function")
    cli_logger.debug("sync_main: Running asyncio event loop")
    asyncio.run(main())
    cli_logger.debug("sync_main: Asyncio event loop completed")


if __name__ == "__main__":
    cli_logger.debug("__main__: Script executed directly, calling sync_main()")
    sync_main()
    cli_logger.debug("__main__: Script execution completed")
