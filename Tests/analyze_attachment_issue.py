#!/usr/bin/env python3
"""
Comprehensive analysis and fix for attachment processing in Jira-Telegram bot
"""

import sys
import logging

sys.path.append("/home/Bot1/src")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def analyze_attachment_processing_issue():
    """Analyze the attachment processing issue based on user feedback"""

    print("🔍 ANALYZING ATTACHMENT PROCESSING ISSUE")
    print("=" * 60)

    print("📝 PROBLEM DESCRIPTION:")
    print("- User sent 3 files of different types from Jira")
    print("- Only photo files are received in Telegram")
    print("- Other file types (Excel, text, etc.) are not forwarded")
    print("- This suggests the issue is NOT with MIME type detection")
    print("- The issue is likely with file extraction or processing logic")

    print("\n🔍 POTENTIAL ROOT CAUSES:")
    print("1. Embedded attachment extraction only catches certain file types")
    print("2. File download URLs are not being built correctly for non-image files")
    print("3. Authentication issues with certain file types")
    print("4. Jira webhook payload doesn't include all attachment types")
    print("5. Attachment processing logic has type-specific filtering")

    print("\n📊 INVESTIGATION PLAN:")
    print("1. Check webhook payload structure for all file types")
    print("2. Verify embedded attachment extraction regex")
    print("3. Test file download URL building for different types")
    print("4. Check authentication and headers for file downloads")
    print("5. Implement universal file handling")


def create_debug_webhook_handler():
    """Create a debug version of webhook handler that logs everything"""

    debug_code = '''
async def debug_handle_comment_created(webhook_data: Dict[str, Any]) -> None:
    """Debug version of comment handler that logs everything"""

    logger.info("🔍 DEBUG: Starting comment processing")
    logger.info(f"📋 Full webhook data: {json.dumps(webhook_data, indent=2, ensure_ascii=False)}")

    try:
        # Extract comment data
        comment = webhook_data.get('comment', {})
        comment_body = comment.get('body', '')
        issue_key = webhook_data.get('issue', {}).get('key', '')

        logger.info(f"📝 Comment body: {comment_body}")
        logger.info(f"🔑 Issue key: {issue_key}")

        # Check for ALL possible attachment locations
        all_attachments = []

        # 1. Direct comment attachments
        if 'attachment' in comment:
            direct_attachments = comment.get('attachment', [])
            logger.info(f"📎 Found {len(direct_attachments)} direct attachments")
            for att in direct_attachments:
                logger.info(f"  - {att.get('filename', 'unknown')}: {json.dumps(att, indent=2)}")
            all_attachments.extend(direct_attachments)

        # 2. Plural attachments
        if 'attachments' in comment:
            plural_attachments = comment.get('attachments', [])
            logger.info(f"📎 Found {len(plural_attachments)} plural attachments")
            for att in plural_attachments:
                logger.info(f"  - {att.get('filename', 'unknown')}: {json.dumps(att, indent=2)}")
            all_attachments.extend(plural_attachments)

        # 3. Issue-level attachments (might be missing)
        if 'issue' in webhook_data and 'fields' in webhook_data['issue']:
            issue_attachments = webhook_data['issue']['fields'].get('attachment', [])
            logger.info(f"📎 Found {len(issue_attachments)} issue-level attachments")
            for att in issue_attachments:
                logger.info(f"  - {att.get('filename', 'unknown')}: {json.dumps(att, indent=2)}")
            all_attachments.extend(issue_attachments)

        # 4. Embedded attachments in text
        if comment_body:
            embedded = extract_embedded_attachments(comment_body)
            logger.info(f"📎 Found {len(embedded)} embedded attachments")
            for att in embedded:
                logger.info(f"  - {att.get('filename', 'unknown')}: {json.dumps(att, indent=2)}")
            all_attachments.extend(embedded)

        # 5. Content structure attachments
        if 'content' in comment:
            content_attachments = []
            for item in comment.get('content', []):
                if isinstance(item, dict):
                    if 'attachment' in item:
                        content_attachments.append(item['attachment'])
                    elif 'type' in item and item['type'] == 'mediaGroup':
                        for media in item.get('content', []):
                            if 'attachment' in media:
                                content_attachments.append(media['attachment'])

            logger.info(f"📎 Found {len(content_attachments)} content structure attachments")
            for att in content_attachments:
                logger.info(f"  - {att.get('filename', 'unknown')}: {json.dumps(att, indent=2)}")
            all_attachments.extend(content_attachments)

        logger.info(f"📋 TOTAL ATTACHMENTS FOUND: {len(all_attachments)}")

        # Try to process all attachments
        if all_attachments:
            logger.info("🔄 Starting attachment processing...")
            for i, att in enumerate(all_attachments, 1):
                logger.info(f"🔄 Processing attachment {i}/{len(all_attachments)}")
                logger.info(f"  Filename: {att.get('filename', 'unknown')}")
                logger.info(f"  ID: {att.get('id', 'no-id')}")
                logger.info(f"  Content URL: {att.get('content', 'no-content')}")
                logger.info(f"  Self URL: {att.get('self', 'no-self')}")
                logger.info(f"  MIME Type: {att.get('mimeType', 'unknown')}")

                # Test file download
                try:
                    from src.jira_attachment_utils import build_attachment_urls, download_file_from_jira
                    urls = build_attachment_urls(JIRA_DOMAIN, att.get('id', ''), att.get('filename', ''), att.get('content', ''))
                    logger.info(f"  📥 Download URLs: {urls}")

                    # Try to download
                    file_bytes = await download_file_from_jira(urls)
                    if file_bytes:
                        logger.info(f"  ✅ Successfully downloaded {len(file_bytes)} bytes")
                    else:
                        logger.error(f"  ❌ Failed to download file")
                except Exception as e:
                    logger.error(f"  ❌ Download error: {e}")

    except Exception as e:
        logger.error(f"🚨 DEBUG ERROR: {e}", exc_info=True)
'''

    return debug_code


def create_universal_attachment_extractor():
    """Create a universal attachment extractor that handles all file types"""

    extractor_code = '''
async def extract_all_attachments_universal(webhook_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Universal attachment extractor that finds ALL attachments regardless of type"""

    all_attachments = []

    # Get comment data
    comment = webhook_data.get('comment', {})
    comment_body = comment.get('body', '')
    issue_key = webhook_data.get('issue', {}).get('key', '')

    logger.info(f"🔍 Extracting attachments for issue {issue_key}")

    # 1. Direct comment attachments
    if 'attachment' in comment:
        direct_attachments = comment.get('attachment', [])
        logger.info(f"📎 Direct attachments: {len(direct_attachments)}")
        all_attachments.extend(direct_attachments)

    # 2. Plural attachments
    if 'attachments' in comment:
        plural_attachments = comment.get('attachments', [])
        logger.info(f"📎 Plural attachments: {len(plural_attachments)}")
        all_attachments.extend(plural_attachments)

    # 3. Issue-level attachments
    if 'issue' in webhook_data and 'fields' in webhook_data['issue']:
        issue_attachments = webhook_data['issue']['fields'].get('attachment', [])
        logger.info(f"📎 Issue attachments: {len(issue_attachments)}")
        all_attachments.extend(issue_attachments)

    # 4. Embedded attachments in comment body
    if comment_body:
        embedded = extract_embedded_attachments(comment_body)
        logger.info(f"📎 Embedded attachments: {len(embedded)}")
        all_attachments.extend(embedded)

    # 5. Content structure parsing (recursive)
    def extract_from_content(content_item):
        attachments = []
        if isinstance(content_item, dict):
            # Direct attachment
            if 'attachment' in content_item:
                attachments.append(content_item['attachment'])

            # Media group
            if content_item.get('type') == 'mediaGroup':
                for media in content_item.get('content', []):
                    attachments.extend(extract_from_content(media))

            # Other content types
            if 'content' in content_item:
                for sub_item in content_item['content']:
                    attachments.extend(extract_from_content(sub_item))

        return attachments

    if 'content' in comment:
        content_attachments = []
        for item in comment.get('content', []):
            content_attachments.extend(extract_from_content(item))

        logger.info(f"📎 Content structure attachments: {len(content_attachments)}")
        all_attachments.extend(content_attachments)

    # 6. Try to get ALL attachments from issue API if we have attachment IDs but missing data
    if issue_key:
        try:
            from src.jira_attachment_utils import get_issue_attachments_by_filename
            import httpx
            from config.config import JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN

            # Get all attachments from issue
            auth = httpx.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
            url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}?fields=attachment"

            async with httpx.AsyncClient(timeout=30, auth=auth) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                issue_data = resp.json()
                api_attachments = issue_data.get('fields', {}).get('attachment', [])

                logger.info(f"📎 API attachments: {len(api_attachments)}")

                # Add any missing attachments
                existing_ids = {att.get('id') for att in all_attachments if att.get('id')}
                for api_att in api_attachments:
                    if api_att.get('id') not in existing_ids:
                        all_attachments.append(api_att)
                        logger.info(f"  + Added missing attachment: {api_att.get('filename')}")

        except Exception as e:
            logger.error(f"Error getting attachments from API: {e}")

    # Remove duplicates by ID
    unique_attachments = []
    seen_ids = set()

    for att in all_attachments:
        att_id = att.get('id')
        if att_id and att_id not in seen_ids:
            unique_attachments.append(att)
            seen_ids.add(att_id)
        elif not att_id:  # No ID, check by filename
            filename = att.get('filename', '')
            if filename and filename not in [a.get('filename') for a in unique_attachments]:
                unique_attachments.append(att)

    logger.info(f"📋 Total unique attachments: {len(unique_attachments)}")

    return unique_attachments
'''

    return extractor_code


def create_universal_file_processor():
    """Create a universal file processor that handles all file types equally"""

    processor_code = '''
async def process_all_files_universally(attachments: List[Dict[str, Any]], issue_key: str, chat_id: str) -> None:
    """Universal file processor that treats all files equally"""

    logger.info(f"🔄 Processing {len(attachments)} attachments universally")

    success_count = 0
    error_count = 0

    for i, attachment in enumerate(attachments, 1):
        try:
            logger.info(f"🔄 Processing attachment {i}/{len(attachments)}")

            # Extract all possible identifiers
            att_id = attachment.get('id', '')
            filename = attachment.get('filename', f'file_{i}')
            mime_type = attachment.get('mimeType', attachment.get('contentType', ''))
            content_url = attachment.get('content', attachment.get('self', ''))

            # If no MIME type, infer from filename
            if not mime_type:
                mime_type = _infer_mime_type(filename)

            logger.info(f"  📁 File: {filename}")
            logger.info(f"  🆔 ID: {att_id}")
            logger.info(f"  📋 MIME: {mime_type}")
            logger.info(f"  🔗 URL: {content_url}")

            # Build all possible download URLs
            from src.jira_attachment_utils import build_attachment_urls, download_file_from_jira
            urls = build_attachment_urls(JIRA_DOMAIN, att_id, filename, content_url)

            logger.info(f"  📥 Download URLs ({len(urls)}): {urls[:3]}...")  # Show first 3

            # Try to download
            file_bytes = await download_file_from_jira(urls)

            if file_bytes:
                logger.info(f"  ✅ Downloaded {len(file_bytes)} bytes")

                # Send to Telegram
                await send_attachment_to_telegram({
                    'chat_id': chat_id,
                    'file_name': filename,
                    'file_bytes': file_bytes,
                    'mime_type': mime_type,
                    'issue_key': issue_key
                })

                success_count += 1
                logger.info(f"  ✅ Successfully sent to Telegram")

            else:
                logger.error(f"  ❌ Failed to download file")
                error_count += 1

        except Exception as e:
            logger.error(f"  ❌ Error processing attachment {i}: {e}", exc_info=True)
            error_count += 1

    logger.info(f"📊 Processing complete: {success_count} success, {error_count} errors")
'''

    return processor_code


def main():
    """Main function to analyze and fix the attachment processing issue"""

    print("🚀 ATTACHMENT PROCESSING ANALYSIS AND FIX")
    print("=" * 80)

    # Analyze the issue
    analyze_attachment_processing_issue()

    # Create debug tools
    debug_handler = create_debug_webhook_handler()
    universal_extractor = create_universal_attachment_extractor()
    universal_processor = create_universal_file_processor()

    print("\n🔧 CREATING COMPREHENSIVE FIX")
    print("=" * 40)

    # Write the debug handler
    with open("/home/Bot1/debug_webhook_handler.py", "w") as f:
        f.write(debug_handler)
    print("✅ Created debug webhook handler")

    # Write the universal extractor
    with open("/home/Bot1/universal_attachment_extractor.py", "w") as f:
        f.write(universal_extractor)
    print("✅ Created universal attachment extractor")

    # Write the universal processor
    with open("/home/Bot1/universal_file_processor.py", "w") as f:
        f.write(universal_processor)
    print("✅ Created universal file processor")

    print("\n🎯 NEXT STEPS:")
    print("1. Apply the universal attachment extraction logic")
    print("2. Update the webhook handler to use comprehensive extraction")
    print("3. Test with multiple file types")
    print("4. Monitor logs for debugging")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
