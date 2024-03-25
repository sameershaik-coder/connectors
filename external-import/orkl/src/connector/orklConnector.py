import json
import sys
import time
from datetime import datetime, timedelta, timezone

from pycti import OpenCTIConnectorHelper  # type: ignore
from services import OrklConverter  # type: ignore
from services.utils import MAX_AUTHORIZED, ConfigOrkl  # type: ignore
import os
from services.utils import get_json_object_from_file,write_json_to_file
from pathlib import Path

class OrklConnector:
    def __init__(self):
        """
        Initialize the orklConnector with necessary configurations
        """

        # Load configuration file and connection helper
        self.config = ConfigOrkl()
        self.helper = OpenCTIConnectorHelper(self.config.load)
        self.converter = OrklConverter(self.helper)

    def run(self) -> None:
        """
        Main execution loop procedure for orkl connector
        """
        self.helper.log_info("[CONNECTOR] Fetching datasets...")
        get_run_and_terminate = getattr(self.helper, "get_run_and_terminate", None)
        if callable(get_run_and_terminate) and self.helper.get_run_and_terminate():
            self.handle_sync()
            self.helper.force_ping()
        else:
            while True:
                self.handle_sync()

    def _initiate_work(self, timestamp: int) -> str:
        """
        Initialize a work
        :param timestamp: Timestamp in integer
        :return: Work id in string
        """
        utc_time = datetime.fromtimestamp(timestamp, timezone.utc)
        work_description = f"{self.helper.connect_name} run @ {utc_time.strftime('%Y-%m-%d %H:%M:%S')}"
        return self.helper.api.work.initiate_work(self.helper.connect_id, work_description)

    def update_connector_state(self, current_time: int, work_id: str) -> None:
        """
        Update the connector state
        :param current_time: Time in int
        :param work_id: Work id in string
        """
        try:
            utc_time = datetime.fromtimestamp(current_time, timezone.utc)
            msg = (
                f"[CONNECTOR] Connector successfully run, storing last_run as "
                f"{utc_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.helper.log_info(msg)
            self.helper.api.work.to_processed(work_id, msg)
            self.helper.set_state({"last_run": current_time})

            interval_in_hours = round(self.config.interval / 60 / 60, 2)
            self.helper.log_info(
                "[CONNECTOR] Last_run stored, next run in: "
                + str(interval_in_hours)
                + " hours"
            )
        except Exception as e:
            self.helper.log_info(
                "[CONNECTOR] Last_run store failed with following exception : {e}, next run in: "
                + str(interval_in_hours)
                + " hours"
            )
            

    
    def get_interval(self):
        """
        Get the interval from the config and return it.
        """
        return self.config.interval


    def _maintain_data(self, now: datetime, last_run: float, work_id: str) -> None:
        """
        Maintain data updated if maintain_data config is True
        :param now: Current date in datetime
        :param last_run: Last run date in float
        :param work_id: Work id in str
        """
        self.helper.log_info("[CONNECTOR] Getting the last orkls since the last run...")

        self.converter.perform_sync_from_year(work_id)

    def sleep_until_next_interval(self):
        """
        Generate a function comment for the given function body in a markdown code block with the correct language syntax.
        """
        if self.helper.connect_run_and_terminate:
            self.helper.log_info("Connector stop")
            self.helper.metric.state("stopped")
            self.helper.force_ping()
            sys.exit(0)
        
        # Sleep during debugging    
        print("going to sleep for 300 seconds")
        time.sleep(300)
        print("woke up from sleep, waiting for next run...")
        
        self.helper.metric.state("idle")
        time.sleep(self.get_interval())
    
    def run_task(self, last_run):
        """
        Run the task of syncing data from orkl to opencti.

        Args:
            last_run (datetime): The datetime of the last run of connector.

        Returns:
            None
        """
        now = datetime.now()
        current_time = int(datetime.timestamp(now))
        # Initiate work_id to track the job
        work_id = self._initiate_work(current_time)
        self._maintain_data(now, last_run, work_id)
        self.update_connector_state(current_time, work_id)
        self.sleep_until_next_interval()

    def handle_sync(self) -> None:
        try:
            """
            Get the current state and check if connector already runs
            """
            now = datetime.now()
            current_time = int(datetime.timestamp(now))
            current_state = self.helper.get_state()
            if current_state is not None:
                if "last_run" in current_state:
                    # previous run was okay, continue
                    last_run = current_state["last_run"]
                    if(self.config.maintain_data and (current_time - last_run) >= int(self.config.interval)):
                        self.run_task(last_run)
                    else:
                        new_interval = self.config.interval - (current_time - last_run)
                        new_interval_in_hours = round(new_interval / 60 / 60, 2)
                        self.helper.log_info(
                            "[CONNECTOR] Connector will not run, next run in: "
                            + str(new_interval_in_hours)
                            + " hours"
                        )
                        time.sleep(new_interval)
                else:
                    # something went wrong in previous run, continue
                    last_run = None
                    self.run_task(last_run)
            else:
                # running the connector for first time
                last_run = None
                msg = "[CONNECTOR] Connector has never run..."
                self.helper.log_info(msg)
                self.initialize_version_sync_done()
                self.run_task(last_run)
        
        except (KeyboardInterrupt, SystemExit):
            msg = "[CONNECTOR] Connector stop..."
            self.helper.log_info(msg)
            sys.exit(0)
        except Exception as e:
            error_msg = f"[CONNECTOR] Error while processing data: {str(e)}"
            self.helper.log_error(error_msg)

    def initialize_version_sync_done(self) -> None:
        """
        Initialize the version sync status with entry id as 0 as the connector never run or running for the first time.
        """
        file_path: str = os.path.dirname(os.path.abspath(__file__)) + "/../../src/services/converter/sync_details.json"
        #file_path: str = "/opt/opencti-connector-orkl"+"/services/converter/sync_details.json"
        print("Checking if path exists")
        try:
            with open(file_path, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data["version_sync_done"] = 0  # Update the value if needed
                f.seek(0)  # Move the file pointer to the beginning
                json.dump(data, f)  # Write the updated data
                f.truncate()  # Truncate any remaining data after the update
        except FileNotFoundError:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"version_sync_done": 0}, f)
