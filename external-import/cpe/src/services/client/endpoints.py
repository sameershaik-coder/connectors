"""
API URL VARIABLES
"""

from services.utils.configVariables import ConfigCPE  # type: ignore

# Base
config = ConfigCPE()
API_URL = config.base_url
API_VERSION = "/2.0"
BASE_URL = API_URL + API_VERSION
