import os
import logging
import asyncio
import json
from typing import Dict, Any, List, Optional
import httpx
from src.field_mapping import FIELD_MAP
from utils.jira_field_mappings import get_field_value_by_name
from config.config import (
    JIRA_BASE_URL,
    JIRA_EMAIL,
    JIRA_API_TOKEN,
    JIRA_PROJECT_KEY,
    JIRA_ISSUE_TYPE,
    JIRA_REPORTER_ACCOUNT_ID,
)
from src.constants import JIRA_FIELD_MAPPINGS

class JiraApiError(Exception):
    """Custom exception for Jira API errors"""
    pass

# HTTP Basic Auth для Jira
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS_JSON = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

async def _make_request(method: str, url: str, **kwargs) -> Dict[str, Any]:
    """Unified request handler with error handling
    
    Args:
        method: HTTP method (GET, POST, etc)
        url: API endpoint URL
        **kwargs: Additional request parameters
        
    Returns:
        Dict[str, Any]: JSON response from the API
        
    Raises:
        JiraApiError: For API errors, network errors, or timeouts
    """
    # Define default timeouts if not provided
    if 'timeout' not in kwargs:
        kwargs['timeout'] = httpx.Timeout(10.0, connect=5.0)
    
    # Maximum number of retry attempts
    max_retries = 3
    retry_delay = 1  # Initial delay in seconds
    
    # Логируем деталі запиту
    request_body = kwargs.get('json', {})
    logger = logging.getLogger(__name__)
    logger.info(f"Making {method} request to {url}")
    logger.debug(f"Request body: {json.dumps(request_body, indent=2, ensure_ascii=False)}")
    
    # Use default AUTH
    auth = AUTH
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(auth=auth) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
        except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            if attempt == max_retries - 1:
                # This was the last attempt
                raise JiraApiError(f"Request timed out after {max_retries} attempts: {str(e)}") from e
            
            # Wait before retrying with exponential backoff
            await asyncio.sleep(retry_delay * (2 ** attempt))
            continue
        except httpx.HTTPStatusError as e:
            error_msg = f"Jira API error ({e.response.status_code})"
            
            try:
                error_details = e.response.json()
                logger.error(f"Jira API error response: {json.dumps(error_details, indent=2, ensure_ascii=False)}")
                
                # Extract detailed error information
                if "errorMessages" in error_details and error_details["errorMessages"]:
                    error_msg += f": {', '.join(error_details['errorMessages'])}"
                elif "errors" in error_details and error_details["errors"]:
                    error_parts = []
                    for field, msg in error_details["errors"].items():
                        error_parts.append(f"{field}: {msg}")
                    error_msg += f": {', '.join(error_parts)}"
                
                # Special handling for field validation errors (400 Bad Request)
                if e.response.status_code == 400 and isinstance(error_details, dict):
                    error_messages = error_details.get("errorMessages", [])
                    errors_dict = error_details.get("errors", {})
                    
                    # Log all error messages for better diagnosis
                    if error_messages:
                        logger.error(f"Validation error messages: {error_messages}")
                    if errors_dict:
                        logger.error(f"Field errors: {errors_dict}")
                        
                    # Check for specific field validation errors
                    for field_name, error_text in errors_dict.items():
                        logger.error(f"Field validation error for '{field_name}': {error_text}")
                        
                        # Specially handle custom field errors
                        if field_name in ["customfield_10069", "customfield_10065", "customfield_10068"]:
                            field_label = {
                                "customfield_10069": "Балансова Одиниця (Підрозділ)",
                                "customfield_10065": "Departament",
                                "customfield_10068": "Service"
                            }.get(field_name, field_name)
                            
                            logger.error(f"❌ Помилка валідації для кастомного поля {field_label} ({field_name}): {error_text}")
            except Exception as parse_error:
                logger.error(f"Failed to parse error response: {str(parse_error)}")
                try:
                    # Try to get raw response text if JSON parsing fails
                    error_msg += f": {e.response.text[:200]}"
                except Exception:
                    pass
            
            logger.error(f"HTTP Error: {error_msg}")
            raise JiraApiError(error_msg) from e
        except httpx.RequestError as e:
            raise JiraApiError(f"Network error: {str(e)}") from e
    
    # This point should never be reached, but added for type safety
    raise JiraApiError(f"Request failed after {max_retries} attempts with no specific error")

def build_jira_payload(bot_vars: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Формує JSON для Jira Issue на основі bot_vars і FIELD_MAP.
    
    Args:
        bot_vars (Dict[str, Any]): Словник з ключами, як у YAML 
            (наприклад, 'division', 'service', 'telegram_id' тощо)
    
    Returns:
        Dict[str, Dict[str, Any]]: Структурований JSON для створення Issue в Jira
    
    Examples:
        >>> vars = {"summary": "Test Issue", "issuetype": "Task"}
        >>> build_jira_payload(vars)
        {'fields': {'summary': 'Test Issue', 'issuetype': {'name': 'Task'}}}
    """
    fields: Dict[str, Any] = {}
    logger = logging.getLogger(__name__)
    
    # Обязательно добавляем проект если он не был добавлен ранее
    if "project" in bot_vars and "project" not in fields:
        fields["project"] = {"key": bot_vars["project"]}
    
    # Маппінг полів з вкладеними об'єктами
    nested_fields = {
        "issuetype.name": ("issuetype", "name"),
        "reporter.accountId": ("reporter", "accountId"),
        "project.key": ("project", "key")
    }
    
    for var_name, value in bot_vars.items():
        jira_field = FIELD_MAP.get(var_name)
        if not jira_field or value is None:
            continue

        # Log field mapping for debugging
        logger.info(f"Mapping field {var_name} -> {jira_field} = {value}")

        # Обробка базових полів
        if jira_field == "summary":
            fields[jira_field] = str(value)
        elif jira_field == "customfield_10145":  # telegram_id field
            fields[jira_field] = str(value)
        elif jira_field == "customfield_10146":  # telegram_username field
            # Only add telegram_username if it has a value
            if value and str(value).strip():
                fields[jira_field] = str(value)
        elif jira_field == "description":
            # Convert to Atlassian Document Format
            fields[jira_field] = {
                "version": 1,
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": str(value)
                            }
                        ]
                    }
                ]
            }
            logger.info(f"Converting description to Atlassian Document Format")
        
        # Обробка вкладених полів
        elif jira_field in nested_fields:
            parent, child = nested_fields[jira_field]
            fields.setdefault(parent, {})[child] = value
        
        # Обробка кастомних полів
        elif jira_field in ("customfield_10069", "customfield_10065", "customfield_10068"):
            # These are select fields that need specific format with ID
            if isinstance(value, dict) and ('name' in value or 'id' in value):
                # Value is already properly formatted
                fields[jira_field] = value
            else:
                # Get properly formatted field value using our centralized mappings
                str_value = str(value)
                
                # Маппинг кастомных полей в типы полей
                field_type_mapping = {
                    "customfield_10069": "division",
                    "customfield_10065": "department",
                    "customfield_10068": "service"
                }
                
                # Получаем тип поля для использования в get_field_value_by_name
                field_type = field_type_mapping.get(jira_field)
                
                if field_type:
                    fields[jira_field] = get_field_value_by_name(str_value, field_type)
                    logger.info(f"Using field mapping for {jira_field}: {str_value} -> {fields[jira_field]}")
                else:
                    fields[jira_field] = {"name": str_value}
                    logger.warning(f"Unknown field type for {jira_field}, using default format: {fields[jira_field]}")
        else:
            fields[jira_field] = value
            
    # Проверка наличия обязательных полей
    if "project" not in fields:
        fields["project"] = {"key": "SD"}  # Устанавливаем проект по умолчанию
        
    # Проверяем, что поле issuetype правильно сформировано
    if "issuetype" in fields and isinstance(fields["issuetype"], dict) and "name" not in fields["issuetype"]:
        # Если issuetype — словарь без name, добавляем name
        if isinstance(bot_vars.get("issuetype"), str):
            fields["issuetype"]["name"] = bot_vars["issuetype"]
    elif "issuetype" in fields and not isinstance(fields["issuetype"], dict):
        # Если issuetype не словарь, преобразуем его
        value = fields["issuetype"]
        fields["issuetype"] = {"name": value}

    return {"fields": fields}

async def create_jira_issue(fields: Dict) -> str:
    """
    Створює нову задачу в Jira.
    
    Raises:
        JiraApiError: If API request fails or response is invalid
    """
    logger = logging.getLogger(__name__)
    
    if not fields.get('fields'):
        raise ValueError("Missing 'fields' in payload")
    
    # Проверка наличия обязательных полей
    required_fields = ['project', 'issuetype', 'summary']
    missing_fields = [field for field in required_fields if field not in fields.get('fields', {})]
    
    if missing_fields:
        error_msg = f"Missing required fields: {missing_fields} in payload: {fields}"
        logger.error(f"Jira API Error: {error_msg}")
        raise ValueError(error_msg)
    
    # Дополнительная проверка формата project поля
    project_field = fields.get('fields', {}).get('project')
    if project_field and not isinstance(project_field, dict):
        fields['fields']['project'] = {"key": project_field}
        logger.warning(f"Автоматически исправлен формат поля project: {project_field} -> {fields['fields']['project']}")
        
    # Проверяем формат кастомных полей перед отправкой
    _ensure_correct_custom_fields_format(fields)
    
    # Дополнительная проверка формата issuetype поля
    issuetype_field = fields.get('fields', {}).get('issuetype')
    if issuetype_field and not isinstance(issuetype_field, dict):
        fields['fields']['issuetype'] = {"name": issuetype_field}
        logger.warning(f"Автоматически исправлен формат поля issuetype: {issuetype_field} -> {fields['fields']['issuetype']}")
    
    # Список проблемных полей, которые могут вызвать ошибки валидации
    problematic_fields = []
    # Определяем кастомные поля, которые могут быть проблемными
    custom_fields = {
        "customfield_10069": "Балансова Одиниця (Підрозділ)",
        "customfield_10065": "Departament",
        "customfield_10068": "Service"
    }
    
    # Сохраняем оригинальный payload для логов
    original_fields = json.loads(json.dumps(fields))
    
    # Максимальное количество попыток создания задачи с удалением проблемных полей
    max_attempts = 4  # Одна попытка с полным payload + до 3 попыток с удалением полей
    attempt = 1
    
    while attempt <= max_attempts:
        try:
            url = f"{JIRA_BASE_URL}/rest/api/3/issue"
            
            if attempt == 1:
                logger.info(f"Отправка запроса на создание задачи в Jira (попытка {attempt}): {url}")
            else:
                logger.info(f"Повторная попытка ({attempt}) создания задачи с модифицированными полями: {url}")
                
                # Log which fields were removed
                if problematic_fields:
                    logger.info(f"Удалены проблемные поля: {problematic_fields}")
            
            # Log the payload for debugging
            logger.info(f"Payload: {json.dumps(fields, indent=2, ensure_ascii=False)}")
            
            # Validate reporter field if present
            reporter_field = fields.get('fields', {}).get('reporter')
            if reporter_field:
                # Ensure proper format for reporter field regardless of input format
                if JIRA_REPORTER_ACCOUNT_ID:
                    # Always set to the default reporter if we have one available
                    fields['fields']['reporter'] = {"accountId": JIRA_REPORTER_ACCOUNT_ID}
                    logger.info(f"Using default reporter accountId: {JIRA_REPORTER_ACCOUNT_ID}")
                elif not isinstance(reporter_field, dict):
                    # Try to convert string format to dict format
                    fields['fields']['reporter'] = {"accountId": str(reporter_field)}
                    logger.info(f"Converting reporter format: {reporter_field} -> {fields['fields']['reporter']}")
                elif isinstance(reporter_field, dict) and 'accountId' in reporter_field:
                    if isinstance(reporter_field['accountId'], dict):
                        # Fix nested dict issue
                        accountId = reporter_field['accountId'].get('accountId')
                        fields['fields']['reporter'] = {"accountId": accountId}
                        logger.info(f"Fixed nested reporter accountId format: {accountId}")
                
            # Process custom fields
            for cf_id, cf_name in custom_fields.items():
                if cf_id in fields.get('fields', {}) and cf_id not in problematic_fields:
                    value = fields['fields'][cf_id]
                    # Ensure the field has the correct format
                    if isinstance(value, dict) and ('id' in value or 'name' in value):
                        logger.info(f"Field {cf_name} ({cf_id}) already in correct format: {value}")
                    else:
                        # If the value is a string, we need to convert it to a proper format
                        str_value = str(value) if not isinstance(value, dict) else str(value.get('name', ''))
                        
                        # Use our centralized field mappings to format the value
                        fields['fields'][cf_id] = get_field_value_by_name(cf_id, str_value)
                        logger.info(f"Using field mapping for {cf_name} ({cf_id}): {str_value} -> {fields['fields'][cf_id]}")
                        
            # Ensure description is in Atlassian Document Format
            if 'description' in fields.get('fields', {}) and not isinstance(fields['fields']['description'], dict):
                description_text = str(fields['fields']['description'])
                fields['fields']['description'] = {
                    "version": 1,
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description_text
                                }
                            ]
                        }
                    ]
                }
                logger.info("Fixed description format to Atlassian Document Format")
            
            # Make the API request
            response = await _make_request("POST", url, json=fields, headers=HEADERS_JSON)
            
            if not response or not response.get("key"):
                logger.error(f"Invalid response format, no key found: {json.dumps(response, indent=2, ensure_ascii=False)[:200]}...")
                raise JiraApiError("Failed to get issue key from response")
            
            # Verify that the issue was created by fetching it
            issue_key = response["key"]
            try:
                # Quick check to confirm issue exists
                verify_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
                verification = await _make_request("GET", verify_url, headers=HEADERS_JSON)
                if verification and verification.get("key") == issue_key:
                    logger.info(f"Успешно подтверждено создание задачи с ключом: {issue_key}")
                else:
                    logger.warning(f"Created issue {issue_key} but couldn't verify it properly")
            except Exception as e:
                # Log but don't fail if verification has issues
                logger.warning(f"Created issue {issue_key} but verification failed: {str(e)}")
            
            # Log which fields were removed in successful attempt
            if problematic_fields:
                logger.info(f"✅ Задача успішно створена після видалення проблемних полів: {problematic_fields}")
            else:
                logger.info(f"✅ Задача успішно створена з усіма полями")
                
            logger.info(f"Успешно создана задача с ключом: {issue_key}")
            return issue_key
            
        except JiraApiError as e:
            error_message = str(e)
            logger.error(f"Jira API Error (попытка {attempt}): {error_message}")
            
            # Проверка на ошибки валидации полей
            validation_errors = {
                "customfield_10069": ["Балансова Одиниця", "допустим", "Підрозділ"],
                "customfield_10065": ["Departament", "допустим"],
                "customfield_10068": ["Service", "допустим"],
                "reporter": ["reporter", "допустим", "укажите допустимое значение", "укажите"]
            }
            
            field_to_remove = None
            
            # Проверяем каждое проблемное поле в тексте ошибки
            for field_id, keywords in validation_errors.items():
                # Если поле уже в списке проблемных или его нет в payload, пропускаем
                if field_id in problematic_fields or field_id not in fields.get('fields', {}):
                    continue
                
                # Проверяем ключевые слова в тексте ошибки (нечувствительно к регистру)
                error_message_lower = error_message.lower()
                
                # Специальная проверка для reporter
                if field_id == "reporter" and '"reporter":' in error_message_lower:
                    field_to_remove = field_id
                    logger.info(f"Обнаружена ошибка валидации для поля reporter по точному совпадению в JSON")
                    break
                
                if any(keyword.lower() in error_message_lower for keyword in keywords):
                    field_to_remove = field_id
                    field_name = custom_fields.get(field_id, field_id)
                    logger.info(f"Обнаружена ошибка валидации для поля {field_name} ({field_id})")
                    break
            
            # Если нашли проблемное поле и это не последняя попытка
            if field_to_remove and attempt < max_attempts:
                problematic_fields.append(field_to_remove)
                
                # Специальная обработка для поля reporter - заменить вместо удаления
                if field_to_remove == "reporter":
                    if JIRA_REPORTER_ACCOUNT_ID:
                        logger.info(f"Заменяю проблемное поле reporter на значение по умолчанию: {JIRA_REPORTER_ACCOUNT_ID}")
                        fields['fields']["reporter"] = {"accountId": JIRA_REPORTER_ACCOUNT_ID}
                    else:
                        logger.info(f"Удаляю проблемное поле reporter, так как JIRA_REPORTER_ACCOUNT_ID не установлен")
                        if "reporter" in fields.get('fields', {}):
                            del fields['fields']["reporter"]
                else:
                    logger.info(f"Удаляю проблемное поле {field_to_remove} и повторяю попытку")
                    # Удаляем поле из payload
                    if field_to_remove in fields.get('fields', {}):
                        del fields['fields'][field_to_remove]
                
                # Увеличиваем счетчик попыток
                attempt += 1
                continue
            else:
                # Если не нашли проблемное поле или это последняя попытка
                logger.error(f"Не удалось создать задачу после {attempt} попыток")
                logger.error(f"Последняя ошибка: {error_message}")
                logger.error(f"Оригинальный payload: {json.dumps(original_fields, indent=2, ensure_ascii=False)[:200]}...")
                raise JiraApiError(f"Failed to create Jira issue after {attempt} attempts: {error_message}")
                
        except Exception as e:
            error_msg = f"Failed to create Jira issue: {str(e)}"
            logger.error(f"{error_msg}. Payload: {json.dumps(fields, indent=2, ensure_ascii=False)[:200]}...")
            raise JiraApiError(error_msg) from e
    
    # This point should never be reached, but added for type safety
    raise JiraApiError(f"Failed to create Jira issue after {max_attempts} attempts with no specific error")

async def get_issue_details(issue_key: str, fields: List[str]) -> Dict[str, Any]:
    """
    Отримує деталі задачі з Jira.
    
    Args:
        issue_key (str): Ключ задачі (e.g., "PRJ-123")
        fields (List[str]): Список полів для отримання
    
    Raises:
        JiraApiError: If API request fails
        ValueError: If issue_key is invalid
    """
    if not issue_key or not issue_key.strip():
        raise ValueError("Invalid issue key")
        
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    params = {"fields": ",".join(fields)}
    return await _make_request("GET", url, params=params, headers=HEADERS_JSON)

async def find_open_issues(telegram_id: str) -> List[Dict[str, str]]:
    """
    Шукає відкриті задачі користувача за Telegram ID.
    
    Raises:
        JiraApiError: If API request fails
        ValueError: If telegram_id is invalid
    """
    if not telegram_id:
        raise ValueError("Invalid Telegram ID (None)")

    # Нормалізуємо ID: видаляємо пробіли і апострофи
    normalized_id = str(telegram_id).strip().replace("'", "").replace('"', "")
    
    if not normalized_id:
        raise ValueError("Invalid Telegram ID (empty after normalization)")

    # Додаємо логування
    logger = logging.getLogger(__name__)
    logger.info(f"find_open_issues: пошук задач для Telegram ID: '{telegram_id}' (нормалізовано: '{normalized_id}')")

    # Використовуємо оператор "~" (contains) замість "=" для більш гнучкого пошуку
    jql = (
        f'project = {JIRA_PROJECT_KEY} '
        f'AND "Telegram ID" ~ "{normalized_id}" '
        'AND statusCategory != Done'
    )
    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    logger.info(f"find_open_issues: JQL запит: {jql}")
    
    response = await _make_request(
        "GET", 
        url, 
        params={"jql": jql, "fields": "status"},
        headers=HEADERS_JSON
    )
    
    # Додаємо логування відповіді
    logger.info(f"find_open_issues: відповідь від Jira: {str(response)[:200]}...")
    logger.info(f"find_open_issues: кількість issues в відповіді: {len(response.get('issues', []))}")
    
    # Логуємо повну відповідь від Jira для діагностики
    logger.info(f"find_open_issues: відповідь від Jira: {json.dumps(response)[:200]}...")
    
    # Перевіряємо наявність ключа issues в відповіді
    issues = response.get("issues", [])
    logger.info(f"find_open_issues: кількість issues в відповіді: {len(issues)}")
    
    result = [{
        "key": issue["key"],
        "status": issue["fields"]["status"]["name"]
    } for issue in issues]
    
    logger.info(f"find_open_issues: знайдено {len(result)} задач")
    if result:
        for issue in result:
            logger.info(f"find_open_issues: задача {issue['key']} зі статусом {issue['status']}")
    
    return result

async def find_done_issues(telegram_id: str) -> List[Dict[str, str]]:
    """
    Шукає виконані (завершені) задачі користувача за Telegram ID.
    
    Raises:
        JiraApiError: If API request fails
        ValueError: If telegram_id is invalid
    """
    if not telegram_id:
        raise ValueError("Invalid Telegram ID (None)")

    # Нормалізуємо ID: видаляємо пробіли і апострофи
    normalized_id = str(telegram_id).strip().replace("'", "").replace('"', "")
    
    if not normalized_id:
        raise ValueError("Invalid Telegram ID (empty after normalization)")

    # Додаємо логування
    logger = logging.getLogger(__name__)
    logger.info(f"find_done_issues: пошук завершених задач для Telegram ID: '{telegram_id}' (нормалізовано: '{normalized_id}')")

    # Шукаємо задачі зі статусом Done
    jql = (
        f'project = {JIRA_PROJECT_KEY} '
        f'AND "Telegram ID" ~ "{normalized_id}" '
        'AND statusCategory = Done'
    )
    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    logger.info(f"find_done_issues: JQL запит: {jql}")
    
    response = await _make_request(
        "GET", 
        url, 
        params={"jql": jql, "fields": "status"},
        headers=HEADERS_JSON
    )
    
    # Логування відповіді
    logger.info(f"find_done_issues: кількість завершених задач в відповіді: {len(response.get('issues', []))}")
    
    # Перевіряємо наявність ключа issues в відповіді
    issues = response.get("issues", [])
    
    result = [{
        "key": issue["key"],
        "status": issue["fields"]["status"]["name"]
    } for issue in issues]
    
    logger.info(f"find_done_issues: знайдено {len(result)} завершених задач")
    if result:
        for issue in result:
            logger.info(f"find_done_issues: задача {issue['key']} зі статусом {issue['status']}")
    
    return result

async def add_comment_to_jira(issue_key: str, comment: str, author_name: Optional[str] = None) -> None:
    """
    Додає коментар до Jira Issue з опціональним заголовком автора.
    
    Args:
        issue_key: Ключ задачі Jira
        comment: Текст коментаря
        author_name: ПІБ автора повідомлення (додається як заголовок)
    
    Raises:
        JiraApiError: If API request fails
        ValueError: If issue_key or comment is invalid
    """
    if not issue_key or not comment:
        raise ValueError("Invalid issue key or empty comment")
        
    # Додаємо заголовок автора, якщо вказано
    if author_name:
        full_comment = f"**Ім'я: {author_name} додав коментар:**\n\n{comment}"
    else:
        full_comment = comment
        
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    
    # Спрощений формат ADF (Atlassian Document Format)
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "text": full_comment,
                            "type": "text"
                        }
                    ]
                }
            ]
        }
    }
    
    # Додаємо логування для діагностики
    logger = logging.getLogger(__name__)
    logger.info(f"Відправляємо коментар до {issue_key}: {json.dumps(payload)[:100]}...")
    
    try:
        await _make_request("POST", url, json=payload, headers=HEADERS_JSON)
        logger.info(f"Коментар успішно додано до {issue_key}")
    except Exception as e:
        logger.error(f"Помилка при додаванні коментаря до {issue_key}: {str(e)}")
        raise

async def attach_file_to_jira(issue_key: str, filename: str, content: bytes) -> None:
    """
    Додає вкладення до Jira Issue.
    
    Raises:
        JiraApiError: If API request fails
        ValueError: If parameters are invalid
    """
    if not all([issue_key, filename, content]):
        raise ValueError("Missing required parameters")
        
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/attachments"
    headers = {"X-Atlassian-Token": "no-check"}
    
    try:
        async with httpx.AsyncClient(auth=AUTH) as client:
            # Перетворюємо bytearray в bytes якщо потрібно
            if isinstance(content, bytearray):
                content = bytes(content)
                
            files = {"file": (filename, content, "application/octet-stream")}
            response = await client.post(url, headers=headers, files=files)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        error_msg = f"Jira API error ({e.response.status_code})"
        try:
            error_details = e.response.json()
            error_msg += f": {error_details.get('errorMessages', ['Unknown error'])[0]}"
        except Exception:
            pass
        raise JiraApiError(error_msg) from e
    except httpx.RequestError as e:
        raise JiraApiError(f"Network error: {str(e)}") from e

# New retrieval functions
async def get_issue_status(issue_key: str) -> Dict[str, str]:
    """Get issue status information"""
    response = await get_issue_details(issue_key, ["status"])
    status = response["fields"]["status"]
    return {
        "name": status["name"],
        "category": status["statusCategory"]["name"]
    }

async def get_issue_summary(issue_key: str) -> Dict[str, str]:
    """Get issue summary and description"""
    response = await get_issue_details(issue_key, ["summary", "description"])
    return {
        "summary": response["fields"]["summary"],
        "description": response["fields"].get("description", "")
    }
    
async def get_full_issue_info(issue_key: str) -> Dict[str, Any]:
    """
    Отримує повну інформацію про задачу, включаючи статус, опис, ПІБ та інші поля.
    
    Args:
        issue_key (str): Ключ задачі (e.g., "PRJ-123")
        
    Returns:
        Dict[str, Any]: Словник з повною інформацією про задачу
    """
    fields = [
        "status", 
        "summary", 
        "description", 
        "created", 
        "reporter",  # Додаємо репортера
        "customfield_10065",  # Додайте тут реальні ID полів для ПІБ, підрозділу та департаменту
        "customfield_10068",  # service
        "customfield_10069",  # division
    ]
    
    response = await get_issue_details(issue_key, fields)
    fields_data = response["fields"]
    
    # Форматуємо дату створення в зрозумілому форматі
    created_date = fields_data.get("created", "")
    if created_date:
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
            created_date = dt.strftime("%d.%m.%Y, %H:%М")  # Fixed Cyrillic 'М' to Latin 'M'
        except Exception:
            pass
    
        # Отримуємо коментарі, якщо вони є
    comments_data = fields_data.get("comment", {}).get("comments", [])
    
    # Додаємо логування для розуміння структури коментарів
    import logging
    if comments_data:
        logging.info(f"Отримано {len(comments_data)} коментарів для задачі {issue_key}")
        logging.info(f"Структура першого коментаря: {str(comments_data[0])[:200]}...")
    else:
        logging.info(f"Коментарі для задачі {issue_key} відсутні")
    
    return {
        "key": issue_key,
        "status": fields_data.get("status", {}).get("name", "Невідомо"),
        "summary": fields_data.get("summary", ""),
        "description": fields_data.get("description", ""),
        "created": created_date,
        "reporter_name": fields_data.get("reporter", {}).get("displayName", "Невідомо"),
        "service": fields_data.get("customfield_10068", "Невідомо"),
        "division": fields_data.get("customfield_10069", "Невідомо"),
        "department": fields_data.get("customfield_10065", "Невідомо"),  # Додаємо поле департаменту
        "comments": comments_data,  # Додаємо коментарі до результату
        # Решта полів додати по необхідності
    }

def _ensure_correct_custom_fields_format(payload: Dict[str, Any]) -> None:
    """
    Проверяет и корректирует формат кастомных полей перед отправкой в Jira API.
    
    Args:
        payload: Словарь с данными для отправки в Jira API
    """
    logger = logging.getLogger(__name__)
    
    custom_fields = (
        "customfield_10069",  # Балансова Одиниця (Підрозділ)
        "customfield_10065",  # Departament
        "customfield_10068"   # Service
    )
    
    # Маппинги идентификаторов из constants.py
    field_mappings = {
        "customfield_10069": JIRA_FIELD_MAPPINGS.get("customfield_10069", {}),  # DIVISION_ID_MAPPINGS
        "customfield_10065": JIRA_FIELD_MAPPINGS.get("customfield_10065", {}),  # DEPARTMENT_ID_MAPPINGS
        "customfield_10068": JIRA_FIELD_MAPPINGS.get("customfield_10068", {})   # SERVICE_ID_MAPPINGS
    }
    
    fields = payload.get("fields", {})
    
    for field_id in custom_fields:
        if (field_id in fields):
            field_value = fields[field_id]
            field_name = {
                "customfield_10069": "Балансова Одиниця (Підрозділ)",
                "customfield_10065": "Departament",
                "customfield_10068": "Service"
            }.get(field_id, field_id)
            
            # Проверяем, что поле имеет правильный формат
            if isinstance(field_value, dict):
                # Если есть другие ключи, кроме 'id', оставляем только 'id'
                if 'id' in field_value:
                    if len(field_value) > 1 or field_value.get('name') == field_id:
                        id_value = field_value['id']
                        fields[field_id] = {"id": id_value}
                        logger.info(f"Field {field_name} ({field_id}) already in correct format with ID: {fields[field_id]}")
                        
                        # Дополнительная проверка валидности ID
                        mapping = field_mappings.get(field_id, {})
                        valid_ids = [entry.get("id") for entry in mapping.values() if entry.get("id")]
                        if valid_ids and id_value not in valid_ids:
                            logger.warning(f"⚠️ Возможно неверное значение ID для поля {field_name}: {id_value} не найдено в списке допустимых значений!")
                            
                elif 'name' in field_value and field_value['name'] != field_id:
                    # Оставляем только name, если это не имя самого поля
                    name_value = field_value['name']
                    fields[field_id] = {"name": name_value}
                    logger.info(f"Field {field_name} ({field_id}) corrected to use name: {fields[field_id]}")
                    
                    # Проверяем есть ли соответствующее значение в маппинге
                    mapping = field_mappings.get(field_id, {})
                    found = False
                    for key, value in mapping.items():
                        if key == name_value or value.get("name") == name_value:
                            found = True
                            # Заменяем на объект с ID, если возможно
                            if value.get("id"):
                                fields[field_id] = {"id": value["id"]}
                                logger.info(f"Заменено name на id для {field_name}: {name_value} -> {fields[field_id]}")
                            break
                    
                    if not found:
                        logger.warning(f"⚠️ Имя '{name_value}' для поля {field_name} не найдено в маппинге!")
                else:
                    logger.warning(f"Field {field_name} ({field_id}) has invalid format: {field_value}")
            else:
                # Если значение не словарь, пробуем найти его в маппингах
                str_value = str(field_value)
                mapping = field_mappings.get(field_id, {})
                
                if str_value.isdigit():
                    fields[field_id] = {"id": str_value}
                    logger.info(f"Field {field_name} ({field_id}) converted to ID format: {fields[field_id]}")
                elif str_value in mapping:
                    # Используем ID из маппинга
                    fields[field_id] = {"id": mapping[str_value].get("id", "")}
                    logger.info(f"Field {field_name} ({field_id}) mapped from name to ID: {str_value} -> {fields[field_id]}")
                else:
                    # Если не нашли в маппинге, используем как имя
                    fields[field_id] = {"name": str_value}
                    logger.info(f"Field {field_name} ({field_id}) converted to name format: {fields[field_id]}")
                    logger.warning(f"⚠️ Имя '{str_value}' для поля {field_name} не найдено в маппинге!")

async def find_user_by_jira_issue_key(issue_key: str) -> Optional[Dict[str, Any]]:
    """
    Finds a Telegram user based on a Jira issue key by looking up the Telegram ID field.
    
    Args:
        issue_key (str): The Jira issue key (e.g., "PRJ-123")
        
    Returns:
        Optional[Dict[str, Any]]: User data if found, including at least telegram_id, or None if not found
        
    Raises:
        JiraApiError: If API request fails
        ValueError: If issue_key is invalid
    """
    if not issue_key or not issue_key.strip():
        raise ValueError("Invalid issue key")
    
    logger = logging.getLogger(__name__)
    logger.info(f"Looking up Telegram user for issue {issue_key}")
    
    # Get issue details including the telegram_id custom field
    try:
        response = await get_issue_details(issue_key, ["customfield_10145"])  # telegram_id field
        
        fields = response.get("fields", {})
        telegram_id = fields.get("customfield_10145")
        
        if not telegram_id:
            logger.warning(f"No Telegram ID found for issue {issue_key}")
            return None
            
        # Normalize the Telegram ID
        normalized_id = str(telegram_id).strip().replace("'", "").replace('"', "")
        
        if not normalized_id:
            logger.warning(f"Invalid Telegram ID format for issue {issue_key}")
            return None
            
        logger.info(f"Found Telegram ID {normalized_id} for issue {issue_key}")
        
        return {
            "telegram_id": normalized_id,
            "issue_key": issue_key,
        }
        
    except Exception as e:
        logger.error(f"Error finding user for issue {issue_key}: {str(e)}")
        return None

async def add_internal_note_to_jira(issue_key: str, note_text: str) -> None:
    """
    Додає внутрішню примітку (internal note) до Jira Issue.
    
    Внутрішня примітка - це коментар, який видно тільки користувачам Jira, а не клієнтам.
    
    Raises:
        JiraApiError: If API request fails
        ValueError: If issue_key or note_text is invalid
    """
    if not issue_key or not note_text:
        raise ValueError("Invalid issue key or empty note text")
        
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    
    # Спрощений формат ADF (Atlassian Document Format) з властивістю internal=true
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "text": note_text,
                            "type": "text"
                        }
                    ]
                }
            ]
        },
        "properties": [
            {
                "key": "sd.public.comment",
                "value": {
                    "internal": True
                }
            }
        ]
    }
    
    # Додаємо логування для діагностики
    logger = logging.getLogger(__name__)
    logger.info(f"Додаємо внутрішню примітку до {issue_key}")
    
    try:
        await _make_request("POST", url, json=payload, headers=HEADERS_JSON)
        logger.info(f"Внутрішня примітка успішно додана до {issue_key}")
    except Exception as e:
        logger.error(f"Помилка при додаванні внутрішньої примітки до {issue_key}: {str(e)}")
        raise JiraApiError(f"Failed to add internal note: {str(e)}")

async def add_comment_with_file_reference_to_jira(issue_key: str, comment: str, author_name: Optional[str] = None, filename: Optional[str] = None, file_content: bytes = b"") -> None:
    """
    Додає коментар до Jira Issue з посиланням на файл та прикріплює файл.
    
    Args:
        issue_key: Ключ задачі Jira
        comment: Текст коментаря
        author_name: ПІБ автора повідомлення (додається як заголовок)
        filename: Назва файлу
        file_content: Вміст файлу в байтах
    
    Raises:
        JiraApiError: If API request fails
        ValueError: If issue_key is invalid
    """
    if not issue_key:
        raise ValueError("Invalid issue key")
    
    logger = logging.getLogger(__name__)
    
    # Спочатку прикріплюємо файл, якщо він є
    attachment_url = None
    if filename and file_content:
        try:
            attachment_response = await attach_file_to_jira(issue_key, filename, file_content)
            logger.info(f"Файл {filename} успішно прикріплено до {issue_key}")
            
            # Отримуємо URL прикріпленого файлу
            if attachment_response and len(attachment_response) > 0:
                attachment_id = attachment_response[0].get('id')
                if attachment_id:
                    attachment_url = f"{JIRA_BASE_URL}/secure/attachment/{attachment_id}/{filename}"
                    logger.info(f"URL файлу: {attachment_url}")
        except Exception as e:
            logger.error(f"Помилка при прикріпленні файлу {filename} до {issue_key}: {str(e)}")
            # Продовжуємо навіть якщо файл не вдалось прикріпити
    
    # Додаємо заголовок автора, якщо вказано
    if author_name:
        header_text = f"**Ім'я: {author_name} додав коментар:**\n\n"
    else:
        header_text = ""
    
    # Формуємо коментар з посиланням на файл у форматі ADF
    if attachment_url and filename:
        if comment and comment.strip():
            full_comment_text = f"{header_text}{comment}\n\n"
        else:
            full_comment_text = f"{header_text}"
        
        # Створюємо коментар з посиланням на файл у форматі ADF
        url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
        
        # ADF payload з посиланням на файл
        adf_content = [
            {
                "type": "paragraph",
                "content": [
                    {
                        "text": full_comment_text,
                        "type": "text"
                    }
                ]
            }
        ]
        
        # Додаємо посилання на файл
        adf_content.append({
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": "📎 Прикріплено файл: "
                },
                {
                    "type": "text",
                    "text": filename,
                    "marks": [
                        {
                            "type": "link",
                            "attrs": {
                                "href": attachment_url,
                                "title": filename
                            }
                        }
                    ]
                }
            ]
        })
        
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": adf_content
            }
        }
        
        try:
            await _make_request("POST", url, json=payload, headers=HEADERS_JSON)
            logger.info(f"Коментар з посиланням на файл успішно додано до {issue_key}")
        except Exception as e:
            logger.error(f"Помилка при додаванні коментаря з посиланням на файл до {issue_key}: {str(e)}")
            raise
    else:
        # Якщо немає файлу або URL, створюємо звичайний коментар
        full_comment = f"{header_text}{comment}" if comment else f"{header_text}Файл прикріплено"
        await add_comment_to_jira(issue_key, full_comment, None)  # author_name вже додано до тексту

