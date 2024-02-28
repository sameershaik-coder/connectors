"""
API URL VARIABLES
"""

from services.utils.configVariables import ConfigOrkl  # type: ignore

# Base
config = ConfigOrkl()
API_URL = config.base_url
BASE_URL = API_URL

