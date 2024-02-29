import os

import yaml
from pycti import get_config_variable  # type: ignore

from .common import convert_hours_to_seconds
from .constants import CONFIG_FILE_PATH


class ConfigOrkl:
    def __init__(self):
        """
        Initialize the ORKL Connector with necessary configurations
        """

        # Load configuration file and connection helper
        self.load = self._load_config()
        self._initialize_configurations()

    @staticmethod
    def _load_config() -> dict:
        """
        Load the configuration from the YAML file
        :return: Configuration dictionary
        """
        config = (
            yaml.load(
                open(CONFIG_FILE_PATH),
                Loader=yaml.FullLoader,
            )
            if os.path.isfile(CONFIG_FILE_PATH)
            else {}
        )
        return config

    def _initialize_configurations(self) -> None:
        """
        Connector configuration variables
        """
        self.max_entries_to_proccess = get_config_variable(
            "ORKL_MAX_ENTRIES_TO_PROCESS",
            ["orkl", "max_entries_to_proccess"],
            self.load,
        )

        self.update_existing_data = get_config_variable(
            "CONNECTOR_UPDATE_EXISTING_DATA",
            ["connector", "update_existing_data"],
            self.load,
        )

        self.base_url = get_config_variable(
            "ORKL_BASE_URL",
            ["orkl", "base_url"],
            self.load,
        )

        self.api_key = get_config_variable(
            "ORKL_API_KEY",
            ["orkl", "api_key"],
            self.load,
        )
        
        self.orkl_sync_from_version = get_config_variable(
            "ORKL_SYNC_FROM_VERSION",
            ["orkl", "orkl_sync_from_version"],
            self.load,
        )

        self.config_interval = get_config_variable(
            "ORKL_INTERVAL",
            ["orkl", "interval"],
            self.load,
            isNumber=True,
        )

        self.interval = convert_hours_to_seconds(self.config_interval)

        self.max_date_range = get_config_variable(
            "ORKL_MAX_DATE_RANGE", ["orkl", "max_date_range"], self.load, isNumber=True
        )

        self.maintain_data = get_config_variable(
            "ORKL_MAINTAIN_DATA", ["orkl", "maintain_data"], self.load
        )

        self.pull_history = get_config_variable(
            "ORKL_PULL_HISTORY", ["orkl", "pull_history"], self.load
        )

        self.history_start_year = get_config_variable(
            "ORKL_HISTORY_START_YEAR",
            ["orkl", "history_start_year"],
            self.load,
            isNumber=True,
        )
