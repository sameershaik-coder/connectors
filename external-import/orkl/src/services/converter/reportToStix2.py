import datetime
import time
import stix2
from pycti import Identity,StixCoreRelationship, Report, CustomObservableText,ThreatActor,ThreatActorIndividual,Tool  # type: ignore
from services.utils import APP_VERSION, ConfigOrkl  # type: ignore
from datetime import datetime
from ..client import ReportClient as ReportClient  # type: ignore
import os, json
from services.utils import get_json_object_from_file,write_json_to_file
import jsonpickle

class OrklConverter:
    def __init__(self, helper):
        self.config = ConfigOrkl()
        self.helper = helper
        self.client_api = ReportClient(
            helper=self.helper,
            header=f"OpenCTI-orkl/{APP_VERSION}",
        )

        self.author = self._create_author()
    
    def get_version_sync_done(self):
        """
        A function that retrieves the version sync done entryid from previous run from a JSON file.
        """
        root_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = "sync_details.json"
        file_path = os.path.join(root_dir, file_path)
        return get_json_object_from_file(file_path,"version_sync_done")
    
    def get_latest_orkl_version(self):
        """
        This function retrieves the latest version of the ORKL library by querying the client API. 
        It then extracts and returns the ID of the latest version as an integer.
        """
        return int(self.client_api.get_latest_library_version()["data"]["ID"])
    
    
    def get_entries_from_year(self, from_year) -> list:
        """
        Get entries from a specific year and return them as a list.
        
        Parameters:
            from_year (int): The year from which to retrieve the entries.
        
        Returns:
            list: A list of entries from the specified year.
        """
        limit = 100
        offset = 0
        entries_data = []

        while True:
            # get library entries from orkl based on limit and offset
            data = self.client_api.get_library_work_items(limit, offset)
            
            # if no data is returned, it means that no more entries are available which require sync
            if data is None:
                break
            
            all_entries = data["data"]["entries"]
            # check if there are entries which are created from the year in config
            filtered_entries = [entry for entry in all_entries if self.is_entry_from_year(entry, from_year)]
            # add the filtered entries to the list
            entries_data += filtered_entries
            # update the offset
            offset += limit
            
            # if there are entries that are not from the year in config, break
            if len(filtered_entries) == 0:
                break

        return entries_data

    def is_entry_from_year(self, entry, from_year) -> bool:
        """
        Check if the entry is from a created from year in config.

        Parameters:
            entry (dict): The entry to check.
            from_year (int): The year to compare against.

        Returns:
            bool: True if the entry is from the specified year, False otherwise.
        """
        entry_year = datetime.strptime(entry['CreatedAt'], '%Y-%m-%dT%H:%M:%S.%fZ').year
        return entry_year >= from_year
    
    def get_entries_from_version_id(self, from_version_id) -> list:
        """
        Retrieves entries from a specific version ID and returns a list of entries.

        Parameters:
            from_version_id (int): The ID from which to start retrieving entries.

        Returns:
            list: A list of entries starting from the specified version ID.
        """
        limit = 100
        offset = 0
        entries_data = []

        while True:
            # get library entries from orkl based on limit and offset
            data = self.client_api.get_library_work_items(limit, offset)
            
            # if no data is returned, it means that no more entries are available which require sync
            if data is None:
                break

            all_entries = data["data"]["entries"]
            # check if there are entries whose entry id is greater than from_version_id
            id_exists = self.check_version_id_exists(from_version_id, all_entries)
            
            # if there are entries whose entry id is greater than from_version_id, add them to the list entries_data
            if id_exists:
                filtered_entries = [entry for entry in all_entries if entry.get('ID') > from_version_id]
                entries_data += filtered_entries
                break
            # if there are no entries whose entry id is greater than from_version_id, then update the offset and repeat the loop
            else:
                entries_data += all_entries
                offset += limit

        return entries_data
    
    def check_version_id_exists(self,id, entries) -> bool:
        """
        Check if the given ID exists in the list of entries and return True if it does, otherwise return False.
        
        :param id: The ID to check for existence in the entries list
        :param entries: The list of entries to search for the given ID
        :return: bool indicating whether the ID exists in the entries list
        """
        return [entry for entry in entries if entry.get('ID') == id]
    
    def get_reports_data_from_entries(self, entries) -> list:
        """
        A function that retrieves reports data from a list of entries.

        Parameters:
            entries (list): A list of entries to extract reports data from.

        Returns:
            list: A list containing the reports data extracted from the entries.
        """
        result = []
        for entry in entries:
            reports = entry.get("created_library_entries")
            if reports:
                result+=self.get_reports_data(reports)
        return result        
                
    def get_reports_data(self, reports) -> list:
        """
        Retrieve data from reports using their IDs and return a list of report data.
        
        Parameters:
            self: The object instance.
            reports: A list of report IDs.
        
        Returns:
            list: A list containing the data of each report.
        """
        result = []
        for report in reports:
            report_data = self.client_api.get_entry_by_id(report)["data"]
            result.append(report_data)
        return result
    
    def perform_sync_from_year(self, work_id) -> list:
        """
        Retrieve all reports from orkl to convert into STIX2 format
        :param orkl_params: Dict of params
        :return: List of data converted into STIX2
        """
        results=[]
        config = ConfigOrkl()
        SYNC_FROM_YEAR = int(config.history_start_year)
        version_sync_done = self.get_version_sync_done()  
        if version_sync_done <= 0:
            # running the connector for first time so get entries by the year
            all_entries = self.get_entries_from_year(SYNC_FROM_YEAR)
        elif version_sync_done > 0:
            # get all entries from where connector has left off from prevoius run
            all_entries = self.get_entries_from_version_id(version_sync_done)
            if len(all_entries)==0:
                # check if sync is up to date with orkl api
                msg = f"[CONVERTER] Data is already up to date. Latest entry id is {version_sync_done} and data sync done entry id is {version_sync_done}"
                self.helper.log_info(msg)
                return results
        
        sorted_entries = sorted(all_entries, key=lambda x: x["ID"])
        entries_processed_count=0
        for entry in sorted_entries:
            if(self.check_entries_processed_limit_reached(entries_processed_count)):
                info_msg = (
                                    f"[CONVERTER] maximum processed entries limit reached for current run. Process rest of entries in next run..."
                                )
                self.helper.log_info(info_msg)
                break
            else:
                # print(f"uncomment below code, perform entry sending..{entry['ID']} and {work_id}")
                # self.update_version_sync_done(entry['ID'])
                # entries_processed_count+=1 # remove above lines later only for debugging
                
                extract_complete=self.extract_reports_send_bundle(entry,work_id)
                if extract_complete==True:
                    entry_id=entry["ID"]
                    self.update_version_sync_done(entry_id)
                    entries_processed_count+=1
                    info_msg = (
                                    f"[CONVERTER] Completed extracting and sending reports to OCTI for {entry_id}"
                                )
                    self.helper.log_info(info_msg)        
        return results

    def extract_reports_send_bundle(self,entry,work_id):
        result=False
        current_entry_reports=[]
        reports = entry.get("created_library_entries")
        entry_id=entry["ID"]
        # check if there are any reports to process
        if reports:
            # get all orkl reports data in current_entry_reports
            current_entry_reports+=self.get_reports_data(reports)
            if current_entry_reports is not None:
                if(len(current_entry_reports) == 0):
                    # log message to OCTI when no reports found for entry id
                    info_msg = (
                        f"[CONVERTER] No reports were found for the entry with entry id : {entry_id}"
                        f"moving to next entry"
                    )
                    self.helper.log_info(info_msg)
                else:
                    # process each orkl report data, convert to stix and send to OCTI
                    for i in range(0, len(current_entry_reports), 1):
                        processed_object = self.process_object(current_entry_reports[i])
                        if len(processed_object) != 0:
                            reports_bundle = self._to_stix_bundle(processed_object)
                            reports_to_json = self._to_json_bundle(reports_bundle)

                            # Retrieve the author object for the info message
                            info_msg = (
                                f"[CONVERTER] "
                                f"Sending bundle to server with {len(reports_bundle)} objects, "
                                f"concerning {len(processed_object) - 1} reports"
                            )
                            self.helper.log_info(info_msg)

                            self.helper.send_stix2_bundle(
                                reports_to_json,
                                update=self.config.update_existing_data,
                                work_id=work_id,
                            )
                            print(f"[CONVERTER] Completed extracting reports from {entry_id}")
                            #time.sleep(10)
                    result=True
            else:
                raise Exception(
                    f"[CONVERTER] Attempting to extract reports from entry failed. " "Wait for connector to re-run..."
                )
        else:
        # log message to OCTI when no reports found for entry id
            info_msg = (
                f"[CONVERTER] No reports were found for the entry with entry id : {entry_id} "
                f"moving to next entry"
            )
            self.helper.log_info(info_msg)
        return result
        
    def check_entries_processed_limit_reached(self,count:int):
        """
        Check if the count exceeds the maximum entries to process and return True or False accordingly.
        
        Parameters:
            count (int): The count to be checked against the maximum entries to process.
        
        Returns:
            bool: True if the count exceeds the maximum entries to process, False otherwise.
        """
        if count>int(self.config.max_entries_to_process):
            return True
        else:
            return False
    
    def update_version_sync_done(self, version):
        """
        Updates the version sync status orkl library entry id in the sync_details.json file.

        :param version: int - The version to mark as synced.
        :return: None
        """
        root_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = "sync_details.json"
        file_path = os.path.join(root_dir, file_path)
        result = {"version_sync_done": int(version)}
        write_json_to_file(file_path,result)
        
    # def is_invalid_date(self,date_string):
    #     try:
    #         # check if there is z in string
    #         if "Z" in date_string:
    #             date_string = date_string[:-1]
    #         # Convert the string to a datetime object
    #         date_object = datetime.fromisoformat(date_string)
    #         # Define the range of invalid dates
    #         invalid_date_range_start = datetime(1900, 1, 1, 0, 0, 0)
    #         invalid_date_range_end = datetime(9999, 12, 31, 23, 59, 59)
    #         # Check if the date falls within the invalid range
    #         if invalid_date_range_start <= date_object <= invalid_date_range_end:
    #             return True
    #         else:
    #             return False
    #     except ValueError:
    #         # Handle the case where the string is not a valid ISO format
    #         return True
    
    def check_date_is_in_franctional_format(self, date_str):
        """
        A function to check if the given date string is in fractional format and return the corresponding datetime object.
        
        Parameters:
        - date_str (str): A string representing a date, potentially in fractional format.
        
        Returns:
        - datetime object: The datetime object corresponding to the input date string, or None if the date format is invalid.
        """
        result = None
        try:
            if "Z" in date_str:
                date_str = date_str[:-1]
            # Convert the string to a datetime object
            date_object = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f')
            # Extract the date part
            result = date_object
            print("Converted date:", result)
        except ValueError:
            print("Invalid date format")
        return result
    
    def check_and_handle_date_formats(self, date_str):
        """
        Check and handle date formats.

        Parameters:
            date_str (str): The date string to be checked and handled

        Returns:
            result: The result of checking and handling the date formats
        """
        result = self.check_date_is_in_franctional_format(date_str)
        if result is None:
            result = self.check_valid_format_timezone(date_str)
        return result
        
    
    def check_valid_format_timezone(self, date_str):
        """
        Check if the input date string is in a valid format for a timezone. If valid, return the converted datetime object. If not valid, log the invalid date and return None.
        
        Parameters:
        - date_str (str): A string representing a date in the format "%Y-%m-%dT%H:%M:%SZ"
        
        Returns:
        - datetime object if the date_str is in a valid format, None otherwise
        """
        try:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            # If parsing fails, log and return None
            self.log_invalid_date(date_str)
            return None

    def log_invalid_date(self, date_str):
        """
        Logs an invalid date format detected in the given date string from the orkl api and replaces it with None.
        
        :param date_str: The date string with invalid format
        :return: None
        """
        info_msg = (
            f"[CONVERTER] Invalid date format detected in {date_str} from orkl api. "
            f"Replacing with None."
        )
        self.helper.log_info(info_msg)
        

    def resolve_source_names(self, source_name):
        """
        Resolve the source names based on the input source name and check if it is valid source name

        :param source_name: str, the name of the source
        :return: str, the resolved shortname of the source
        """
        shortname = source_name
        if ":" in source_name:
            shortname = source_name.split(":")[0]
        return shortname
    
    def check_if_source_exists(self, name:str):
        """
        Check if a source with the given name exists in the opencti system.

        Parameters:
            name (str): The name of the source to check.

        Returns:
            object: The existing identity object if found, otherwise None.
        """
        identity_obj = None
        identities = self.helper.api.stix_domain_object.list(
                                            types=["Identity"],
                                            filters={
                                                "mode": "and",
                                                "filters": [{"key": "name", "values": [name]}],
                                                "filterGroups": [],
                                            },
                                        )
        if len(identities) > 0:
            print(f"Identity {name} already exists in the opencti")
            identity_obj = identities[0]
        return identity_obj
    
    def check_if_threat_actor_exists(self, name:str):
        """
        Check if a threat actor with the given name exists in the system.

        Args:
            name (str): The name of the threat actor to check.

        Returns:
            object: The threat actor object if it exists, otherwise None.
        """
        ta_obj = None
        ta_objs = self.helper.api.stix_domain_object.list(
                                            types=["ThreatActorGroup","ThreatActorIndividual","ThreatActor"],
                                            filters={
                                                "mode": "and",
                                                "filters": [{"key": "name", "values": [name]}],
                                                "filterGroups": [],
                                            },
                                        )
        if len(ta_objs) > 0:
            # check if return obj is a valid type of threat actor
            id = ta_objs[0].get("standard_id")
            if(id is not None):
                if("threat-actor" in id):
                    print(f"ThreatActor {name} already exists in the opencti")
                    ta_obj = ta_objs[0]
                else:
                    ta_obj = None        
        return ta_obj
    
    def process_object(self, object: dict) -> list:
        """
        A function that processes an object and returns a list of results. 
        The function performs various operations on the input object, 
        such as creating external references, threat actor objects, report source objects, and report objects. 
        It also handles date formats and checks for existing tools and identities.
        The function returns a list of results.
        """
        trimmed_list = object

        result = []

        external_references = []

        report = trimmed_list

        id = report["id"]
        created_at = self.check_and_handle_date_formats(report.get("created_at", ""))
        updated_at = report["updated_at"]
        deleted_at = report["deleted_at"]
        sha1_hash = report["sha1_hash"]
        title = report["title"]
        authors = report["authors"]
        file_creation_date = self.check_and_handle_date_formats(report.get("file_creation_date", ""))
        file_modification_date = self.check_and_handle_date_formats(report.get("file_modification_date", ""))
        file_size = report["file_size"]
        plain_text = report["plain_text"]
        language = report["language"]
        sources = report["sources"]
        references = report["references"]
        report_names = report["report_names"]
        threat_actors = report["threat_actors"]
        
        # check if the date is invalid from orkl
        if(created_at == datetime(1, 1, 1) or file_creation_date == datetime(1, 1, 1) or file_modification_date == datetime(1, 1, 1)):
            # if we have a valid date then use it, else use current date
            if created_at is not None:
                file_creation_date = created_at
                file_modification_date = created_at
            else:
                created_at = datetime.now()
                file_creation_date = datetime.now()
                file_modification_date = datetime.now()

        info = [
            "Additional details about report :",
            f"orkl id: {id if (id is not None and id != '') else 'N/A'}",
            f"report created date : {created_at if (created_at is not None and created_at != '') else 'N/A'}",
            f"report updated date : {updated_at if (updated_at is not None and updated_at != '') else 'N/A'}",
            f"report deleted date : {deleted_at if (deleted_at is not None and deleted_at != '') else 'N/A'}",
            f"report sha1_hash : {sha1_hash if (sha1_hash is not None and sha1_hash != '') else 'N/A'}",
            f"report title : {title if (title is not None and title != '') else 'N/A'}",
            f"report authors : {authors if (authors is not None and authors != '') else 'N/A'}",
            f"report file_size : {file_size if (file_size is not None and file_size != '') else 'N/A'}",
            f"report language : {language if (language is not None and language != '') else 'N/A'}"
        ]
        report_info = '\n\n'.join(info)

        event_markings = []

        report_name = report_names[0].split(".")[0]

        external_references=[]
        threat_actor_objects = []
        threat_actor_relationship_objects = []
        threat_actor_source_objects = []
        threat_actors_tools_objects=[]
        all_tools_ids=[]
        all_tools_names=[]
        if len(threat_actors) > 0:
            for threat_actor in threat_actors:
                # create threat actor tools objects
                tools = threat_actor["tools"]
                if tools:
                    for tool in tools:
                        if tool not in all_tools_names:
                            existing_tools_objects=[]
                            # check if tool exists
                            existing_tools = self.helper.api.stix_domain_object.list(
                                                types=["Tools"],
                                                filters={
                                                    "mode": "and",
                                                    "filters": [{"key": "name", "values": [tool]}],
                                                    "filterGroups": [],
                                                },
                                            )
                            if len(existing_tools) > 0:
                                print(f"Tool {tool} already exists in the opencti")
                                tool_obj = existing_tools[0]
                                existing_tools_objects.append(tool_obj)
                                if(tool_obj["standard_id"] not in all_tools_ids):
                                    all_tools_ids.append(tool_obj["standard_id"])
                            else:
                                # Create tool object
                                tool_obj = stix2.Tool(
                                    id=Tool.generate_id(tool),
                                    name=tool,
                                    labels="orkl-threat-actor-tool",
                                    allow_custom=True,
                                )
                                all_tools_ids.append(tool_obj.id)
                                threat_actors_tools_objects.append(tool_obj)
                            all_tools_names.append(tool)

                threat_actor_aliases = threat_actor["aliases"]
                threat_actor_obj_description = "Also known as [aliases] : " + str(threat_actor_aliases) + "\n"

                # create threat actor source object
                
                threat_actor_source_name = self.resolve_source_names(threat_actor["source_name"])
                threat_actor_source_id = None
                threat_actor_source = self.check_if_source_exists(threat_actor_source_name)
                if(threat_actor_source is None):
                    threat_actor_source = stix2.Identity(
                                        id=Identity.generate_id(threat_actor_source_name, "organization"),
                                        name=threat_actor_source_name,
                                        created_by_ref=self.author.id,
                                    )
                    threat_actor_source_objects.append(threat_actor_source)
                    threat_actor_source_id = threat_actor_source.id
                else:
                    threat_actor_source_id = threat_actor_source["standard_id"]
                
                # process threat actors    
                threat_actor_id = None
               
                
                # create threat actor object
                threat_actor_obj = stix2.ThreatActor(
                    id=ThreatActorIndividual.generate_id(threat_actor["main_name"]),
                    name=threat_actor["main_name"],
                    description=threat_actor_obj_description,
                    created=threat_actor["created_at"],
                    modified=threat_actor["updated_at"],
                    labels="orkl-threat-actor",
                    created_by_ref=threat_actor_source_id,
                    custom_properties={
                        "x_opencti_description": threat_actor_obj_description,
                        "x_opencti_score": 50
                    },
                    allow_custom=True,
                )
                threat_actor_objects.append(threat_actor_obj)
                threat_actor_id = threat_actor_obj.id
                    

                # create relationship between threat actor and tools
                if tools:
                    for tool in threat_actors_tools_objects:
                        relationship = self._create_relationship(threat_actor_id, tool.id, "uses")
                        threat_actor_relationship_objects.append(relationship)
                
        if "files" in report:
            report_source_name = self.resolve_source_names(sources[0]["name"])
            files=report["files"]
            if "pdf" in files:
                external_reference = stix2.ExternalReference(
                    source_name=report_source_name+" Report PDF",  url=files["pdf"]
                )
                external_references.append(external_reference)
            if "text" in files:
                external_reference = stix2.ExternalReference(
                    source_name=report_source_name+" Report TEXT",  url=files["text"]
                )
                external_references.append(external_reference)
            if "img" in files:
                external_reference = stix2.ExternalReference(
                    source_name=report_source_name+" Report IMAGE",  url=files["img"]
                )
                external_references.append(external_reference)

        if len(references) > 0:

            external_reference = stix2.ExternalReference(
                source_name=report_source_name + " Report source",  url=references[0]
            )
            external_references.append(external_reference)

        report_source_objects=[]
        if len(sources) > 0:
            # check if an identity already exits in OCTI
            existing_source_octi_object = self.check_if_source_exists(sources[0]["name"])
            # create a stix identity object if it doesn't exist
            if(existing_source_octi_object is None):
                custom_properties = {
                        "x_opencti_description": sources[0]["description"],
                        "x_opencti_score": 50,
                        "labels": ["orkl-report-source"],
                        "created_by_ref": self.author.id,
                        "external_references": [],
                    }

                if sources[0]["name"] != None:
                    report_source_name = self.resolve_source_names(sources[0]["name"])
                    source_object = stix2.Identity(
                    id=Identity.generate_id(report_source_name, "organization"),
                    name=report_source_name,
                    description=sources[0]["description"],
                    created_by_ref=self.author.id,
                    custom_properties=custom_properties,
                    allow_custom=True)
                    report_source_objects.append(source_object)
                    report_source_id=source_object.id
            else:
                report_source_id=existing_source_octi_object["standard_id"]
            
        # create report object
        report_object_references = []
        all_elements = (
            threat_actors_tools_objects
            + threat_actor_objects
        )

        for element in all_elements:
            report_object_references.append(element)
            result.append(element) 

        
        for relationship in threat_actor_relationship_objects:
            report_object_references.append(relationship)
            result.append(relationship)
        
        
        for threat_actor_source in threat_actor_source_objects:
            result.append(threat_actor_source)
        
        for report_source in report_source_objects:
            result.append(report_source)
                    
        # Check if the length of report_object_references is 0
        # sometimes this happens when there are no tools and threat actors so we need to handle that
        # This means report does not have any references or has only existing OCTI references
        # This case needs to be handled so that report_object_references is not empty
        if len(report_object_references) == 0:
            # First check if we can add report source objects
            if len(report_source_objects) > 0:
                report_source = report_source_objects[0]
                report_object_references.append(report_source)
            else:
                # if report source object doesn't exist, probably because it was already existing in OCTI create a new one
                custom_properties = {
                        "x_opencti_description": sources[0]["description"],
                        "x_opencti_score": 50,
                        "labels": ["orkl-report-source"],
                        "created_by_ref": self.author.id,
                        "external_references": [],
                    }
                if sources[0]["name"] != None:
                    report_source_name = self.resolve_source_names(sources[0]["name"])
                    source_object = stix2.Identity(
                    id=Identity.generate_id(report_source_name, "organization"),
                    name=report_source_name,
                    description=sources[0]["description"],
                    created_by_ref=self.author.id,
                    custom_properties=custom_properties,
                    allow_custom=True)
                    report_object_references.append(source_object)
            
        report_description = report_info + "\n\n"
        report_description += "Report Content Text :" + "\n\n"   
        report_description += plain_text    
        
        report = stix2.Report(
            id=Report.generate_id(report_name,created_at),
            name=report_name,
            description=report_description,
            published=created_at,
            created=file_creation_date,
            modified=file_modification_date,
            created_by_ref = report_source_id,
            report_types=["orkl-report"],
            object_marking_refs=event_markings,
            object_refs=report_object_references,
            external_references=external_references,
            labels="orkl-threat-report",
            custom_properties={
                "x_opencti_report_status": 2,
                "x_opencti_files": [],
            },
            allow_custom=True,
            )

        result.append(report)

        return result

    def _create_relationship(self, from_id: str, to_id: str, relation):
        """
        :param from_id: From id in string
        :param to_id: To id in string
        :param relation:
        :return: Relationship STIX object
        """
        return stix2.Relationship(
            id=StixCoreRelationship.generate_id(relation, from_id, to_id),
            relationship_type=relation,
            source_ref=from_id,
            target_ref=to_id,
            created_by_ref=self.author.id,
        )

    @staticmethod
    def _create_author():
        """
        :return: ORKL as default author
        """
        return stix2.Identity(
            id=Identity.generate_id("ORKL", "organization"),
            name="ORKL",
            identity_class="organization",
        )

    @staticmethod
    def _to_stix_bundle(stix_objects):
        """
        :return: STIX objects as a Bundle
        """
        return stix2.Bundle(objects=stix_objects, allow_custom=True)

    @staticmethod
    def _to_json_bundle(stix_bundle):
        """
        :return: STIX bundle as JSON format
        """
        return stix_bundle.serialize()
