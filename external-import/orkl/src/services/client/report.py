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
