#!/usr/bin/env python3
"""
Network Diagnostics and Jira Connectivity Test
Specialized script to diagnose the file forwarding issues
"""

import asyncio
import httpx
import logging
import sys

# Add Bot1 path
sys.path.append("/home/Bot1")
sys.path.append("/home/Bot1/src")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_dns_resolution():
    """Test DNS resolution capabilities"""
    logger.info("🔍 Testing DNS resolution...")

    test_domains = ["google.com", "atlassian.net", "httpbin.org"]

    results = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for domain in test_domains:
            try:
                url = f"https://{domain}"
                response = await client.get(url)
                results[domain] = {
                    "status": "SUCCESS",
                    "status_code": response.status_code,
                    "error": None,
                }
                logger.info(f"✅ {domain}: {response.status_code}")
            except httpx.ConnectError as e:
                results[domain] = {
                    "status": "DNS_FAILURE",
                    "status_code": None,
                    "error": str(e),
                }
                logger.error(f"❌ {domain}: DNS Error - {e}")
            except Exception as e:
                results[domain] = {
                    "status": "OTHER_ERROR",
                    "status_code": None,
                    "error": str(e),
                }
                logger.error(f"❌ {domain}: Other Error - {e}")

    return results


async def test_jira_api_connectivity():
    """Test specific Jira API connectivity"""
    logger.info("🔍 Testing Jira API connectivity...")

    try:
        # Load config
        from config.config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN

        if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN]):
            logger.error("❌ Missing Jira configuration")
            return {"status": "CONFIG_ERROR", "error": "Missing credentials"}

        # Clean domain
        domain = JIRA_DOMAIN.replace("https://", "").replace("http://", "")
        base_url = f"https://{domain}"

        logger.info(f"Testing connectivity to: {base_url}")

        auth = httpx.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)

        # Test basic API endpoint
        test_url = f"{base_url}/rest/api/3/myself"

        async with httpx.AsyncClient(
            timeout=30.0, auth=auth, follow_redirects=True, trust_env=True
        ) as client:
            response = await client.get(test_url)
            response.raise_for_status()

            data = response.json()
            logger.info("✅ Jira API connection successful")
            logger.info(f"   User: {data.get('displayName', 'Unknown')}")

            return {
                "status": "SUCCESS",
                "user": data.get("displayName"),
                "account_id": data.get("accountId"),
            }

    except httpx.ConnectError as e:
        logger.error(f"❌ Jira API DNS/Connection Error: {e}")
        return {"status": "DNS_FAILURE", "error": str(e)}
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Jira API HTTP Error: {e.response.status_code}")
        return {"status": "AUTH_ERROR", "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        logger.error(f"❌ Jira API Other Error: {e}")
        return {"status": "OTHER_ERROR", "error": str(e)}


async def test_attachment_download_simulation():
    """Simulate the attachment download process"""
    logger.info("🔍 Testing attachment download simulation...")

    try:
        from config.config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN
        from src.jira_attachment_utils import (
            build_attachment_urls,
        )

        # Simulate attachment parameters
        domain = JIRA_DOMAIN.replace("https://", "").replace("http://", "")
        test_attachment_id = "12345"  # Fake ID for URL testing
        test_filename = "test-file.jpg"

        # Build URLs like the real system does
        urls = build_attachment_urls(domain, test_attachment_id, test_filename)

        logger.info(f"Generated {len(urls)} test URLs:")
        for i, url in enumerate(urls, 1):
            logger.info(f"  {i}. {url}")

        # Test each URL for connectivity (without expecting success)
        results = []

        async with httpx.AsyncClient(
            timeout=30.0,
            auth=httpx.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
            follow_redirects=True,
            trust_env=True,
        ) as client:

            for url in urls[:3]:  # Test first 3 URLs only
                try:
                    response = await client.get(url)
                    results.append(
                        {
                            "url": url,
                            "status": "REACHABLE",
                            "status_code": response.status_code,
                            "content_type": response.headers.get(
                                "content-type", "unknown"
                            ),
                        }
                    )
                    logger.info(f"✅ URL reachable: {url} ({response.status_code})")

                except httpx.ConnectError as e:
                    results.append(
                        {"url": url, "status": "DNS_FAILURE", "error": str(e)}
                    )
                    logger.error(f"❌ DNS failure for: {url}")

                except httpx.HTTPStatusError as e:
                    results.append(
                        {
                            "url": url,
                            "status": "HTTP_ERROR",
                            "status_code": e.response.status_code,
                            "error": str(e),
                        }
                    )
                    logger.warning(
                        f"⚠️ HTTP error for: {url} ({e.response.status_code})"
                    )

                except Exception as e:
                    results.append(
                        {"url": url, "status": "OTHER_ERROR", "error": str(e)}
                    )
                    logger.error(f"❌ Other error for: {url}")

        return {"status": "COMPLETED", "urls_tested": len(results), "results": results}

    except Exception as e:
        logger.error(f"❌ Attachment download simulation failed: {e}")
        return {"status": "ERROR", "error": str(e)}


async def run_comprehensive_network_diagnosis():
    """Run all network diagnostic tests"""
    logger.info("🚀 Starting comprehensive network diagnosis...")
    logger.info("=" * 60)

    # Test 1: Basic DNS resolution
    logger.info("\n📡 TEST 1: Basic DNS Resolution")
    dns_results = await test_dns_resolution()

    # Test 2: Jira API connectivity
    logger.info("\n🔗 TEST 2: Jira API Connectivity")
    jira_results = await test_jira_api_connectivity()

    # Test 3: Attachment download simulation
    logger.info("\n📎 TEST 3: Attachment Download Simulation")
    attachment_results = await test_attachment_download_simulation()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 DIAGNOSTIC SUMMARY")
    logger.info("=" * 60)

    # DNS Summary
    dns_success = sum(1 for r in dns_results.values() if r["status"] == "SUCCESS")
    dns_total = len(dns_results)
    logger.info(f"DNS Resolution: {dns_success}/{dns_total} successful")

    # Jira API Summary
    jira_status = jira_results.get("status", "UNKNOWN")
    logger.info(f"Jira API Status: {jira_status}")

    # Attachment URLs Summary
    if attachment_results.get("status") == "COMPLETED":
        att_results = attachment_results.get("results", [])
        reachable = sum(
            1 for r in att_results if r.get("status", "") in ["REACHABLE", "HTTP_ERROR"]
        )
        total = len(att_results)
        logger.info(f"Attachment URLs: {reachable}/{total} reachable")

    # Generate diagnosis
    logger.info("\n🎯 ROOT CAUSE ANALYSIS:")

    dns_failures = [d for d, r in dns_results.items() if "DNS" in r["status"]]
    if dns_failures:
        logger.error(f"❌ DNS Resolution Issues detected for: {dns_failures}")
        logger.error("   → This explains 'Temporary failure in name resolution' errors")

    if jira_results.get("status") == "DNS_FAILURE":
        logger.error("❌ Jira API unreachable due to DNS issues")
        logger.error("   → File downloads will fail consistently")

    if all(r["status"] == "SUCCESS" for r in dns_results.values()):
        logger.info("✅ DNS resolution working correctly")

    if jira_results.get("status") == "SUCCESS":
        logger.info("✅ Jira API authentication working correctly")

    # Recommendations
    logger.info("\n💡 RECOMMENDATIONS:")

    if dns_failures:
        logger.info("1. 🔧 Fix DNS configuration:")
        logger.info("   - Check /etc/resolv.conf")
        logger.info("   - Restart systemd-resolved")
        logger.info("   - Consider alternative DNS servers (8.8.8.8, 1.1.1.1)")

    logger.info("2. 🔍 Monitor specific error patterns:")
    logger.info("   - Watch for 'name resolution' errors")
    logger.info("   - Check attachment download success rates")

    logger.info("3. 🚀 Implement network resilience:")
    logger.info("   - Add retry mechanisms with exponential backoff")
    logger.info("   - Implement connection pooling")
    logger.info("   - Add network health checks")


if __name__ == "__main__":
    asyncio.run(run_comprehensive_network_diagnosis())
