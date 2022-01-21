import json
import logging

import requests

logger = logging.getLogger(__name__)


class QondorClient:
    def __init__(self, key):
        self.key = key
        self.get_all_projects_url = "https://qondor.azure-api.net/Prod/Project/v1/Project/GetAll"
        self.get_all_participants_for_a_project_url = "https://qondor.azure-api.net/Prod/Participant/v1/Participant/GetForProject?projectId={0}"
        self.get_all_custom_participant_fields_url = "https://qondor.azure-api.net/Prod/Participant/v1/ParticipantField/GetForProject?projectId={0}"
        self.create_custom_company_participant_field_url = "https://qondor.azure-api.net/Prod/Participant/v1/ParticipantField"
        self.send_single_participant_url = "https://qondor.azure-api.net/Prod/Participant/v1/Participant"
        self.headers = {"Content-Type": "application/json; charset=utf-8",
                        "Ocp-Apim-Subscription-Key": self.key}

    def get_all_projects(self, changed_after=None):
        if changed_after:
            response = requests.get(url=self.get_all_projects_url + "?changedAfter={0}".format(changed_after),
                                    headers=self.headers).json()
        else:
            response = requests.get(url=self.get_all_projects_url,
                                    headers=self.headers).json()
        return [{"id": project["id"], "name": project["name"]} for project in response]

    def get_all_participants_for_a_project(self, project_id):
        response = requests.get(url=self.get_all_participants_for_a_project_url.format(project_id),
                                headers=self.headers).json()
        return [{participant.get("email", None): participant.get("participantReference", None)}
                for participant in response]

    # the default company field by Qondor does not work
    # the custom field Visma wants therefore is "Kommune/virksomhet"
    # however, sometimes they are not available, unless created
    # here is where you check for it to know if it exits or not
    # and then proceed creating one, if it doesn't
    def check_custom_company_participant_field_existence(self, project_id):
        response = requests.get(url=self.get_all_custom_participant_fields_url.format(project_id),
                                headers=self.headers).json()
        return "Kommune/virksomhet" in [field["heading"] for field in response]

    def create_custom_company_participant_field(self, project_id):
        if not self.check_custom_company_participant_field_existence(project_id):
            data = {
                "projectId": project_id,
                "heading": "Kommune/virksomhet"
            }
            response = requests.post(url=self.create_custom_company_participant_field_url,
                                     headers=self.headers,
                                     data=json.dumps(data))
            if response.status_code == 200:
                return True
            else:
                return False
        return None
        # decide more on output to catch all errors

    def send_single_participant(self, project_id, existing_emails, existing_participant_data, data):
        if data:
            # if data is not in the right format, it cannot be add/update
            if not data.get("firstName", None) or not data.get("lastName", None):
                return False
            # reformat data for custom company participant field
            if data.get("company", None):
                data["participantFields"] = {"Kommune/virksomhet": data["company"]}
            # in the future, the new API will enable us to post participant status of attending to be "potential" by default
            # the name of the field is unknown and the value is unknown as well
            # if the name is "Attending" and the value is "potential"
            # you shoud add here the code:
            # data["participantFields"] = {"Attending": "Potential"}
            # or if the value is a number:
            # data["participantFields"] = {"Attending": 5}

            # check if a participant has already been registered to decide add or update
            email = data.get("email", None)

            # add a new participant
            if email not in existing_emails:
                data["projectId"] = project_id
                try:
                    response = requests.post(url=self.send_single_participant_url,
                                             headers=self.headers,
                                             data=json.dumps(data))
                    if response.status_code != 200:
                        logger.debug("-----ERROR----- Adding participant to project {0}: {1}".
                                     format(project_id, data.get("email", None)))
                    return True
                except Exception as e:
                    logger.debug(e)
                    logger.debug("-----ERROR----- Adding participant to project {0}: {1}".
                                 format(project_id, data.get("email", None)))
                    return False

            # update an existing participant
            else:
                index = existing_emails.index(email)
                data["reference"] = existing_participant_data[index][email]
                try:
                    response = requests.put(url=self.send_single_participant_url,
                                            headers=self.headers,
                                            data=json.dumps(data))
                    if response.status_code != 200:
                        logger.debug("-----ERROR----- Updating participant to project {0}: {1}".
                                     format(project_id, data.get("email", None)))
                    return True
                except Exception as e:
                    logger.debug(e)
                    logger.debug("-----ERROR----- Updating participant to project {0}: {1}".
                                 format(project_id, data.get("email", None)))
                    return False

        logger.debug("-----WARNING----- No project id to add participant")
        return None
