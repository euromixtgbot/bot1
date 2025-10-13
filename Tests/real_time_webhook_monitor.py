#!/usr/bin/env python3
"""
Real-time webhook event monitor for file forwarding testing
Monitors webhook.log for attachment and comment events and provides analysis
"""

import time
import re
import json
from datetime import datetime
from collections import defaultdict, deque
from pathlib import Path

LOG_FILE = "/home/Bot1/logs/webhook.log"
CACHE_STATUS_LOG = "/home/Bot1/cache_status.log"


class WebhookMonitor:
    def __init__(self):
        self.events = deque(maxlen=100)
        self.attachment_events = defaultdict(list)
        self.comment_events = defaultdict(list)
        self.stats = {
            "total_attachments": 0,
            "total_comments": 0,
            "successful_forwards": 0,
            "failed_forwards": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def parse_webhook_line(self, line):
        """Parse webhook log line for events"""
        timestamp_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if not timestamp_match:
            return None

        timestamp = timestamp_match.group(1)

        # Look for attachment events
        if "attachment_created" in line:
            issue_key_match = re.search(
                r'issue_key["\']?\s*:\s*["\']?([A-Z]+-\d+)', line
            )
            attachment_id_match = re.search(
                r'attachment.*id["\']?\s*:\s*["\']?(\d+)', line
            )
            filename_match = re.search(r'filename["\']?\s*:\s*["\']?([^"\']+)', line)

            return {
                "type": "attachment_created",
                "timestamp": timestamp,
                "issue_key": issue_key_match.group(1) if issue_key_match else None,
                "attachment_id": (
                    attachment_id_match.group(1) if attachment_id_match else None
                ),
                "filename": filename_match.group(1) if filename_match else None,
                "raw_line": line.strip(),
            }

        # Look for comment events
        elif "comment_created" in line:
            issue_key_match = re.search(
                r'issue_key["\']?\s*:\s*["\']?([A-Z]+-\d+)', line
            )

            return {
                "type": "comment_created",
                "timestamp": timestamp,
                "issue_key": issue_key_match.group(1) if issue_key_match else None,
                "raw_line": line.strip(),
            }

        # Look for cache-related events
        elif any(
            keyword in line
            for keyword in ["CACHE", "find_cached_attachments", "Strategy"]
        ):
            return {
                "type": "cache_operation",
                "timestamp": timestamp,
                "operation": line.strip(),
            }

        # Look for file forwarding results
        elif any(
            keyword in line
            for keyword in ["sent to Telegram", "Failed to send", "Forwarding file"]
        ):
            return {
                "type": "forwarding_result",
                "timestamp": timestamp,
                "result": line.strip(),
            }

        return None

    def monitor_log(self):
        """Monitor webhook log in real-time"""
        print("🔍 Starting real-time webhook monitor...")
        print(f"📂 Monitoring: {LOG_FILE}")
        print(f"📊 Cache status log: {CACHE_STATUS_LOG}")
        print("=" * 80)
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Monitor started")
        print("=" * 80)

        # Start monitoring from end of file
        try:
            with open(LOG_FILE, "r") as f:
                f.seek(0, 2)  # Go to end of file

                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue

                    event = self.parse_webhook_line(line)
                    if event:
                        self.process_event(event)

        except FileNotFoundError:
            print(f"❌ Log file not found: {LOG_FILE}")
            print("⏳ Waiting for log file to be created...")
            while not Path(LOG_FILE).exists():
                time.sleep(1)
            self.monitor_log()
        except KeyboardInterrupt:
            print("\n🛑 Monitor stopped by user")
            self.print_summary()

    def process_event(self, event):
        """Process a parsed webhook event"""
        current_time = datetime.now().strftime("%H:%M:%S")

        if event["type"] == "attachment_created":
            self.stats["total_attachments"] += 1
            issue_key = event["issue_key"] or "NO_ISSUE_KEY"
            self.attachment_events[issue_key].append(event)

            print(
                f"📎 {current_time} ATTACHMENT: {event['filename']} "
                f"(ID: {event['attachment_id']}, Issue: {issue_key})"
            )

            if not event["issue_key"]:
                print(
                    f"⚠️  {current_time} WARNING: Attachment without issue_key - will use fallback strategy"
                )

        elif event["type"] == "comment_created":
            self.stats["total_comments"] += 1
            issue_key = event["issue_key"] or "NO_ISSUE_KEY"
            self.comment_events[issue_key].append(event)

            print(f"💬 {current_time} COMMENT: Issue {issue_key}")

            # Check if we have pending attachments for this issue
            if issue_key in self.attachment_events:
                attachments = self.attachment_events[issue_key]
                print(
                    f"🔍 {current_time} MATCH: Found {len(attachments)} cached attachments for {issue_key}"
                )
                self.stats["cache_hits"] += len(attachments)
            else:
                print(
                    f"🔍 {current_time} SEARCH: No direct match, will use multi-strategy search"
                )

        elif event["type"] == "cache_operation":
            print(f"🧠 {current_time} CACHE: {event['operation']}")

        elif event["type"] == "forwarding_result":
            if "sent to Telegram" in event["result"]:
                self.stats["successful_forwards"] += 1
                print(f"✅ {current_time} SUCCESS: {event['result']}")
            else:
                self.stats["failed_forwards"] += 1
                print(f"❌ {current_time} FAILED: {event['result']}")

        # Log to cache status file
        with open(CACHE_STATUS_LOG, "a") as f:
            f.write(
                f"{datetime.now().isoformat()} - {event['type']}: {json.dumps(event, default=str)}\n"
            )

    def print_summary(self):
        """Print monitoring summary"""
        print("\n" + "=" * 80)
        print("📊 MONITORING SUMMARY")
        print("=" * 80)
        print(f"📎 Total Attachments: {self.stats['total_attachments']}")
        print(f"💬 Total Comments: {self.stats['total_comments']}")
        print(f"✅ Successful Forwards: {self.stats['successful_forwards']}")
        print(f"❌ Failed Forwards: {self.stats['failed_forwards']}")
        print(f"🎯 Cache Hits: {self.stats['cache_hits']}")
        print(f"🔍 Cache Misses: {self.stats['cache_misses']}")

        if self.stats["total_attachments"] > 0:
            success_rate = (
                self.stats["successful_forwards"] / self.stats["total_attachments"]
            ) * 100
            print(f"📈 Success Rate: {success_rate:.1f}%")

        print("=" * 80)


if __name__ == "__main__":
    monitor = WebhookMonitor()
    monitor.monitor_log()
