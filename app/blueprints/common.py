import logging
from abc import ABC
from typing import Tuple, List, Dict

from flask import Blueprint, current_app, abort, request, jsonify
from flask.views import View

from ..database import get_db
from ..decorators import validate_oauth_signature, required_args, require_authed_session
from ..enums import ServiceType
from ..session import Session, get_session
from ..util import ServiceRequest

logger = logging.getLogger(__name__)


class BaseEloquaView(View, ABC):
    """
    Base view for Eloqua cloud apps.
    """

    default_name = None
    default_url_rule = None

    @classmethod
    def add_url_rule_to(cls, blueprint: Blueprint, view_name: str = None, *view_args, **view_kwargs):
        view_name = view_name or cls.default_name
        blueprint.add_url_rule(cls.default_url_rule, view_func=cls.as_view(view_name, *view_args, **view_kwargs))

    @property
    def default_response(self) -> Tuple[str, int]:
        raise NotImplementedError()

    @property
    def args(self):
        return ServiceRequest(request)

    @property
    def db(self):
        return get_db()

    def insert_service_log(self, msg=None, error=None, extra=None):
        extra = extra or {}
        data = {**self.args.as_dict(), **extra}

        if msg:
            data["_message"] = msg
        if error:
            data["_error"] = error

        data["method"] = request.method
        get_db().insert_service_log(self.default_name, data)

    def dispatch_request(self, *args, **kwargs):
        return self.default_response


class BaseCreateView(BaseEloquaView, ABC):
    """
    Base view for cloud app instance creation.

    :param record_definition: (Optional) The record definition to use.
    :param requires_configuration: (Optional) Whether the instance requires an immediate configuration or not, i.e.
           show the configuration screen on instance creation.
    :param instance_type: (Optional) The cloud app service type. Saved to the database, otherwise has no use.
    """

    methods = ["POST"]
    default_url_rule = "/create/<string:app_id>/<string:install_id>"
    decorators = [required_args(["instance_id"]), validate_oauth_signature]

    def __init__(self, record_definition: dict = None, requires_configuration: bool = False,
                 instance_type: ServiceType = None, instance_config: dict = None):
        self.record_definition = record_definition or {}
        self.requires_configuration = requires_configuration
        self.instance_type = instance_type
        self.instance_config = instance_config

    @property
    def instance_id(self):
        """
        Gets the instance id from the request query parameters.

        :return: The instance id.
        """
        return request.args["instance_id"]

    @property
    def eloqua_configuration(self) -> dict:
        """
        Returns the Eloqua configuration dictionary. Used in default response.

        :return: Eloqua configuration
        """
        return {
            "recordDefinition": self.record_definition,
            "requiresConfiguration": self.requires_configuration,
        }

    @property
    def default_response(self) -> Tuple[str, int]:
        return jsonify(self.eloqua_configuration), 200


class DefaultCreateView(BaseCreateView):
    """
    Default implementation for :class:`BaseCreateView`. Creates the instance and logs whether it was successful or not.
    Responds with 200 & the config dict if successful, 500 otherwise.
    """

    default_name = "eloqua_instance_create"

    def create_instance_in_db(self, app_id, install_id, eloqua_configuration=None, instance_config=None) -> bool:
        success = self.db.save_service_instance(app_id, install_id, self.instance_id, instance_type=self.instance_type,
                                                eloqua_configuration=eloqua_configuration or self.eloqua_configuration,
                                                configuration=instance_config or self.instance_config)
        if success:
            current_app.logger.info("Created new instance '%s' in '%s'.", self.instance_id, install_id)
        else:
            current_app.logger.error("Something went wrong while trying to create new instance '%s' in '%s'.",
                                     self.instance_id, install_id)
        return success

    def dispatch_request(self, app_id, install_id):
        success = self.create_instance_in_db(app_id, install_id)
        if success:
            return self.default_response
        else:
            abort(500)


class BaseConfigureView(BaseEloquaView, ABC):
    """
    Base configuration view for cloud app instances.
    """

    methods = ["GET", "POST"]
    default_url_rule = "/configure/<string:app_id>/<string:install_id>/<string:instance_id>"
    decorators = [require_authed_session, validate_oauth_signature(methods=["GET"], create_new_session=True)]

    def __init__(self):
        self._session = None
        self.app_id = None
        self.install_id = None
        self.instance_id = None

    def get(self, app_id, install_id, instance_id, *args, **kwargs) -> Tuple[str, int]:
        return self.default_response()

    def post(self, app_id, install_id, instance_id, *args, **kwargs) -> Tuple[str, int]:
        return self.default_response()

    def dispatch_request(self, app_id, install_id, instance_id, *args, **kwargs):
        self.app_id = app_id
        self.install_id = install_id
        self.instance_id = instance_id

        if request.method == "POST":
            self.insert_service_log(extra={"posted_data": request.form})
        else:
            self.insert_service_log()

        if request.method == "GET":
            return self.get(app_id, install_id, instance_id, *args, **kwargs)

        if request.method == "POST":
            return self.post(app_id, install_id, instance_id, *args, **kwargs)

        # Method not allowed.
        abort(405)

    def default_response(self, *args, **kwargs) -> Tuple[str, int]:
        return "No configurations available.", 200

    @property
    def session(self) -> Session:
        if not self._session:
            self._session = get_session()
        return self._session

    def get_app_config(self, app_id, install_id):
        return self.db.get_installation_config(app_id, install_id)

    def get_config(self, app_id=None, install_id=None, instance_id=None):
        return self.db.get_service_instance_custom_configuration(app_id or self.app_id, install_id or self.install_id,
                                                                 instance_id or self.instance_id)

    def get_eloqua_config(self, app_id=None, install_id=None, instance_id=None):
        return self.db.get_service_instance_eloqua_configuration(app_id or self.app_id, install_id or self.install_id,
                                                                 instance_id or self.instance_id)

    def save_config(self, config: dict, app_id=None, install_id=None,
                    instance_id=None, partial_update=False):
        self.db.save_service_instance(app_id or self.app_id, install_id or self.install_id,
                                      instance_id or self.instance_id, configuration=config,
                                      partial_update=partial_update)

    def save_eloqua_config(self, config: dict, app_id=None, install_id=None, instance_id=None):
        self.db.save_service_instance(app_id or self.app_id, install_id or self.install_id,
                                      instance_id or self.instance_id, eloqua_configuration=config,
                                      partial_update=True)


class BaseNotifyView(BaseEloquaView, ABC):
    """
    Base view for receiving cloud app notifications. Responds with a 200 code; if you want to handle the notifications
    asynchronously, use BaseAsyncNotifyView instead.
    """

    methods = ["POST"]
    default_url_rule = "/notify/<string:app_id>/<string:install_id>/<string:instance_id>"
    decorators = [validate_oauth_signature]

    @property
    def total_results(self):
        """
        Returns the total number of items from the notification request.

        :return: Total results
        """
        return request.json.get("totalResults", 0)

    @property
    def items(self) -> List[Dict]:
        """
        Returns the items from the notification request. Defaults to an empty list.

        :return: The items from the notification request
        """
        return request.json.get("items", [])

    @property
    def execution_id(self) -> str:
        """
        Returns the execution id from the request (if `execution_id` is set as a query parameter in the notification
        URL).

        :return: The execution ID or None if not set.
        """
        return request.args.get("execution_id", None)

    @property
    def default_response(self) -> Tuple[str, int]:
        return "", 200

    def process_items(self, app_id: str, install_id: str, instance_id: str, items: List[Dict], total_results,
                      execution_id: str = None) -> None:
        """
        Processes the received notification items. Called by default by :meth:`dispatch_request`. Must be implemented by
        subclasses.

        :param app_id: App id.
        :param install_id: Installation id.
        :param instance_id: Instance id.
        :param items: Items received in the notification request.
        :param total_results: Total number of items in the notification request.
        :param execution_id: (Optional) The execution id (or the id of the batch received). Might be `None` if
               `execution_id` is not set as a query parameter in the notification URL.
        """
        raise NotImplementedError()

    def dispatch_request(self, app_id: str, install_id: str, instance_id: str):
        self.process_items(app_id, install_id, instance_id, self.items, self.total_results, self.execution_id)
        return self.default_response


class BaseAsyncNotifyView(BaseNotifyView, ABC):
    """
    Base view for receiving cloud app notifications. Basically the same as :class:`BaseAsyncNotifyView`, but responds
    with 204 instead of 200, i.e. the notification items should be handled asynchronously.
    """

    @property
    def default_response(self) -> Tuple[str, int]:
        return "", 204


class BaseDeleteView(BaseEloquaView, ABC):
    """
    Base view for deleting cloud app instances.
    """

    methods = ["DELETE"]
    default_url_rule = "/delete/<string:app_id>/<string:install_id>/<string:instance_id>"
    decorators = [validate_oauth_signature]

    @property
    def default_response(self) -> Tuple[str, int]:
        return "", 204


class DefaultDeleteView(BaseDeleteView):
    """
    Default implementation for :class:`BaseDeleteView`. Deletes the instance and logs whether it was successful or not.
    Responds with 204 if successful, 404 otherwise.
    """

    default_name = "eloqua_instance_delete"

    @staticmethod
    def delete_instance_in_db(app_id: str, install_id: str, instance_id: str) -> bool:
        success = get_db().delete_service_instance(app_id, install_id, instance_id)
        if success:
            current_app.logger.info("Deleted instance '%s' in installation '%s'.", instance_id, install_id)
        else:
            current_app.logger.warning("Couldn't delete instance '%s' in installation '%s'.", instance_id, install_id)
        return success

    def dispatch_request(self, app_id: str, install_id: str, instance_id: str):
        self.insert_service_log()
        success = self.delete_instance_in_db(app_id, install_id, instance_id)
        if success:
            return "", 204
        else:
            abort(404)
