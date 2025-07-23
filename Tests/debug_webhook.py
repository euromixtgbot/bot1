#!/usr/bin/env python3
"""
Debug webhook handler for comprehensive logging of all attachment processing
"""

import sys
import os
import json
import logging
import asyncio
from typing import Dict, List, Any

sys.path.append('/home/Bot1/src')

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/Bot1/webhook_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def analyze_webhook_payload(webhook_data: Dict[str, Any]) -> None:
    """Comprehensive analysis of webhook payload"""
    
    logger.info("🔍 WEBHOOK PAYLOAD ANALYSIS")
    logger.info("=" * 60)
    
    # Basic event info
    event_type = webhook_data.get('webhookEvent', 'unknown')
    logger.info(f"📋 Event Type: {event_type}")
    
    # Issue info
    issue = webhook_data.get('issue', {})
    issue_key = issue.get('key', 'unknown')
    issue_summary = issue.get('fields', {}).get('summary', 'unknown')
    logger.info(f"🎫 Issue: {issue_key} - {issue_summary}")
    
    # Comment info
    comment = webhook_data.get('comment', {})
    comment_body = comment.get('body', '')
    author = comment.get('author', {})
    author_name = author.get('displayName', 'unknown')
    logger.info(f"💬 Comment by: {author_name}")
    logger.info(f"📝 Comment body: {comment_body[:200]}...")
    
    # Search for attachments in ALL locations
    logger.info("\n🔍 SEARCHING FOR ATTACHMENTS IN ALL LOCATIONS:")
    logger.info("-" * 50)
    
    all_attachments = []
    
    # 1. Comment-level attachments
    if 'attachment' in comment:
        comment_attachments = comment['attachment']
        logger.info(f"📎 Comment attachments (singular): {len(comment_attachments)}")
        for i, att in enumerate(comment_attachments):
            logger.info(f"  {i+1}. {att.get('filename', 'unknown')} (ID: {att.get('id', 'no-id')})")
        all_attachments.extend(comment_attachments)
    
    if 'attachments' in comment:
        comment_attachments_plural = comment['attachments']
        logger.info(f"📎 Comment attachments (plural): {len(comment_attachments_plural)}")
        for i, att in enumerate(comment_attachments_plural):
            logger.info(f"  {i+1}. {att.get('filename', 'unknown')} (ID: {att.get('id', 'no-id')})")
        all_attachments.extend(comment_attachments_plural)
    
    # 2. Issue-level attachments
    if 'issue' in webhook_data and 'fields' in webhook_data['issue']:
        issue_attachments = webhook_data['issue']['fields'].get('attachment', [])
        logger.info(f"📎 Issue-level attachments: {len(issue_attachments)}")
        for i, att in enumerate(issue_attachments):
            logger.info(f"  {i+1}. {att.get('filename', 'unknown')} (ID: {att.get('id', 'no-id')})")
        all_attachments.extend(issue_attachments)
    
    # 3. Content structure
    if 'content' in comment:
        content_attachments = []
        for item in comment['content']:
            if isinstance(item, dict) and 'attachment' in item:
                content_attachments.append(item['attachment'])
        logger.info(f"📎 Content structure attachments: {len(content_attachments)}")
        for i, att in enumerate(content_attachments):
            logger.info(f"  {i+1}. {att.get('filename', 'unknown')} (ID: {att.get('id', 'no-id')})")
        all_attachments.extend(content_attachments)
    
    # 4. Embedded attachments in text
    if comment_body:
        import re
        embedded_pattern = r'!([^|!]+)(?:\|([^!]+))?!'
        embedded_matches = re.findall(embedded_pattern, comment_body)
        logger.info(f"📎 Embedded attachments in text: {len(embedded_matches)}")
        for i, match in enumerate(embedded_matches):
            filename = match[0].split('/')[-1]
            params = match[1] if len(match) > 1 else ''
            logger.info(f"  {i+1}. {filename} (params: {params})")
    
    # Summary
    unique_files = set()
    for att in all_attachments:
        filename = att.get('filename', 'unknown')
        unique_files.add(filename)
    
    logger.info(f"\n📊 SUMMARY:")
    logger.info(f"Total attachment objects found: {len(all_attachments)}")
    logger.info(f"Unique filenames: {len(unique_files)}")
    logger.info(f"Files: {list(unique_files)}")
    
    # Full webhook payload (truncated)
    logger.info(f"\n📋 FULL WEBHOOK PAYLOAD:")
    logger.info(json.dumps(webhook_data, indent=2, ensure_ascii=False)[:2000] + "...")

def main():
    """Test webhook analysis with sample data"""
    
    # Sample webhook payload based on user's screenshot
    sample_webhook = {
        "webhookEvent": "comment_created",
        "issue": {
            "key": "SD-42699",
            "fields": {
                "summary": "Test issue with multiple attachments",
                "attachment": [
                    {
                        "id": "1001",
                        "filename": "відповідь Е-мікс.txt",
                        "mimeType": "text/plain",
                        "content": "https://euromix.atlassian.net/secure/attachment/1001/відповідь%20Е-мікс.txt"
                    },
                    {
                        "id": "1002", 
                        "filename": "Статуси для відображення на порталі.xlsx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "content": "https://euromix.atlassian.net/secure/attachment/1002/Статуси%20для%20відображення%20на%20порталі.xlsx"
                    },
                    {
                        "id": "1003",
                        "filename": "IMG-299481c87ebe831a0566c37750ee804-V.jpg",
                        "mimeType": "image/jpeg", 
                        "content": "https://euromix.atlassian.net/secure/attachment/1003/IMG-299481c87ebe831a0566c37750ee804-V.jpg"
                    }
                ]
            }
        },
        "comment": {
            "author": {
                "displayName": "Мартыненко Олег Викторович"
            },
            "body": "Test comment with attachments"
        }
    }
    
    analyze_webhook_payload(sample_webhook)

if __name__ == "__main__":
    main()
