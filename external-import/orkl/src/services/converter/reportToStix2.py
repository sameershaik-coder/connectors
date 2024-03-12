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
        root_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = "sync_details.json"
        file_path = os.path.join(root_dir, file_path)
        return get_json_object_from_file(file_path,"version_sync_done")
    
    def get_latest_orkl_version(self):
        return int(self.client_api.get_latest_library_version()["data"]["ID"])
    
    
    def get_entries_from_year(self, from_year) -> list:
        limit = 100
        offset = 0
        entries_data = []

        while True:
            data = self.client_api.get_library_work_items(limit, offset)
            
            if data is None:
                break

            all_entries = data["data"]["entries"]
            filtered_entries = [entry for entry in all_entries if self.is_entry_from_year(entry, from_year)]
            
            entries_data += filtered_entries
            offset += limit
            
            if len(filtered_entries) == 0:
                break

        return entries_data

    def is_entry_from_year(self, entry, from_year) -> bool:
        entry_year = datetime.strptime(entry['CreatedAt'], '%Y-%m-%dT%H:%M:%S.%fZ').year
        return entry_year >= from_year
    
    def get_entries_from_version_id(self, from_version_id) -> list:
        limit = 100
        offset = 0
        entries_data = []

        while True:
            data = self.client_api.get_library_work_items(limit, offset)
            
            if data is None:
                break

            all_entries = data["data"]["entries"]
            id_exists = self.check_version_id_exists(from_version_id, all_entries)
            
            if id_exists:
                filtered_entries = [entry for entry in all_entries if entry.get('ID') > from_version_id]
                entries_data += filtered_entries
                break
            else:
                entries_data += all_entries
                offset += limit

        return entries_data
    
    def check_version_id_exists(self,id, entries) -> bool:
        return [entry for entry in entries if entry.get('ID') == id]
    
    def get_reports_data_from_entries(self, entries) -> list:
        result = []
        for entry in entries:
            reports = entry.get("created_library_entries")
            if reports:
                result+=self.get_reports_data(reports)
        return result        
                
    def get_reports_data(self, reports) -> list:
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
        if reports:
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
                    # Process and store data in chunks of 100
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
        if count>int(self.config.max_entries_to_process):
            return True
        else:
            return False
    
    def update_version_sync_done(self, version):
        root_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = "sync_details.json"
        file_path = os.path.join(root_dir, file_path)
        result = {"version_sync_done": int(version)}
        write_json_to_file(file_path,result)
        
    def is_invalid_date(self,date_string):
        try:
            # check if there is z in string
            if "Z" in date_string:
                date_string = date_string[:-1]
            # Convert the string to a datetime object
            date_object = datetime.fromisoformat(date_string)
            # Define the range of invalid dates
            invalid_date_range_start = datetime(1900, 1, 1, 0, 0, 0)
            invalid_date_range_end = datetime(9999, 12, 31, 23, 59, 59)
            # Check if the date falls within the invalid range
            if invalid_date_range_start <= date_object <= invalid_date_range_end:
                return True
            else:
                return False
        except ValueError:
            # Handle the case where the string is not a valid ISO format
            return True
    
    def check_date_is_in_franctional_format(self, date_str):
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
        format_completed=False
        result = self.check_date_is_in_franctional_format(date_str)
        if result is None:
            result = self.check_valid_format_timezone(date_str)
            if result is not None:
                format_completed = True
        else:
            format_completed=True
        return result
            
        
        # invalid_date = self.is_invalid_date(date_str)
        # if invalid_date:
        #     return None
        # else:
        #     try:
        #         parsed_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        #     except ValueError:
        #         parsed_date = self.check_valid_format_timezone(date_str)
        #         if parsed_date is None:
        #             # If parsing fails, log and return None
        #             self.log_invalid_date(date_str)
        #             return None
        #     return parsed_date
    
    def check_valid_format_timezone(self, date_str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            # If parsing fails, log and return None
            self.log_invalid_date(date_str)
            return None

    def log_invalid_date(self, date_str):
        info_msg = (
            f"[CONVERTER] Invalid date format detected in {date_str} from orkl api. "
            f"Replacing with None."
        )
        self.helper.log_info(info_msg)
        

    def resolve_source_names(self, source_name):
        shortname = source_name
        if ":" in source_name:
            shortname = source_name.split(":")[0]
        return shortname
    
    def check_if_source_exists(self, name:str):
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
        trimmed_list = object

        result = []

        external_references = []

        report = trimmed_list

        id = report["id"]
        created_at = report["created_at"]
        created_at = self.check_and_handle_date_formats(created_at)
        updated_at = report["updated_at"]
        deleted_at = report["deleted_at"]
        sha1_hash = report["sha1_hash"]
        title = report["title"]
        authors = report["authors"]
        file_creation_date = report["file_creation_date"]
        file_creation_date=self.check_and_handle_date_formats(file_creation_date)
        file_modification_date = report["file_modification_date"]
        file_modification_date=self.check_and_handle_date_formats(file_modification_date)
        file_size = report["file_size"]
        plain_text = report["plain_text"]
        language = report["language"]
        sources = report["sources"]
        references = report["references"]
        report_names = report["report_names"]
        threat_actors = report["threat_actors"]

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

        

        if created_at is None:
            if file_creation_date is None:
                created_at = datetime.now()
            else:
                created_at = file_creation_date

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
            existing_threat_actors=[]
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
                #existing_threat_actor = self.check_if_threat_actor_exists(threat_actor["main_name"])
                threat_actor_id = None
                # if(existing_threat_actor is None):
                #     # create threat actor object
                #     threat_actor_obj = stix2.ThreatActor(
                #         id=ThreatActorIndividual.generate_id(threat_actor["main_name"]),
                #         name=threat_actor["main_name"],
                #         description=threat_actor_obj_description,
                #         created=threat_actor["created_at"],
                #         modified=threat_actor["updated_at"],
                #         labels="orkl-threat-actor",
                #         created_by_ref=threat_actor_source_id,
                #         custom_properties={
                #             "x_opencti_description": threat_actor_obj_description,
                #             "x_opencti_score": 50
                #         },
                #         allow_custom=True,
                #     )
                #     threat_actor_objects.append(threat_actor_obj)
                #     threat_actor_id = threat_actor_obj.id
                # else:
                #     threat_actor_id = existing_threat_actor["standard_id"]
                #     existing_threat_actors.append(existing_threat_actor)
                
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
                    # for tool in existing_tools_objects:
                    #     relationship = self._create_relationship(threat_actor_id, tool["standard_id"], "uses")
                    #     threat_actor_relationship_objects.append(relationship)
                
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
                allow_custom=True,
            )
                report_source_objects.append(source_object)
            
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
        
        # for existing_ta in existing_threat_actors:
        #     report_object_references.append(existing_ta)
                    
        # Check if the length of report_object_references is 0
        if len(report_object_references) == 0:
            # append report source as reference for the report
            report_object_references.append(report_source)
            
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
            created_by_ref = source_object.id,
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
