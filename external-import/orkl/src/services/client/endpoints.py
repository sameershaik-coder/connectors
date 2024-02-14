"""
API URL VARIABLES
"""

from services.utils.configVariables import ConfigCPE  # type: ignore

# Base
config = ConfigCPE()
API_URL = config.base_url
BASE_URL = API_URL

