import logging

from collections import namedtuple
from typing import List, Dict, Tuple

from dea import EloquaClient
from dea.bulk.definitions import SyncActionsDefinition
from flask import Blueprint, request, flash, render_template

from .common import DefaultCreateView, DefaultDeleteView, BaseAsyncNotifyView, BaseConfigureView
from ..database import get_db
from ..eloqua_outbound_config import *
from ..qondor_client import *
from ..session import get_eloqua_session
from ..settings import *
from ..util import ServiceRequest

logger = logging.getLogger(__name__)


class NotifyView(BaseAsyncNotifyView, BaseConfigureView):
    default_name = "qondor_integration_notify"

    def process_items(self, app_id: str, install_id: str, instance_id: str, items: List[Dict], total_results,
                      execution_id: str = None) -> None:
        args = ServiceRequest(request)
        args.instance_id = instance_id
        db = get_db()
        db.insert_service_log(self.default_name, {"total_results": total_results, "instance_id": instance_id,
                                                  "install_id": install_id, "app_id": app_id, **args.as_dict()})
        logger.debug("///////////////////////////////////////////////////////////////////////////////")
        logger.debug("Received {0}s contacts".format(total_results))
        logger.debug(items)
        db.insert_execution(app_id, install_id, instance_id, execution_id)

        # prepare for adding/updating contacts
        logger.debug("Start sending contact to Qondor")
        # get project id
        success_contacts = []
        error_contacts = []
        missing_project_id = []

        qondor_client = QondorClient(key=QONDOR_PRIMARY_KEY)
        project_id = db.get_qondor_project_id(app_id=app_id, install_id=install_id, instance_id=instance_id)
        # create custom company participant field if not existed
        qondor_client.create_custom_company_participant_field(project_id=project_id)
        # get existing contacts to avoid re-adding them, as they should only be updated
        existing_participant_data = qondor_client.get_all_participants_for_a_project(project_id=project_id)
        existing_emails = [list(email.keys())[0] for email in existing_participant_data]
        # add/update contacts
        for contact in items:
            # don't need to send Eloqua ID in Qondor POST body
            # this step is for updating contact status in Eloqua later
            # after adding/updating contacts in Qondor
            contact_id = contact.pop("id", None)
            data_to_sync = {"id": contact_id}

            contact_status = qondor_client.send_single_participant(project_id=project_id,
                                                                   existing_emails=existing_emails,
                                                                   existing_participant_data=existing_participant_data,
                                                                   data=contact)
            if contact_status and isinstance(contact_status, bool):
                success_contacts.append(data_to_sync)
            elif not contact_status and isinstance(contact_status, bool):
                error_contacts.append(data_to_sync)
            # attach error of missing project id separately for easier debug, if happened
            else:
                error_contacts.append(data_to_sync)
                missing_project_id.append(contact_id)

        # update contact status after successfully or not sent to Qondor
        if len(success_contacts):
            logger.debug("Syncing {} success contacts".format(len(success_contacts)))
            self.import_contact_status(success=True, contacts=success_contacts, execution_id=execution_id)
        if len(error_contacts):
            logger.debug("Syncing {} error contacts".format(len(error_contacts)))
            self.import_contact_status(success=False, contacts=error_contacts, execution_id=execution_id)

        logger.debug(
            "Contacts failed to sent because no Qondor project id was specified: {0}".format(missing_project_id))
        logger.debug("Contacts failed to sent because of other reasons: {0}".format(
            [contact["id"] for contact in error_contacts]))
        logger.debug("Finish sending contact to Qondor")
        logger.debug("///////////////////////////////////////////////////////////////////////////////")

    @staticmethod
    def import_contact_status(success, contacts, execution_id):
        db = get_db()
        execution_info = db.get_execution(execution_id)
        install_id = execution_info["install_id"]
        instance_id = execution_info["instance_id"]

        logger.debug("---------------------------------------------")
        logger.debug("Start importing contact status to Eloqua")
        import_def = SyncActionsDefinition(
            f"Qondor integration #{execution_id} for contacts",
            fields={
                "id": eml.Contact.Id,
            },
            id_field_name="id",
            sync_actions={
                "action": "setStatus",
                "destination": eml.ActionInstance(instance_id).Execution(execution_id),
                "status": "complete" if success else "errored"
            })

        eloqua_client = EloquaClient(session=get_eloqua_session(install_id))
        with eloqua_client.bulk_contacts.imports.create_sync_action(import_def) as bulk_import:
            bulk_import.add_items(contacts)
            bulk_import.upload_and_flush_data(sync_on_upload=True)
        logger.debug("Finish importing contact status to Eloqua")
        logger.debug("---------------------------------------------")


class ConfigureView(BaseConfigureView):
    default_name = "qondor_integration_config"

    def get_projects(self):
        project_info_pair = namedtuple("Project", ("name", "id"))
        project_name_id_tuple_list = []
        qondor_client = QondorClient(key=QONDOR_PRIMARY_KEY)
        # add date time filter
        projects = qondor_client.get_all_projects()
        for project in projects:
            project_name_id_tuple_list.append(project_info_pair(project["name"], str(project["id"])))
        return project_name_id_tuple_list

    @staticmethod
    def validate_form() -> Tuple[bool, List[str]]:
        messages = []
        form = request.form
        selected_project = form.get("project", None)
        if selected_project == "None":
            messages.append("Please select a project")
        return len(messages) == 0, messages

    def get(self, app_id, install_id, instance_id, *args, **kwargs) -> Tuple[str, int]:
        return self.default_response()

    def post(self, app_id, install_id, instance_id, *args, **kwargs) -> Tuple[str, int]:
        is_valid, errors = self.validate_form()

        if not is_valid:
            for error in errors:
                flash(error, "error")
            return self.default_response(request.form)

        # Get configurations from the database
        eloqua_config = self.get_eloqua_config()
        new_eloqua_config = {
            "recordDefinition": {**fields},
            "requiresConfiguration": False
        }

        # Save Eloqua side configurations first (if needed)
        if new_eloqua_config != eloqua_config:
            logger.debug("Changes detected in Eloqua configuration")
            logger.debug(f"Old: {eloqua_config}")
            logger.debug(f"New: {new_eloqua_config}")
            eloqua_client = EloquaClient(session=get_eloqua_session(install_id))
            eloqua_client.put(
                eloqua_client.url_for("/api/cloud/1.0/actions/instances/{instance_id}", instance_id=instance_id),
                json=new_eloqua_config)
            self.save_eloqua_config(new_eloqua_config)
            logger.debug("Eloqua configuration updated")
        self.save_config({
            "project": str(request.form["project"])
        })

        flash("Changes saved", "success")
        return self.default_response()

    def default_response(self, form_values: dict = None) -> Tuple[str, int]:
        logger.debug(f"Config: {self.get_config()}")
        form_values = self.get_config() or form_values or {}
        return render_template("config.html", subtitle="Instance configuration", projects=self.get_projects(),
                               form_values=form_values)


bp = Blueprint("visma_qondor_integration", __name__, url_prefix="/eloqua/ops")
DefaultCreateView.add_url_rule_to(bp, "qondor_integration_create",
                                  record_definition=fields,
                                  requires_configuration=True,
                                  instance_config={})
DefaultDeleteView.add_url_rule_to(bp, "qondor_integration_delete")
NotifyView.add_url_rule_to(bp)
ConfigureView.add_url_rule_to(bp)
