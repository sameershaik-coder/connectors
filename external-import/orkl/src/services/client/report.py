from .api import ORKLAPIClient
from services.utils.configVariables import ConfigOrkl
import os
from services.utils import get_json_object_from_file

class ReportClient(ORKLAPIClient):
    
    def get_version_sync_done(self):
        root_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = "sync_details.json"
        file_path = os.path.join(root_dir, file_path)
        return get_json_object_from_file(file_path,"version_sync_done")
    
    def get_latest_orkl_version(self):
        return int(self.get_latest_library_version()["data"]["ID"])
    
    def get_entries_from_version_id(self, from_version_id) -> list:
        version_id_found = False
        limit = 100
        offset = 0
        result = []

        while not version_id_found:
            all_entries = self.get_library_work_items(limit, offset)["data"]["entries"]
            version_id_found = self.check_version_id_exists(from_version_id, all_entries)

            if version_id_found:
                filtered_entries = [entry for entry in all_entries if entry.get('ID') > from_version_id]
                result += filtered_entries
            else:
                result += all_entries
                offset += limit

        return result

            
    
    def check_version_id_exists(self,id, entries) -> bool:
        return [entry for entry in entries if entry.get('ID') == id]
    
    def get_all_reports_from_entries(self, entries) -> list:
        all_reports_data = []
        for entry in entries:
            reports = entry.get("created_library_entries")
            if reports:
                all_reports_data.extend(self.get_reports_data_from_api(reports))
        return all_reports_data
        
                
    def get_reports_data_from_api(self, reports) -> list:
        reports_data = []
        for report in reports:
            report_data = self.get_entry_by_id(report)["data"]
            reports_data.append(report_data)
        return reports_data
    
    def get_reports(self) -> list:
        """
        Get and filter Entries from Orkl
        :param entries_params: Dict of params
        :return: A list of dicts of report entries
        """
        reports_collection = None
        config = ConfigOrkl()
        SYNC_FROM_VERSION = int(config.orkl_sync_from_version)
        latest_version = self.get_latest_orkl_version()
        version_sync_done = self.get_version_sync_done()  
        if latest_version >= SYNC_FROM_VERSION:
            if version_sync_done < SYNC_FROM_VERSION:
                all_entries = self.get_entries_from_version_id(version_sync_done)
                print(all_entries)
                reports_collection = self.get_all_reports_from_entries(all_entries)
            else:
                msg = f"Data is already up to date. Latest version is {latest_version} and data sync done version is {SYNC_FROM_VERSION}"
                self.helper.log_info(msg)
        else:
            if SYNC_FROM_VERSION > latest_version:
                raise Exception(f"Version does not exist, check orkl_sync_from_version in config file. Latest version is {latest_version} and sync from version is {SYNC_FROM_VERSION}")
            else:
                if latest_version==SYNC_FROM_VERSION and version_sync_done==SYNC_FROM_VERSION:
                    msg = f"Data is already up to date. Latest version is {latest_version} and data sync done version is {SYNC_FROM_VERSION}"
                    self.helper.log_info(msg)
                else:
                    raise Exception(f"Unable to perform sync from version {SYNC_FROM_VERSION} to latest version {latest_version}. Please check the config file.")        
            
        return reports_collection
