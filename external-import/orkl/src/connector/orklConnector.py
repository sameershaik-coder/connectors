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

    def _import_recent(self, now: datetime, work_id: str) -> None:
        """
        Import the most recent orkls depending on date range chosen
        :param now: Current date in datetime
        :param work_id: Work id in string
        """
        if self.config.max_date_range > MAX_AUTHORIZED:
            error_msg = "The max_date_range cannot exceed {} days".format(
                MAX_AUTHORIZED
            )
            raise Exception(error_msg)

        date_range = timedelta(days=self.config.max_date_range)
        start_date = now - date_range

        orkl_params = self._update_orkl_params(start_date, now)

        self.converter.perform_sync_from_year(work_id)

    def _import_history(
        self, start_date: datetime, end_date: datetime, work_id: str
    ) -> None:
        """
        Import orkls history if pull_history config is True
        :param start_date: Start date in datetime
        :param end_date: End date in datetime
        :param work_id: Work id in string
        """
        years = range(start_date.year, end_date.year + 1)
        start, end = start_date, end_date + timedelta(1)

        for year in years:
            year_start = datetime(year, 1, 1, 0, 0)
            year_end = datetime(year + 1, 1, 1, 0, 0)

            date_range = min(end, year_end) - max(start, year_start)
            days_in_year = date_range.days

            # If the year is the current year, get all days from start year to now
            if year == end_date.year:
                date_range = end_date - year_start
                days_in_year = date_range.days

            start_date_current_year = year_start

            while days_in_year > 0:
                end_date_current_year = start_date_current_year + timedelta(
                    days=MAX_AUTHORIZED
                )
                info_msg = (
                    f"[CONNECTOR] Connector retrieve orkl history for year {year}, "
                    f"{days_in_year} days left"
                )
                self.helper.log_info(info_msg)

                """
                If retrieve history for this year and days_in_year left are less than 120 days
                Retrieve orkls from the rest of days                         
                """
                if year == end_date.year and days_in_year < MAX_AUTHORIZED:
                    end_date_current_year = start_date_current_year + timedelta(
                        days=days_in_year
                    )
                    # Update date range
                    orkl_params = self._update_orkl_params(
                        start_date_current_year, end_date_current_year
                    )

                    self.converter.perform_sync_from_year(work_id)
                    days_in_year = 0

                """
                Retrieving for each year MAX_AUTHORIZED = 120 days
                1 year % 120 days => 5 or 6 (depends if it is a leap year or not)
                """
                if days_in_year > 6:
                    # Update date range
                    orkl_params = self._update_orkl_params(
                        start_date_current_year, end_date_current_year
                    )

                    self.converter.perform_sync_from_year(work_id)
                    start_date_current_year += timedelta(days=MAX_AUTHORIZED)
                    days_in_year -= MAX_AUTHORIZED
                else:
                    end_date_current_year = start_date_current_year + timedelta(
                        days=days_in_year
                    )
                    # Update date range
                    orkl_params = self._update_orkl_params(
                        start_date_current_year, end_date_current_year
                    )
                    self.converter.perform_sync_from_year(work_id)
                    days_in_year = 0

            info_msg = f"[CONNECTOR] Importing orkl history for year {year} finished"
            self.helper.log_info(info_msg)

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

    @staticmethod
    def _update_orkl_params(start_date: datetime, end_date: datetime) -> dict:
        """
        Update orkl params to handle date range
        :param start_date: Start date in datetime
        :param end_date: End date in datetime
        :return: Dict of orkl params
        """
        return {
            "lastModStartDate": start_date.isoformat(),
            "lastModEndDate": end_date.isoformat(),
        }

    def sleep_until_next_interval(self):
        if self.helper.connect_run_and_terminate:
            self.helper.log_info("Connector stop")
            self.helper.metric.state("stopped")
            self.helper.force_ping()
            sys.exit(0)
        # Sleep during debugging    
        print("going to sleep for 1000 seconds")
        time.sleep(1000)
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