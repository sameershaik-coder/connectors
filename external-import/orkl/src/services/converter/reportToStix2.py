import datetime
import time
import stix2
from pycti import Identity,StixCoreRelationship, Report, CustomObservableText,ThreatActor,ThreatActorIndividual,Tool  # type: ignore
from services.utils import APP_VERSION, ConfigOrkl  # type: ignore
from datetime import datetime
from ..client import ReportClient as ReportClient  # type: ignore
import os, json

class OrklConverter:
    def __init__(self, helper):
        self.config = ConfigOrkl()
        self.helper = helper
        self.client_api = ReportClient(
            helper=self.helper,
            header=f"OpenCTI-orkl/{APP_VERSION}",
        )

        self.author = self._create_author()
    def add_references():
        pass

    def send_bundle(self, orkl_params: dict, work_id: str) -> None:
        """
        Send bundle to API
        :param orkl_params: Dict of params
        :param work_id: work id in string
        :return:
        """

        report_objects = self.perform_sync(work_id, orkl_params)


        # if len(software_objects) != 0:
        #     vulnerabilities_bundle = self._to_stix_bundle(software_objects)
        #     vulnerabilities_to_json = self._to_json_bundle(vulnerabilities_bundle)

        #     # Retrieve the author object for the info message
        #     info_msg = (
        #         f"[CONVERTER] Sending bundle to server with {len(vulnerabilities_bundle)} objects, "
        #         f"concerning {len(software_objects) - 1} vulnerabilities"
        #     )
        #     self.helper.log_info(info_msg)

        #     self.helper.send_stix2_bundle(
        #         vulnerabilities_to_json,
        #         update=self.config.update_existing_data,
        #         work_id=work_id,
        #     )

        # else:
        #     pass
    
    def get_version_sync_done(self):
        root_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = "sync_details.json"
        file_path = os.path.join(root_dir, file_path)
        with open(file_path, 'r') as json_file:
        # Load the JSON data from the file
            return json.load(json_file)["version_sync_done"]
    
    def get_latest_orkl_version(self):
        return int(self.client_api.get_latest_library_version()["data"]["ID"])
    
    
    def get_entries_from_year(self,from_year) -> list:
        task_completed = False
        limit = 100
        offset = 0
        result=[]
        while(task_completed == False):
            data = self.client_api.get_library_work_items(limit,offset)
            if data is not None:
                all_entries = data["data"]["entries"]
                filtered_entries = [entry for entry in all_entries if datetime.strptime(entry['CreatedAt'], '%Y-%m-%dT%H:%M:%S.%fZ').year >= from_year]
                if len(filtered_entries)==0:
                    result+=filtered_entries
                    self.current_orkl_entries=result
                    task_completed = True
                    return result
                else:
                    result+=filtered_entries
                    offset += limit
                    task_completed=False
            else:
                task_completed = True
                return result
    
    def get_entries_from_version_id(self,from_version_id) -> list:
        id_exists = False
        limit = 100
        offset = 0
        result=[]
        while(id_exists == False):
            data = self.client_api.get_library_work_items(limit,offset)
            if len(data["data"]["entries"])>0:
                all_entries = data["data"]["entries"]
            id_exists = self.check_version_id_exists(from_version_id,all_entries)
            if id_exists:
                filtered_entries = [entry for entry in all_entries if entry.get('ID') > from_version_id]
                result+=filtered_entries
                self.current_orkl_entries=result
                return result
            else:
                result+=all_entries
                offset += limit
                id_exists=False
            
    
    def check_year_exists(self,id, entries) -> bool:
        return [entry for entry in entries if entry.get('ID') == id]
    
    def check_version_id_exists(self,id, entries) -> bool:
        return [entry for entry in entries if entry.get('ID') == id]
    
    def process_entries(self, entries) -> list:
        result = []
        for entry in entries:
            reports = entry.get("created_library_entries")
            if reports:
                result+=self.process_reports(reports)
        
        return result        
                
    def process_reports(self, reports) -> list:
        result = []
        for report in reports:
            report_data = self.client_api.get_entry_by_id(report)["data"]
            result.append(report_data)
            print(report_data)
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
            msg = "[CONNECTOR] Connector has never run..."
            self.helper.log_info(msg)
            # running the connector for first time so get entries by the year
            all_entries = self.get_entries_from_year(SYNC_FROM_YEAR)
        elif version_sync_done > 0:
            # get all entries from where connector has left off from prevoius run
            all_entries = self.get_entries_from_version_id(version_sync_done)
            if len(all_entries)==0:
                # check if sync is up to date with orkl api
                msg = f"Data is already up to date. Latest entry id is {version_sync_done} and data sync done entry id is {version_sync_done}"
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
                                    f"[CONVERTER] completed extracting and sending reports to OCTI for {entry_id}"
                                )
                    self.helper.log_info(info_msg)        
        
                
        return results

    def perform_sync(self, work_id) -> list:
        """
        Retrieve all reports from orkl to convert into STIX2 format
        :param orkl_params: Dict of params
        :return: List of data converted into STIX2
        """
        results=[]
        config = ConfigOrkl()
        SYNC_FROM_VERSION = int(config.orkl_sync_from_version)
        version_sync_done = self.get_version_sync_done()  
        if version_sync_done > SYNC_FROM_VERSION:
            latest_version = self.get_latest_orkl_version()
            if latest_version > SYNC_FROM_VERSION and latest_version > version_sync_done:
                all_entries = self.get_entries_from_version_id(version_sync_done)
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
                        print(f"uncomment below code, perform entry sending..{entry['ID']} and {work_id}")
                        entries_processed_count+=1 # remove this line later only for debugging
                        
                        # extract_complete=self.extract_reports_send_bundle(entry,work_id)
                        # if extract_complete==True:
                        #     entry_id=entry["ID"]
                        #     self.update_version_sync_done(entry_id)
                        #     entries_processed_count+=1
                        #     info_msg = (
                        #                     f"[CONVERTER] completed extracting and sending reports to OCTI for {entry_id}"
                        #                 )
                        #     self.helper.log_info(info_msg)
            else:
                if SYNC_FROM_VERSION > latest_version:
                    raise Exception(f"Version does not exist, check orkl_sync_from_version in config file. Latest version is {latest_version} and sync from version is {SYNC_FROM_VERSION}")
                else:
                    if latest_version==version_sync_done:
                        msg = f"Data is already up to date. Latest version is {latest_version} and data sync done version is {SYNC_FROM_VERSION}"
                        self.helper.log_info(msg)
                    else:
                        raise Exception(f"Unable to perform sync from version {SYNC_FROM_VERSION} to latest version {latest_version}. Please check the config file.")        
        else:
            if version_sync_done < SYNC_FROM_VERSION:
                msg = f"sync from version is {SYNC_FROM_VERSION} and sync done version is : {version_sync_done}. Please change sync from version to >= {version_sync_done}"
                self.helper.log_info(msg)
                
        return results

    def extract_reports_send_bundle(self,entry,work_id):
        result=False
        current_entry_reports=[]
        reports = entry.get("created_library_entries")
        entry_id=entry["ID"]
        if reports:
            current_entry_reports+=self.process_reports(reports)
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
                                f"Sending bundle to server with {len(reports_bundle)} objects, "
                                f"concerning {len(processed_object) - 1} reports"
                            )
                            self.helper.log_info(info_msg)

                            self.helper.send_stix2_bundle(
                                reports_to_json,
                                update=self.config.update_existing_data,
                                work_id=work_id,
                            )
                            print("Completed extracting reports from {entry_id}")
                            #time.sleep(10)
                    result=True
            else:
                raise Exception(
                    "Attempting to extract reports from entry failed. " "Wait for connector to re-run..."
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
        result = {}
        result["version_sync_done"] = int(version)
        with open(file_path, "w") as outfile:
            json.dump(result, outfile)

    def check_and_replace_date(self, date_str):
        try:
            # Attempt to parse the date string
            datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            # If parsing fails, replace the date with the current date
            print("Invalid date format in {date_str}. Replacing with current date.")
            #default_date_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            default_date_str = None
            return default_date_str
        else:
            # If parsing succeeds, return the original date
            return date_str

    def resolve_source_names(self, source_name):
        shortname = source_name
        if ":" in source_name:
            shortname = source_name.split(":")[0]
        return shortname

    def process_object(self, object: dict) -> list:
        trimmed_list = object

        result = []

        external_references = []

        report = trimmed_list

        id = report["id"]
        created_at = report["created_at"]
        created_at = self.check_and_replace_date(created_at)
        updated_at = report["updated_at"]
        deleted_at = report["deleted_at"]
        sha1_hash = report["sha1_hash"]
        title = report["title"]
        authors = report["authors"]
        file_creation_date = report["file_creation_date"]
        file_creation_date=self.check_and_replace_date(file_creation_date)
        file_modification_date = report["file_modification_date"]
        file_modification_date=self.check_and_replace_date(file_modification_date)
        file_size = report["file_size"]
        plain_text = report["plain_text"]
        language = report["language"]
        sources = report["sources"]
        references = report["references"]
        report_names = report["report_names"]
        threat_actors = report["threat_actors"]


        event_markings = []

        report_name = report_names[0].split(".")[0]

        external_references=[]
        threat_actor_objects = []
        threat_actor_relationship_objects = []
        threat_actor_source_objects = []
        threat_actors_tools_objects=[]
        if len(threat_actors) > 0:
            for threat_actor in threat_actors:
                # create threat actor tools objects
                tools = threat_actor["tools"]
                if tools:
                    for tool in tools:
                        # Create tool object
                        tool_obj = stix2.Tool(
                            id=Tool.generate_id(tool),
                            name=tool,
                            labels="orkl-threat-actor-tool",
                            allow_custom=True,
                        )
                        #threat_actors_tools.append(tool_obj)
                        threat_actors_tools_objects.append(tool_obj)

                threat_actor_aliases = threat_actor["aliases"]
                threat_actor_obj_description = ""

                # create threat actor source object
                
                threat_actor_source_name = self.resolve_source_names(threat_actor["source_name"])
                threat_actor_source = stix2.Identity(
                                    id=Identity.generate_id(threat_actor_source_name, "organization"),
                                    name=threat_actor_source_name,
                                    created_by_ref=self.author.id,
                                )
                threat_actor_source_objects.append(threat_actor_source)

                # create threat actor object
                threat_actor_obj = stix2.ThreatActor(
                    id=ThreatActorIndividual.generate_id(threat_actor["main_name"]),
                    name=threat_actor["main_name"],
                    description=threat_actor_obj_description,
                    created=threat_actor["created_at"],
                    modified=threat_actor["updated_at"],
                    labels="orkl-threat-actor",
                    #object_refs=[threat_actor_source.id]+threat_actors_tools_ids,
                    created_by_ref=threat_actor_source.id,
                    custom_properties={
                        "x_opencti_description": threat_actor_obj_description,
                        "x_opencti_score": 50,
                        "x_opencti_aliases": threat_actor_aliases,
                    },
                    allow_custom=True,
                )
                threat_actor_objects.append(threat_actor_obj)

                # create relationship between threat actor and tools
                if tools:
                    for tool in threat_actors_tools_objects[:10]:
                        relationship = self._create_relationship(threat_actor_obj.id, tool.id, "uses")
                        threat_actor_relationship_objects.append(relationship)
                        #result.append(relationship)
                        #all_relationships_ids.append(relationship.id)
                
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
        
        
        # Check if the length of report_object_references is 0
        if len(report_object_references) == 0:
            # append report source as reference for the report
            report_object_references.append(report_source)  
            
        report = stix2.Report(
            id=Report.generate_id(report_name,created_at),
            name=report_name,
            description=plain_text,
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
