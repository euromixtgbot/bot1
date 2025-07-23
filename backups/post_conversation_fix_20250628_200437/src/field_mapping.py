#field_mapping.py

import os
from pathlib import Path
import yaml
from typing import Dict

def load_field_mapping() -> Dict[str, str]:
    """
    Завантажує відповідність між змінними бота і полями Jira.
    
    Returns:
        Dict[str, str]: Dictionary with bot field names as keys and Jira field paths as values
        
    Raises:
        FileNotFoundError: If mapping file is not found
        yaml.YAMLError: If mapping file has invalid YAML syntax
    """
    # Get path to config directory
    config_dir = Path(__file__).parent.parent / 'config'
    mapping_file = os.getenv("FIELDS_MAPPING_FILE", "fields_mapping.yaml")
    mapping_path = config_dir / mapping_file

    if not mapping_path.exists():
        raise FileNotFoundError(f"Field mapping file not found: {mapping_path}")

    try:
        with mapping_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("Mapping file must contain a dictionary")
            return data
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML format in {mapping_file}: {str(e)}")

# Завантажуємо мапінг при імпорті
FIELD_MAP = load_field_mapping()
