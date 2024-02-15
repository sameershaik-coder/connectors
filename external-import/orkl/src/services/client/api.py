import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .endpoints import BASE_URL


class CPEClient:
    """
    Working with CPE API
    """

    def __init__(self, api_key, helper, header):
        """
        Initialize CPE API with necessary configurations
        :param api_key: API key in string
        :param helper: OCTI helper
        :param header:
        """
        headers = {"Bearer": api_key, "User-Agent": header}
        #self.token = api_key
        self.helper = helper
        self.session = requests.Session()
        self.session.headers.update(headers)

    @staticmethod
    def _request_data(self, api_url: str, params=None):
        """
        Internal method to handle API requests
        :return: Response in JSON format
        """
        try:
            response = self.request(api_url, params)

            info_msg = f"[API] HTTP Get Request to endpoint for path ({api_url})"
            self.helper.log_info(info_msg)

            response.raise_for_status()
            return response

        except requests.RequestException as err:
            error_msg = f"[API] Error while fetching data from {api_url}: {str(err)}"
            self.helper.log_error(error_msg)
            return None

    def request(self, api_url, params):
        # Define the retry strategy
        retry_strategy = Retry(
            total=4,  # Maximum number of retries
            backoff_factor=6,  # Exponential backoff factor (e.g., 2 means 1, 2, 4, 8 seconds, ...)
            status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry on
        )
        # Create an HTTP adapter with the retry strategy and mount it to session
        adapter = HTTPAdapter(max_retries=retry_strategy)

        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        response = self.session.get(api_url, params=params)

        if response.status_code == 200:
            # It is recommended that users "sleep" their scripts for six seconds between requests (NIST)
            time.sleep(6)
            return response
        else:
            raise Exception(
                "[API] Attempting to retrieve data failed. Wait for connector to re-run..."
            )
    
    def get_orkl_latest_version(self):
        response = self._request_data(self, BASE_URL+"/version")
        cpe_collection = response.json()
        return cpe_collection
    
    def get_report_by_id(self, id):
        response = self._request_data(self, BASE_URL+'/entry/'+id)
        cpe_collection = response.json()
        return cpe_collection
    
    def get_some_orkl_collection(self,limit,offset, cpe_params=None):
        """
        If params is None, retrieve all CPEs in National Vulnerability Database
        :param cpe_params: Params to filter what list to return
        :return: A list of dicts of the complete collection of CPE from NVD
        """
        try:
            params={
                "limit": limit,
                "offset": offset,
                "order": "desc"
            }
            # params={
            #     "order": "desc"
            # }
            response = self._request_data(self, BASE_URL+'/version/entries', params=params)
            #response = self._request_data(self, BASE_URL, params=cpe_params)
            #print(response.text)
            cpe_collection = response.json()
            return cpe_collection

        except Exception as err:
            self.helper.log_error(err)

    def get_complete_collection(self, cpe_params=None):
        """
        If params is None, retrieve all CPEs in National Vulnerability Database
        :param cpe_params: Params to filter what list to return
        :return: A list of dicts of the complete collection of CPE from NVD
        """
        try:
            response = self._request_data(self, BASE_URL, params=cpe_params)

            cpe_collection = response.json()
            return cpe_collection

        except Exception as err:
            self.helper.log_error(err)
