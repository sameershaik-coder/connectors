import datetime

import stix2 
from pycti import Identity, StixCoreRelationship, Report, CustomObservableText,ThreatActor,ThreatActorIndividual  # type: ignore
from services.utils import APP_VERSION, ConfigCPE  # type: ignore

from ..client import CPESoftware  # type: ignore


class CPEConverter:
    def __init__(self, helper):
        self.config = ConfigCPE()
        self.helper = helper
        self.client_api = CPESoftware(
            api_key=self.config.api_key,
            helper=self.helper,
            header=f"OpenCTI-cve/{APP_VERSION}",
        )
    
        self.author = self._create_author()
    def add_references():
        pass
    
    def send_bundle(self, cpe_params: dict, work_id: str) -> None:
        """
        Send bundle to API
        :param cpe_params: Dict of params
        :param work_id: work id in string
        :return:
        """
        
        software_objects = self.softwares_to_stix2(cpe_params)

        if len(software_objects) != 0:
            vulnerabilities_bundle = self._to_stix_bundle(software_objects)
            vulnerabilities_to_json = self._to_json_bundle(vulnerabilities_bundle)

            # Retrieve the author object for the info message
            info_msg = (
                f"[CONVERTER] Sending bundle to server with {len(vulnerabilities_bundle)} objects, "
                f"concerning {len(software_objects) - 1} vulnerabilities"
            )
            self.helper.log_info(info_msg)

            self.helper.send_stix2_bundle(
                vulnerabilities_to_json,
                update=self.config.update_existing_data,
                work_id=work_id,
            )

        else:
            pass
    
    def softwares_to_stix2(self, cpe_params: dict) -> list:
        """
        Retrieve all CVEs from NVD to convert into STIX2 format
        :param cpe_params: Dict of params
        :return: List of data converted into STIX2
        """
        softwares = self.client_api.get_softwares(cpe_params)

        trimmed_list = softwares["data"]

        result = []

        result.append(self.author)

        external_references = []

        for report in trimmed_list:
            # Getting different fields
            
            id = report["id"]
            created_at = report["created_at"]
            updated_at = report["updated_at"]
            deleted_at = report["deleted_at"]
            sha1_hash = report["sha1_hash"]
            title = report["title"]
            authors = report["authors"]
            file_creation_date = report["file_creation_date"]
            file_modification_date = report["file_modification_date"]
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
            
            if "files" in report:
                files=report["files"]
                if "pdf" in files:
                    external_reference = stix2.ExternalReference(
                        source_name="ORKL",  url=files["pdf"]
                    )
                    external_references.append(external_reference)
                if "text" in files:
                    external_reference = stix2.ExternalReference(
                        source_name="ORKL",  url=files["text"]
                    )
                    external_references.append(external_reference)
                if "img" in files:
                    external_reference = stix2.ExternalReference(
                        source_name="ORKL",  url=files["img"]
                    )
                    external_references.append(external_reference)
            
            if len(references) > 0:
                external_reference = stix2.ExternalReference(
                    source_name="ORKL",  url=references[0]
                )
                external_references.append(external_reference)
                
            source_objects=[]
            if len(sources) > 0:
                custom_properties = {
                        "x_opencti_description": sources[0]["description"],
                        "x_opencti_score": 50,
                        "labels": ["orkl-report-source"],
                        "created_by_ref": self.author.id,
                        "external_references": [],
                    }
                
                if sources[0]["name"] != None:
                    source_object = stix2.Identity(
                    id=Identity.generate_id(sources[0]["name"], "organization"),
                    name=sources[0]["name"],
                    description=sources[0]["description"],
                    created_by_ref=self.author.id,
                    custom_properties=custom_properties,
                    allow_custom=True,
                )
                else:
                    source_object = CustomObservableText(
                        value=sources[0]["id"],
                        custom_properties=custom_properties,
                    )
                source_objects.append(source_object)
                result.append(source_object)
            
            report = stix2.Report(
                id=Report.generate_id(report_name,created_at),
                name=report_name,
                description=plain_text,
                published=created_at,
                created=file_creation_date,
                modified=file_modification_date,
                report_types=["orkl-report"],
                object_marking_refs=event_markings,
                object_refs=source_objects,
                external_references=external_references,
                    confidence=60,
                    custom_properties={
                        "x_opencti_report_status": 2,
                        "x_opencti_files": [],
                        "created_by_ref": self.author.id,
                    },
                    allow_custom=True,
                )
            
            result.append(report)
            
            for threat_actor in threat_actors:
                threat_actor_obj_description = "Source : "
                threat_actor_obj_description = threat_actor_obj_description + threat_actor["source_name"] 
                
                threat_actor_obj = stix2.ThreatActor(
                    id=ThreatActorIndividual.generate_id(threat_actor["id"]),
                    name=threat_actor["main_name"],
                    created=threat_actor["created_at"],
                    modified=threat_actor["updated_at"],
                    labels="ORKL-threat-actor",
                    description=threat_actor_obj_description,
                    custom_properties={
                        "x_opencti_score": 50,
                        "created_by_ref": self.author.id,
                        "x_opencti_aliases": threat_actor["aliases"],
                    },
                    allow_custom=True,
                )
                result.append(threat_actor_obj)
                if threat_actor_obj is not None:
                    relationship = self._create_relationship(report.id, threat_actor_obj.id, "related-to")
                    result.append(relationship)
                
            
            for source_object in source_objects:
                relationship = self._create_relationship(report.id, source_object.id, "created-by")                
                result.append(relationship)
                
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
        :return: CVEs' default author
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
