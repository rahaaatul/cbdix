"""Core ping functionality with async operations"""

import asyncio

import aiohttp
from icmplib import ICMPLibError, NameLookupError, async_ping

from .logging import color_highlight, success
from .logging import core_logger as logger


async def ping_hosts(hostnames: list[str], timeout: float = 2.0) -> list[dict]:
    """Ping multiple hosts and return results."""
    logger.debug(f"Starting ping sweep: {len(hostnames)} hosts, timeout={timeout}s")
    results = []

    for hostname in hostnames:
        logger.debug(f"Pinging {color_highlight(hostname, 'DEBUG')}")
        result = await _ping_single_host(hostname, timeout)
        results.append(result)
        if result["is_alive"]:
            logger.info(f"Host reachable: {color_highlight(hostname, 'SUCCESS')}")
        else:
            logger.error(f"Host unreachable: {color_highlight(hostname, 'ERROR')}")

    logger.debug(f"Ping sweep complete: {len(results)} hosts processed")
    return results


async def _ping_single_host(hostname: str, timeout: float) -> dict:
    """Ping a single host with error handling."""
    logger.debug(
        f"Attempting ping: {color_highlight(hostname, 'DEBUG')} (timeout={timeout}s)"
    )
    try:
        ping_result = await async_ping(hostname, timeout=timeout, count=3)

        if ping_result.is_alive:
            logger.debug(
                f"Ping successful: {color_highlight(hostname, 'DEBUG')} (RTT: {ping_result.avg_rtt:.2f}ms)"
            )
        else:
            logger.debug(
                f"Ping failed: {color_highlight(hostname, 'DEBUG')} (packet loss: {ping_result.packet_loss}%)"
            )

        return {
            "hostname": hostname,
            "is_alive": ping_result.is_alive,
            "avg_rtt": ping_result.avg_rtt if ping_result.is_alive else None,
            "packet_loss": ping_result.packet_loss,
            "error": None,
        }

    except NameLookupError:
        logger.warning(f"DNS resolution failed: {color_highlight(hostname, 'WARNING')}")
        return {
            "hostname": hostname,
            "is_alive": False,
            "avg_rtt": None,
            "packet_loss": 100.0,
            "error": "DNS resolution failed",
        }

    except ICMPLibError as e:
        logger.error(f"ICMP error for {color_highlight(hostname, 'ERROR')}: {str(e)}")
        return {
            "hostname": hostname,
            "is_alive": False,
            "avg_rtt": None,
            "packet_loss": 100.0,
            "error": str(e),
        }

    except Exception as e:
        logger.error(
            f"Unexpected ping error for {color_highlight(hostname, 'ERROR')}: {str(e)}"
        )
        return {
            "hostname": hostname,
            "is_alive": False,
            "avg_rtt": None,
            "packet_loss": 100.0,
            "error": f"Unexpected error: {str(e)}",
        }


async def quick_check(urls: list[dict], timeout: float = 2.0) -> dict:
    """Fast connectivity check."""
    logger.debug(f"Starting quick connectivity check: {len(urls)} URLs")
    from .utils import get_hostnames_from_urls

    hostnames = get_hostnames_from_urls(urls)
    results = await ping_hosts(hostnames, timeout)

    alive = [r for r in results if r["is_alive"]]
    success_rate = len(alive) / len(results) * 100 if results else 0

    logger.info(
        f"Quick check complete: {len(alive)}/{len(results)} hosts alive ({success_rate:.1f}% success rate)"
    )
    if alive:
        success(f"Found {len(alive)} reachable hosts")
    else:
        logger.warning("No hosts reachable in quick check")

    return {
        "total": len(results),
        "alive": len(alive),
        "success_rate": success_rate,
        "results": results,
    }


async def find_working_urls(urls: list[dict], timeout: float = 2.0) -> list[str]:
    """Find working URLs."""
    logger.debug(f"Finding working URLs: checking {len(urls)} URLs")
    from .utils import get_hostnames_from_urls

    hostnames = get_hostnames_from_urls(urls)
    results = await ping_hosts(hostnames, timeout)

    working_urls = []
    for url_data, result in zip(urls, results, strict=True):
        if result["is_alive"]:
            working_urls.append(url_data["url"])

    logger.info(f"Found {len(working_urls)} working URLs out of {len(urls)} total")
    if working_urls:
        success(f"Working URLs identified: {len(working_urls)}")
        for url in working_urls[:5]:  # Log first 5 working URLs
            logger.debug(f"Working: {color_highlight(url, 'SUCCESS')}")
        if len(working_urls) > 5:
            logger.debug(f"... and {len(working_urls) - 5} more")
    else:
        logger.warning("No working URLs found")

    return working_urls


async def check_url_connectivity(
    url: str,
    ping_timeout: float = 2.0,
    http_timeout: float = 5.0,
    session: aiohttp.ClientSession | None = None,
) -> dict:
    """Check both ping and HTTP connectivity for a single URL."""
    from .utils import extract_hostname

    hostname = extract_hostname(url)

    # Step 1: Ping the hostname
    ping_result = await _ping_single_host(hostname, ping_timeout)

    # Step 2: HTTP check (only if ping succeeds)
    http_result = None
    if ping_result["is_alive"]:
        if session is None:
            # Create session if not provided (for backward compatibility)
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=http_timeout),
                connector=aiohttp.TCPConnector(limit=10),
            ) as session:
                http_result = await _check_single_url_http(session, url, http_timeout)
        else:
            # Use provided session
            http_result = await _check_single_url_http(session, url, http_timeout)

    # Determine overall status
    is_working = ping_result["is_alive"] and (
        http_result and http_result["is_http_working"]
    )

    # Debug logging for detailed status
    logger.debug(f"PING {color_highlight(hostname, 'DEBUG')}")
    if http_result:
        if http_result["redirects_to"]:
            logger.debug(
                f"HTTP {color_highlight(url, 'DEBUG')}: {http_result['http_status']} → {http_result['redirects_to']}"
            )
        else:
            logger.debug(
                f"HTTP {color_highlight(url, 'DEBUG')}: {http_result['http_status']}"
            )

    # Log combined result
    if is_working:
        success(f"WORKING: {color_highlight(url, 'SUCCESS')}")
    elif ping_result["is_alive"] and http_result and not http_result["is_http_working"]:
        logger.warning(f"NETWORK OK, SERVICE DOWN: {color_highlight(url, 'WARNING')}")
    elif not ping_result["is_alive"]:
        logger.error(f"NETWORK DOWN: {color_highlight(url, 'ERROR')}")
    else:
        logger.error(f"UNKNOWN: {color_highlight(url, 'ERROR')}")

    return {
        "url": url,
        "hostname": hostname,
        "ping_result": ping_result,
        "http_result": http_result,
        "is_working": is_working,
    }


async def _check_single_url_http(
    session: aiohttp.ClientSession, url: str, timeout: float
) -> dict:
    """Check a single URL for HTTP connectivity and handle redirects."""
    logger.debug(f"HTTP request: {color_highlight(url, 'DEBUG')} (timeout={timeout}s)")
    try:
        async with session.get(url, allow_redirects=True) as response:
            final_url = str(response.url)
            redirected = url != final_url

            logger.debug(
                f"HTTP response: {color_highlight(url, 'DEBUG')} -> {response.status}"
            )
            if redirected:
                logger.debug(
                    f"Redirected: {color_highlight(url, 'DEBUG')} → {color_highlight(final_url, 'DEBUG')}"
                )

            return {
                "url": url,
                "http_status": response.status,
                "redirects_to": final_url if redirected else None,
                "is_http_working": response.status
                < 400,  # 2xx or 3xx considered working
                "error": None,
            }

    except aiohttp.ClientError as e:
        logger.warning(
            f"HTTP connection error for {color_highlight(url, 'WARNING')}: {str(e)}"
        )
        return {
            "url": url,
            "http_status": None,
            "redirects_to": None,
            "is_http_working": False,
            "error": f"Connection error: {str(e)}",
        }

    except TimeoutError:
        logger.warning(f"HTTP timeout for {color_highlight(url, 'WARNING')}")
        return {
            "url": url,
            "http_status": None,
            "redirects_to": None,
            "is_http_working": False,
            "error": "Timeout",
        }

    except Exception as e:
        logger.error(
            f"Unexpected HTTP error for {color_highlight(url, 'ERROR')}: {str(e)}"
        )
        return {
            "url": url,
            "http_status": None,
            "redirects_to": None,
            "is_http_working": False,
            "error": f"Unexpected error: {str(e)}",
        }


async def check_bdix_connectivity(
    urls: list[dict],
    timeout: float = 2.0,
    check_http: bool = True,
    concurrency: int = 20,
) -> dict:
    """Comprehensive BDIX connectivity check - tests each URL concurrently."""
    logger.debug(f"Testing {len(urls)} URLs concurrently with ping + HTTP validation")

    # Create shared HTTP session for all requests with connection limiting
    session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=5.0),
        connector=aiohttp.TCPConnector(
            limit=concurrency
        ),  # Configurable concurrent HTTP connections
    )

    try:
        # Create tasks for concurrent execution
        tasks = [
            check_url_connectivity(
                url_data["url"], ping_timeout=timeout, http_timeout=5.0, session=session
            )
            for url_data in urls
        ]

        # Execute all checks concurrently
        logger.debug(f"Running {len(tasks)} connectivity checks concurrently")
        connectivity_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions that occurred during concurrent execution
        processed_results = []
        for i, result in enumerate(connectivity_results):
            if isinstance(result, Exception):
                # If a task failed, create a fallback result
                url = urls[i]["url"]
                logger.error(f"Failed to check {url}: {result}")
                from .utils import extract_hostname

                processed_results.append(
                    {
                        "url": url,
                        "hostname": extract_hostname(url),
                        "ping_result": {
                            "hostname": extract_hostname(url),
                            "is_alive": False,
                            "avg_rtt": None,
                            "packet_loss": 100.0,
                            "error": f"Task failed: {str(result)}",
                        },
                        "http_result": None,
                        "is_working": False,
                    }
                )
            else:
                processed_results.append(result)

        connectivity_results = processed_results

    finally:
        # Always close the session
        await session.close()

    # Extract working URLs (no duplicates since we check individually)
    working_urls = [
        result["url"] for result in connectivity_results if result["is_working"]
    ]

    # Calculate statistics
    total_urls = len(urls)
    working_count = len(working_urls)

    # Get unique hosts that are pingable
    pingable_hosts = set()
    for result in connectivity_results:
        if result["ping_result"]["is_alive"]:
            pingable_hosts.add(result["hostname"])

    # Log comprehensive summary
    if check_http:
        logger.debug("HTTP validation was enabled")
    else:
        logger.debug("HTTP validation was disabled")

    if working_urls:
        success(
            f"BDIX connectivity test successful: {working_count} working URLs found"
        )
        logger.debug("Sample working URLs:")
        for url in working_urls[:3]:
            logger.debug(f"  ✓ {color_highlight(url, 'SUCCESS')}")
        if len(working_urls) > 3:
            logger.debug(f"  ... and {len(working_urls) - 3} more")
    else:
        logger.warning("No working URLs found")

    return {
        "total_urls_tested": total_urls,
        "working_urls": working_urls,
        "working_count": working_count,
        "success_rate": working_count / total_urls * 100 if total_urls else 0,
        "total_hosts": len(pingable_hosts),
        "connectivity_results": connectivity_results,
        "http_check_enabled": check_http,
    }
