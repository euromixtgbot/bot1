#!/usr/bin/env python3
"""
Focused File Download Diagnostics
Test the actual file download mechanism that's failing
"""

import sys
import os
import logging
import asyncio
import subprocess
import time
from typing import Dict, List, Any

# Add Bot1 path
sys.path.append('/home/Bot1')
sys.path.append('/home/Bot1/src')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_bot_environment():
    """Test if the bot environment is working"""
    logger.info("🔍 Testing bot environment...")
    
    try:
        # Test config import
        from config.config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN
        
        config_status = {
            'JIRA_DOMAIN': bool(JIRA_DOMAIN),
            'JIRA_EMAIL': bool(JIRA_EMAIL), 
            'JIRA_API_TOKEN': bool(JIRA_API_TOKEN and len(JIRA_API_TOKEN) > 10)
        }
        
        logger.info(f"Config loaded: {config_status}")
        
        if all(config_status.values()):
            logger.info("✅ All required config values present")
            return {'status': 'SUCCESS', 'config': config_status}
        else:
            missing = [k for k, v in config_status.items() if not v]
            logger.error(f"❌ Missing config: {missing}")
            return {'status': 'CONFIG_MISSING', 'missing': missing}
            
    except ImportError as e:
        logger.error(f"❌ Config import failed: {e}")
        return {'status': 'IMPORT_ERROR', 'error': str(e)}
    except Exception as e:
        logger.error(f"❌ Environment test failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def test_jira_attachment_utils():
    """Test the Jira attachment utilities"""
    logger.info("🔍 Testing Jira attachment utilities...")
    
    try:
        from src.jira_attachment_utils import build_attachment_urls, normalize_jira_domain
        
        # Test URL building
        test_domain = "euromix.atlassian.net"
        test_id = "12345"
        test_filename = "test-file.jpg"
        
        urls = build_attachment_urls(test_domain, test_id, test_filename)
        
        logger.info(f"✅ build_attachment_urls working, generated {len(urls)} URLs:")
        for i, url in enumerate(urls[:3], 1):  # Show first 3
            logger.info(f"   {i}. {url}")
        
        # Test domain normalization
        normalized = normalize_jira_domain("https://euromix.atlassian.net")
        logger.info(f"✅ normalize_jira_domain: 'https://euromix.atlassian.net' -> '{normalized}'")
        
        return {
            'status': 'SUCCESS',
            'urls_generated': len(urls),
            'sample_urls': urls[:3],
            'normalized_domain': normalized
        }
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return {'status': 'IMPORT_ERROR', 'error': str(e)}
    except Exception as e:
        logger.error(f"❌ Utility test failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def test_real_jira_api_call():
    """Test a real Jira API call using curl"""
    logger.info("🔍 Testing real Jira API call...")
    
    try:
        # Load credentials
        config_file = '/home/Bot1/config/credentials.env'
        credentials = {}
        
        with open(config_file, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    credentials[key] = value.strip('"')
        
        jira_domain = credentials.get('JIRA_DOMAIN', '').replace('https://', '').replace('http://', '')
        jira_email = credentials.get('JIRA_EMAIL', '')
        jira_token = credentials.get('JIRA_API_TOKEN', '')
        
        if not all([jira_domain, jira_email, jira_token]):
            logger.error("❌ Missing Jira credentials")
            return {'status': 'MISSING_CREDENTIALS'}
        
        # Test API call using curl
        api_url = f"https://{jira_domain}/rest/api/3/myself"
        
        curl_cmd = [
            'curl', '-s', '-w', '%{http_code}',
            '-u', f'{jira_email}:{jira_token}',
            '-H', 'Accept: application/json',
            api_url
        ]
        
        logger.info(f"Testing API call to: {api_url}")
        
        result = subprocess.run(
            curl_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            output = result.stdout
            # HTTP code is at the end
            if len(output) >= 3:
                http_code = output[-3:]
                response_body = output[:-3]
                
                if http_code == '200':
                    logger.info("✅ Jira API call successful (HTTP 200)")
                    return {
                        'status': 'SUCCESS',
                        'http_code': 200,
                        'response_length': len(response_body)
                    }
                else:
                    logger.error(f"❌ Jira API call failed (HTTP {http_code})")
                    return {
                        'status': 'HTTP_ERROR',
                        'http_code': http_code,
                        'response': response_body[:200]  # First 200 chars
                    }
            else:
                logger.error("❌ Unexpected curl response format")
                return {'status': 'CURL_ERROR', 'output': output}
        else:
            logger.error(f"❌ Curl command failed: {result.stderr}")
            return {'status': 'CURL_FAILED', 'error': result.stderr}
            
    except FileNotFoundError:
        logger.error("❌ Credentials file not found")
        return {'status': 'NO_CREDENTIALS_FILE'}
    except Exception as e:
        logger.error(f"❌ API test failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def test_recent_webhook_activity():
    """Check for recent webhook activity"""
    logger.info("🔍 Checking recent webhook activity...")
    
    try:
        log_file = '/home/Bot1/logs/bot.log'
        
        # Get recent attachment-related log entries
        grep_cmd = [
            'grep', '-i', '-n',
            'attachment\|файл\|download\|process.*file',
            log_file
        ]
        
        result = subprocess.run(
            grep_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            recent_lines = lines[-10:]  # Last 10 matches
            
            logger.info(f"✅ Found {len(lines)} attachment-related log entries")
            logger.info("Recent entries:")
            for line in recent_lines:
                logger.info(f"   {line}")
            
            return {
                'status': 'SUCCESS',
                'total_entries': len(lines),
                'recent_entries': recent_lines
            }
        else:
            logger.warning("⚠️ No attachment-related log entries found")
            return {'status': 'NO_ENTRIES'}
            
    except Exception as e:
        logger.error(f"❌ Log analysis failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def test_attachment_cache_state():
    """Check the current state of attachment caching"""
    logger.info("🔍 Checking attachment cache state...")
    
    try:
        # Try to read cache info from main process
        ps_cmd = ['ps', 'aux']
        result = subprocess.run(ps_cmd, capture_output=True, text=True)
        
        bot_processes = []
        for line in result.stdout.split('\n'):
            if 'python' in line and ('bot' in line.lower() or 'webhook' in line.lower()):
                bot_processes.append(line.strip())
        
        logger.info(f"Found {len(bot_processes)} potential bot processes:")
        for proc in bot_processes:
            logger.info(f"   {proc}")
        
        # Check if webhook server is responding
        curl_cmd = [
            'curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
            'http://localhost:9443/health'
        ]
        
        try:
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                http_code = result.stdout.strip()
                if http_code in ['200', '404']:  # 404 is OK, means server is responding
                    logger.info(f"✅ Webhook server responding (HTTP {http_code})")
                    return {
                        'status': 'WEBHOOK_ACTIVE',
                        'processes': len(bot_processes),
                        'webhook_response': http_code
                    }
                else:
                    logger.warning(f"⚠️ Webhook server returned HTTP {http_code}")
                    return {
                        'status': 'WEBHOOK_ISSUES',
                        'http_code': http_code
                    }
            else:
                logger.warning("⚠️ Webhook server not responding")
                return {'status': 'WEBHOOK_DOWN'}
        except subprocess.TimeoutExpired:
            logger.warning("⚠️ Webhook server timeout")
            return {'status': 'WEBHOOK_TIMEOUT'}
            
    except Exception as e:
        logger.error(f"❌ Cache state check failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def analyze_timing_issues():
    """Analyze potential timing issues from logs"""
    logger.info("🔍 Analyzing timing patterns...")
    
    try:
        log_file = '/home/Bot1/logs/bot.log'
        
        # Look for attachment vs comment timing
        timing_cmd = [
            'grep', '-i', '-E',
            '(attachment.*created|comment.*created|cached.*attachment|processing.*attachment)',
            log_file
        ]
        
        result = subprocess.run(
            timing_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            recent_lines = lines[-20:]  # Last 20 matches
            
            logger.info(f"Found {len(lines)} timing-related entries")
            logger.info("Recent timing patterns:")
            for line in recent_lines:
                logger.info(f"   {line}")
            
            # Look for patterns
            attachment_events = [l for l in recent_lines if 'attachment' in l.lower()]
            comment_events = [l for l in recent_lines if 'comment' in l.lower()]
            
            return {
                'status': 'SUCCESS',
                'total_events': len(lines),
                'attachment_events': len(attachment_events),
                'comment_events': len(comment_events),
                'recent_patterns': recent_lines
            }
        else:
            logger.warning("⚠️ No timing-related events found")
            return {'status': 'NO_EVENTS'}
            
    except Exception as e:
        logger.error(f"❌ Timing analysis failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def run_focused_file_diagnosis():
    """Run focused diagnostics on file download system"""
    logger.info("🎯 Starting focused file download diagnosis...")
    logger.info("=" * 60)
    
    # Test 1: Bot environment
    logger.info("\n🔧 TEST 1: Bot Environment")
    env_results = test_bot_environment()
    
    # Test 2: Attachment utilities
    logger.info("\n📎 TEST 2: Attachment Utilities")
    utils_results = test_jira_attachment_utils()
    
    # Test 3: Real Jira API
    logger.info("\n🔗 TEST 3: Real Jira API Call")
    api_results = test_real_jira_api_call()
    
    # Test 4: Recent webhook activity
    logger.info("\n📡 TEST 4: Recent Webhook Activity")
    webhook_results = test_recent_webhook_activity()
    
    # Test 5: Cache state
    logger.info("\n💾 TEST 5: Attachment Cache State")
    cache_results = test_attachment_cache_state()
    
    # Test 6: Timing analysis
    logger.info("\n⏱️ TEST 6: Timing Analysis")
    timing_results = analyze_timing_issues()
    
    # Analysis
    logger.info("\n" + "=" * 60)
    logger.info("🔍 FOCUSED ANALYSIS")
    logger.info("=" * 60)
    
    # Environment status
    env_status = env_results.get('status', 'UNKNOWN')
    logger.info(f"Bot Environment: {env_status}")
    
    # Utils status
    utils_status = utils_results.get('status', 'UNKNOWN')
    logger.info(f"Attachment Utils: {utils_status}")
    
    # API status
    api_status = api_results.get('status', 'UNKNOWN')
    logger.info(f"Jira API Access: {api_status}")
    
    # Webhook status
    webhook_status = webhook_results.get('status', 'UNKNOWN')
    cache_status = cache_results.get('status', 'UNKNOWN')
    logger.info(f"Webhook Activity: {webhook_status}")
    logger.info(f"System State: {cache_status}")
    
    # Root cause analysis
    logger.info("\n🎯 SPECIFIC ISSUE ANALYSIS:")
    
    if env_status != 'SUCCESS':
        logger.error("❌ Bot environment issues detected")
        logger.error("   → Configuration or import problems")
    
    if api_status != 'SUCCESS':
        logger.error("❌ Jira API connection issues")
        logger.error("   → Authentication or connectivity problems")
        logger.error("   → Files cannot be downloaded from Jira")
    
    if webhook_status == 'NO_ENTRIES':
        logger.warning("⚠️ No recent attachment processing")
        logger.warning("   → Webhooks may not be triggering properly")
    
    if cache_status in ['WEBHOOK_DOWN', 'WEBHOOK_TIMEOUT']:
        logger.error("❌ Webhook server not responding")
        logger.error("   → Bot may not be receiving events")
    
    # Success indicators
    if env_status == 'SUCCESS':
        logger.info("✅ Bot environment is healthy")
    
    if utils_status == 'SUCCESS':
        logger.info("✅ Attachment utilities are working")
    
    if api_status == 'SUCCESS':
        logger.info("✅ Jira API authentication is working")
    
    # Recommendations
    logger.info("\n💡 SPECIFIC RECOMMENDATIONS:")
    
    if api_status != 'SUCCESS':
        logger.info("1. 🔧 FIX JIRA API ACCESS:")
        logger.info("   - Check credentials in config/credentials.env")
        logger.info("   - Verify Jira API token permissions") 
        logger.info("   - Test manual API calls")
    
    if cache_status in ['WEBHOOK_DOWN', 'WEBHOOK_TIMEOUT']:
        logger.info("2. 🚀 RESTART WEBHOOK SERVER:")
        logger.info("   - sudo systemctl restart telegram-bot.service")
        logger.info("   - Check webhook server logs")
    
    logger.info("3. 🔍 NEXT STEPS:")
    logger.info("   - Monitor file download attempts in real-time")
    logger.info("   - Test with a specific attachment upload")
    logger.info("   - Check timing between attachment_created and comment_created events")
    
    return {
        'env_results': env_results,
        'utils_results': utils_results,
        'api_results': api_results,
        'webhook_results': webhook_results,
        'cache_results': cache_results,
        'timing_results': timing_results
    }

if __name__ == "__main__":
    try:
        results = run_focused_file_diagnosis()
        logger.info("\n✅ Focused diagnosis completed")
    except Exception as e:
        logger.error(f"❌ Diagnosis failed: {e}")
        sys.exit(1)
