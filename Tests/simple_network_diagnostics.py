#!/usr/bin/env python3
"""
Simple Network Diagnostics for File Forwarding Issues
Uses only standard library modules
"""

import socket
import subprocess
import sys
import logging
import json
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_dns_resolution():
    """Test DNS resolution using socket.gethostbyname"""
    logger.info("🔍 Testing DNS resolution...")
    
    test_domains = [
        'google.com',
        'atlassian.net', 
        'httpbin.org'
    ]
    
    results = {}
    
    for domain in test_domains:
        try:
            ip = socket.gethostbyname(domain)
            results[domain] = {
                'status': 'SUCCESS',
                'ip': ip,
                'error': None
            }
            logger.info(f"✅ {domain}: {ip}")
        except socket.gaierror as e:
            results[domain] = {
                'status': 'DNS_FAILURE',
                'ip': None,
                'error': str(e)
            }
            logger.error(f"❌ {domain}: DNS Error - {e}")
        except Exception as e:
            results[domain] = {
                'status': 'OTHER_ERROR',
                'ip': None,
                'error': str(e)
            }
            logger.error(f"❌ {domain}: Other Error - {e}")
    
    return results

def test_jira_domain_resolution():
    """Test Jira domain resolution specifically"""
    logger.info("🔍 Testing Jira domain resolution...")
    
    try:
        # Try to read Jira domain from config
        config_file = '/home/Bot1/config/credentials.env'
        jira_domain = None
        
        try:
            with open(config_file, 'r') as f:
                for line in f:
                    if line.startswith('JIRA_DOMAIN='):
                        jira_domain = line.split('=', 1)[1].strip().strip('"')
                        break
        except FileNotFoundError:
            logger.warning("Config file not found, using example domain")
            jira_domain = "example.atlassian.net"
        
        if jira_domain:
            # Clean the domain (remove http/https)
            if jira_domain.startswith(('http://', 'https://')):
                parsed = urlparse(jira_domain)
                domain = parsed.netloc
            else:
                domain = jira_domain
            
            logger.info(f"Testing Jira domain: {domain}")
            
            try:
                ip = socket.gethostbyname(domain)
                logger.info(f"✅ Jira domain resolved: {domain} -> {ip}")
                return {'status': 'SUCCESS', 'domain': domain, 'ip': ip}
            except socket.gaierror as e:
                logger.error(f"❌ Jira domain DNS failure: {domain} - {e}")
                return {'status': 'DNS_FAILURE', 'domain': domain, 'error': str(e)}
        else:
            logger.warning("⚠️ No Jira domain found in config")
            return {'status': 'CONFIG_ERROR', 'error': 'No Jira domain configured'}
            
    except Exception as e:
        logger.error(f"❌ Error testing Jira domain: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def test_network_commands():
    """Test basic network commands"""
    logger.info("🔍 Testing network commands...")
    
    commands = [
        ('ping', ['ping', '-c', '3', '8.8.8.8']),
        ('dig', ['dig', '+short', 'google.com']),
        ('nslookup', ['nslookup', 'google.com']),
        ('curl', ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'https://httpbin.org/get'])
    ]
    
    results = {}
    
    for name, cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                results[name] = {
                    'status': 'SUCCESS',
                    'output': result.stdout.strip(),
                    'error': None
                }
                logger.info(f"✅ {name}: Success")
            else:
                results[name] = {
                    'status': 'COMMAND_FAILED',
                    'output': result.stdout.strip(),
                    'error': result.stderr.strip()
                }
                logger.warning(f"⚠️ {name}: Command failed (exit {result.returncode})")
                
        except subprocess.TimeoutExpired:
            results[name] = {
                'status': 'TIMEOUT',
                'output': None,
                'error': 'Command timed out'
            }
            logger.error(f"❌ {name}: Timeout")
        except FileNotFoundError:
            results[name] = {
                'status': 'NOT_FOUND',
                'output': None,
                'error': 'Command not found'
            }
            logger.warning(f"⚠️ {name}: Command not found")
        except Exception as e:
            results[name] = {
                'status': 'ERROR',
                'output': None,
                'error': str(e)
            }
            logger.error(f"❌ {name}: Error - {e}")
    
    return results

def check_dns_configuration():
    """Check DNS configuration files"""
    logger.info("🔍 Checking DNS configuration...")
    
    results = {}
    
    # Check resolv.conf
    try:
        with open('/etc/resolv.conf', 'r') as f:
            resolv_content = f.read()
        
        nameservers = []
        for line in resolv_content.split('\n'):
            if line.strip().startswith('nameserver'):
                ns = line.split()[1]
                nameservers.append(ns)
        
        results['resolv_conf'] = {
            'status': 'SUCCESS',
            'nameservers': nameservers,
            'content': resolv_content
        }
        logger.info(f"✅ Found {len(nameservers)} nameservers: {nameservers}")
        
    except Exception as e:
        results['resolv_conf'] = {
            'status': 'ERROR',
            'error': str(e)
        }
        logger.error(f"❌ Error reading resolv.conf: {e}")
    
    # Check systemd-resolved status
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'systemd-resolved'],
            capture_output=True,
            text=True
        )
        
        status = result.stdout.strip()
        results['systemd_resolved'] = {
            'status': 'SUCCESS' if status == 'active' else 'INACTIVE',
            'service_status': status
        }
        logger.info(f"✅ systemd-resolved: {status}")
        
    except Exception as e:
        results['systemd_resolved'] = {
            'status': 'ERROR',
            'error': str(e)
        }
        logger.error(f"❌ Error checking systemd-resolved: {e}")
    
    return results

def analyze_log_patterns():
    """Analyze recent log patterns for network errors"""
    logger.info("🔍 Analyzing log patterns...")
    
    log_files = [
        '/home/Bot1/logs/bot.log',
        '/home/Bot1/logs/webhook.log'
    ]
    
    network_error_patterns = [
        'name resolution',
        'DNS',
        'Connection error',
        'ConnectError',
        'HTTPError',
        'timeout',
        'failed to download'
    ]
    
    results = {}
    
    for log_file in log_files:
        try:
            with open(log_file, 'r') as f:
                # Read last 1000 lines
                lines = f.readlines()[-1000:]
            
            error_count = 0
            error_samples = []
            
            for line in lines:
                for pattern in network_error_patterns:
                    if pattern.lower() in line.lower():
                        error_count += 1
                        if len(error_samples) < 5:  # Keep first 5 samples
                            error_samples.append(line.strip())
                        break
            
            results[log_file] = {
                'status': 'SUCCESS',
                'total_lines_checked': len(lines),
                'network_errors_found': error_count,
                'error_samples': error_samples
            }
            
            if error_count > 0:
                logger.warning(f"⚠️ Found {error_count} network errors in {log_file}")
            else:
                logger.info(f"✅ No network errors in recent {log_file}")
                
        except FileNotFoundError:
            results[log_file] = {
                'status': 'NOT_FOUND',
                'error': 'Log file not found'
            }
            logger.warning(f"⚠️ Log file not found: {log_file}")
        except Exception as e:
            results[log_file] = {
                'status': 'ERROR',
                'error': str(e)
            }
            logger.error(f"❌ Error reading {log_file}: {e}")
    
    return results

def run_comprehensive_diagnosis():
    """Run all diagnostic tests"""
    logger.info("🚀 Starting comprehensive network diagnosis...")
    logger.info("=" * 60)
    
    # Test 1: Basic DNS resolution
    logger.info("\n📡 TEST 1: Basic DNS Resolution")
    dns_results = test_dns_resolution()
    
    # Test 2: Jira domain resolution
    logger.info("\n🔗 TEST 2: Jira Domain Resolution")
    jira_results = test_jira_domain_resolution()
    
    # Test 3: Network commands
    logger.info("\n🛠️ TEST 3: Network Commands")
    command_results = test_network_commands()
    
    # Test 4: DNS configuration
    logger.info("\n⚙️ TEST 4: DNS Configuration")
    dns_config_results = check_dns_configuration()
    
    # Test 5: Log analysis
    logger.info("\n📄 TEST 5: Log Analysis")
    log_results = analyze_log_patterns()
    
    # Summary and analysis
    logger.info("\n" + "=" * 60)
    logger.info("📊 DIAGNOSTIC SUMMARY")
    logger.info("=" * 60)
    
    # DNS Summary
    dns_success = sum(1 for r in dns_results.values() if r['status'] == 'SUCCESS')
    dns_total = len(dns_results)
    logger.info(f"DNS Resolution: {dns_success}/{dns_total} successful")
    
    # Jira DNS Summary
    jira_status = jira_results.get('status', 'UNKNOWN')
    logger.info(f"Jira Domain Resolution: {jira_status}")
    
    # Commands Summary
    cmd_success = sum(1 for r in command_results.values() if r['status'] == 'SUCCESS')
    cmd_total = len(command_results)
    logger.info(f"Network Commands: {cmd_success}/{cmd_total} successful")
    
    # Log errors summary
    total_errors = sum(
        r.get('network_errors_found', 0) 
        for r in log_results.values() 
        if isinstance(r, dict)
    )
    logger.info(f"Network Errors in Logs: {total_errors} found")
    
    # Root cause analysis
    logger.info("\n🎯 ROOT CAUSE ANALYSIS:")
    
    dns_failures = [d for d, r in dns_results.items() if 'FAILURE' in r['status']]
    if dns_failures:
        logger.error(f"❌ DNS Resolution Issues for: {dns_failures}")
        logger.error("   → This explains 'Temporary failure in name resolution' errors")
    
    if jira_results.get('status') == 'DNS_FAILURE':
        logger.error("❌ Jira domain cannot be resolved")
        logger.error("   → File downloads from Jira will fail consistently")
    
    if total_errors > 0:
        logger.warning(f"⚠️ Found {total_errors} network-related errors in recent logs")
        logger.warning("   → Pattern suggests ongoing connectivity issues")
    
    # Recommendations
    logger.info("\n💡 IMMEDIATE ACTIONS NEEDED:")
    
    if dns_failures or jira_results.get('status') == 'DNS_FAILURE':
        logger.info("1. 🔧 DNS FIXES:")
        logger.info("   sudo systemctl restart systemd-resolved")
        logger.info("   sudo systemctl flush-dns")
        logger.info("   Consider adding: nameserver 8.8.8.8 to /etc/resolv.conf")
    
    if total_errors > 10:
        logger.info("2. 🚨 URGENT CODE FIXES:")
        logger.info("   - Add robust retry mechanisms")
        logger.info("   - Implement connection pooling")
        logger.info("   - Add network timeout handling")
    
    logger.info("3. 🔍 MONITORING:")
    logger.info("   - Monitor attachment download success rate")
    logger.info("   - Set up alerts for DNS failures")
    logger.info("   - Track file forwarding metrics")
    
    return {
        'dns_results': dns_results,
        'jira_results': jira_results,
        'command_results': command_results,
        'dns_config_results': dns_config_results,
        'log_results': log_results
    }

if __name__ == "__main__":
    try:
        results = run_comprehensive_diagnosis()
        logger.info("\n✅ Diagnosis completed successfully")
    except Exception as e:
        logger.error(f"❌ Diagnosis failed: {e}")
        sys.exit(1)
