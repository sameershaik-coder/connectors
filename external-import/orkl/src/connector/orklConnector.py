import sys
import time
from datetime import datetime, timedelta

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
            self.process_data()
            self.helper.force_ping()
        else:
            while True:
                self.process_data()

    def _initiate_work(self, timestamp: int) -> str:
        """
        Initialize a work
        :param timestamp: Timestamp in integer
        :return: Work id in string
        """
        now = datetime.utcfromtimestamp(timestamp)
        friendly_name = f"{self.helper.connect_name} run @ " + now.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        work_id = self.helper.api.work.initiate_work(
            self.helper.connect_id, friendly_name
        )

        info_msg = f"[CONNECTOR] New work '{work_id}' initiated..."
        self.helper.log_info(info_msg)

        return work_id

    def update_connector_state(self, current_time: int, work_id: str) -> None:
        """
        Update the connector state
        :param current_time: Time in int
        :param work_id: Work id in string
        """
        msg = (
            f"[CONNECTOR] Connector successfully run, storing last_run as "
            f"{datetime.utcfromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')}"
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

    
    def get_interval(self):
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
        now = datetime.now()
        current_time = int(datetime.timestamp(now))
        # Initiate work_id to track the job
        work_id = self._initiate_work(current_time)
        self._maintain_data(now, last_run, work_id)
        self.update_connector_state(current_time, work_id)
        self.sleep_until_next_interval()

    def process_data(self) -> None:
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

    def initialize_version_sync_done(self):
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(curr_dir)
        path = Path(parent_dir)
        FILE_DIR = path.parent.absolute()
        file_path = str(FILE_DIR)+"/src/services/converter/sync_details.json"
        result = {"version_sync_done": 0}
        write_json_to_file(file_path,result)