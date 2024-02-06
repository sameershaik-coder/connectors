import datetime

import stix2 
from pycti import Identity, StixCoreRelationship,CustomObservableText,StixCyberObservable, StixCyberObservableTypes,Vulnerability  # type: ignore
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
            # vulnerabilities_bundle = stix2.Bundle(objects=software_objects, allow_custom=True).serialize()
            # vulnerabilities_to_json = vulnerabilities_bundle
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

        trimmed_list = softwares[:8]

        result = []

        result.append(self.author)

        external_references = []

        for software in trimmed_list:
            # Getting different fields
            
            cpename = software["cpe"]["cpeName"]
            cpenameid = software["cpe"]["cpeNameId"]
            if "titles" in software["cpe"]:
                cpe = software["cpe"]["titles"][0]["title"]
                languages = [
                software["cpe"]["titles"][0]["lang"]
                            ]

            # Create external references
            external_reference = stix2.ExternalReference(
                source_name="NIST NVD",  url=f"https://nvd.nist.gov/products/cpe/detail/{cpenameid}"
            )

            external_references = [external_reference]
            
            if "cpe" in software and "refs" in software["cpe"]:
                for reference in software["cpe"]["refs"]:
                    if "type" in reference and "ref" in reference:
                        external_reference = stix2.ExternalReference(
                            source_name=reference["type"], url=reference["ref"]
                        )
                        external_references.append(external_reference)

            score = 75

            # Creating the vulnerability with the extracted fields
            custom_properties = {
                        "x_opencti_description": cpe,
                        "x_opencti_score": score,
                        "created_by_ref": self.author.id,
                        "external_references": external_references,
                    }
                    
            software_obj = stix2.Software(
                name=cpename,
                cpe=cpe,
                swid=cpenameid,
                languages=languages,
                custom_properties=custom_properties,
            )
            
            result.append(software_obj)

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
            id=Identity.generate_id("The MITRE Corporation", "organization"),
            name="The MITRE Corporation",
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
