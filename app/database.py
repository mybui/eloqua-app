import datetime
import logging
from typing import Mapping, Iterable

from bson.objectid import ObjectId
from flask import g, current_app
from pymongo import MongoClient, ReturnDocument

from .enums import ServiceType

logger = logging.getLogger(__name__)


def get_db():
    if "db" not in g:
        g.db = Database()

    return g.db


# TODO Make less dependent on MongoDB
# TODO Extract an abstract base class, use that to create database adapters
class Database:
    def __init__(self):
        self._client = MongoClient(current_app.config["DB_CONNECTION_STRING"])
        self._database = self._client[current_app.config["CLOUD_APP_DB_NAME"]]
        self._installations = self._database["installations"]
        self._sessions = self._database["sessions"]
        self._cache = self._database["cache"]
        self._instances = self._database["instances"]
        self._data_dump = self._database["data_dump"]
        self._service_logs = self._database["service_logs"]
        self._executions = self._database["executions"]
        self._data_dump_ttl = current_app.config["CLOUD_APP_DB_DATA_DUMP_TTL"]
        self._service_log_ttl = current_app.config["CLOUD_APP_DB_SERVICE_LOG_TTL"]

        # self._ensure_collection_indexes()

        logger.debug("Created new Database object.")

    def __del__(self):
        logger.debug("Deleting Database object.")

    # Protected internal methods

    def _ensure_collection_indexes(self):
        if "_expires_at" not in self._sessions.index_information():
            self._sessions.create_index("_expires_at", expireAt=True, expireAfterSeconds=0)

        if "_expires_at" not in self._cache.index_information():
            self._cache.create_index("_expires_at", expireAt=True, expireAfterSeconds=0)

        if "created_at" not in self._data_dump.index_information():
            self._data_dump.create_index("created_at", expireAfterSeconds=self._data_dump_ttl)

        if "_created_at" not in self._service_logs.index_information():
            self._service_logs.create_index("_created_at", expireAfterSeconds=self._service_log_ttl)

        if "_created_at" not in self._executions.index_information():
            self._executions.create_index("_created_at", expireAfterSeconds=datetime.timedelta(days=1).total_seconds())

    @staticmethod
    def _get_expiration_date(expires_in):
        return datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)

    @staticmethod
    def _create_partial_embedded_update(prefix, data):
        return {"{}.{}".format(prefix, k): v for k, v in data.items()}

    @staticmethod
    def _flatten_dict(d: Mapping, separator: str = ".") -> dict:
        out = {}

        def _flatten(x: Mapping, parents=()):
            for k, v in x.items():
                if isinstance(v, Mapping) and v.items():
                    _flatten(v, (*parents, k))
                else:
                    out[separator.join((*parents, k))] = v

        _flatten(d)

        return out

    # Installation method

    def upsert_installation(self, data, config=None):
        update_set = {**data}
        if config:
            update_set["config"] = config

        self._installations.update_one(filter={"install_id": data["install_id"]},
                                       update={"$set": update_set},
                                       upsert=True)

    def update_installation(self, app_id, install_id, data, config=None):
        update_set = {**data}
        if config:
            update_set["config"] = config

        result = self._installations.update_one(filter={"install_id": install_id, "app_id": app_id},
                                                update={"$set": update_set})
        if result.matched_count < 1:
            logger.warning("Couldn't update installation data with app_id '%s' and install_id '%s'", app_id, install_id)
            return False
        return True

    def delete_installation(self, app_id, install_id):
        result = self._installations.delete_one({"install_id": install_id, "app_id": app_id})
        if result.deleted_count < 1:
            logger.warning("Couldn't delete installation data with install_id '%s' and app_id '%s'", install_id, app_id)
            return False
        return True

    def get_installation(self, app_id, install_id):
        return self._installations.find_one({"app_id": app_id, "install_id": install_id})

    def get_installation_config(self, app_id, install_id):
        installation = self.get_installation(app_id, install_id)
        if installation is None:
            return installation

        config = installation.get("config", {})
        return config

    def get_base_url_for(self, app_id, install_id):
        result = self.get_installation(app_id, install_id)
        if result is None:
            return None
        else:
            return result.get("base_url")

    def get_token(self, app_id, install_id):
        result = self.get_installation(app_id, install_id)
        if result is None:
            return None
        else:
            return result.get("oauth", {}).get("token")

    def set_token(self, app_id, install_id, token):
        return self._installations.update_one({"app_id": app_id, "install_id": install_id},
                                              {"$set": {"oauth.token": token}})

    # Service instance methods

    def save_service_instance(self, app_id: str, install_id: str, instance_id: str, instance_type: ServiceType = None,
                              eloqua_configuration: dict = None, configuration: dict = None, partial_update=True):
        set_dict = {}

        if eloqua_configuration is not None:
            if partial_update:
                set_dict = {**set_dict,
                            **self._create_partial_embedded_update("configuration.eloqua", eloqua_configuration)}
            else:
                set_dict["configuration.eloqua"] = eloqua_configuration

        if configuration is not None:
            if partial_update:
                set_dict = {**set_dict,
                            **self._create_partial_embedded_update("configuration.custom", configuration)}
            else:
                set_dict["configuration.custom"] = configuration

        if instance_type is not None:
            set_dict["type"] = instance_type.value

        update = {
            "$setOnInsert": {
                "app_id": app_id,
                "install_id": install_id,
                "instance_id": instance_id
            },
            "$currentDate": {
                "last_modified": True
            }
        }

        if set_dict:
            update["$set"] = set_dict

        result = self._instances.update_one(
            {
                "app_id": app_id,
                "install_id": install_id,
                "instance_id": instance_id
            },
            update,
            upsert=True)
        return result.matched_count > 0 or result.upserted_id is not None

    def delete_service_instance(self, app_id: str, install_id: str, instance_id: str):
        result = self._instances.delete_one({
            "app_id": app_id,
            "install_id": install_id,
            "instance_id": instance_id
        })

        return result.deleted_count > 0

    def get_service_instance(self, app_id, install_id, instance_id):
        result = self._instances.find_one({
            "app_id": app_id,
            "install_id": install_id,
            "instance_id": instance_id
        })

        return result

    def get_hourly_active_instances(self):
        result = self._instances.find(
            {"configuration.custom.status": "Activated",
             "configuration.custom.frequency": "Hourly"})

        return result

    def get_daily_active_instances(self):
        result = self._instances.find(
            {"configuration.custom.status": "Activated",
             "configuration.custom.frequency": "Daily"})

        return result

    def get_weekly_active_instances(self):
        result = self._instances.find(
            {"configuration.custom.status": "Activated",
             "configuration.custom.frequency": "Weekly"})

        return result

    def service_instance_exists(self, app_id, install_id, instance_id):
        count = self._instances.count_documents({
            "app_id": app_id,
            "install_id": install_id,
            "instance_id": instance_id
        }, limit=1)
        return count > 0

    def get_service_instance_custom_configuration(self, app_id, install_id, instance_id):
        result = self._instances.find_one({
            "app_id": app_id,
            "install_id": install_id,
            "instance_id": instance_id
        })

        if result:
            return result.get("configuration", {}).get("custom", {})

        return result

    def get_service_instance_eloqua_configuration(self, app_id, install_id, instance_id):
        result = self._instances.find_one({
            "app_id": app_id,
            "install_id": install_id,
            "instance_id": instance_id
        })

        if result:
            return result.get("configuration", {}).get("eloqua", {})

        return result

    # Custom session methods

    def set_session(self, data, session_id=None, expires_in=3600, is_authed=None):
        doc = {
            "_expires_in": expires_in,
            "_expires_at": self._get_expiration_date(expires_in),
            "data": data
        }

        if is_authed is not None:
            doc["is_authed"] = is_authed

        if session_id is None:
            result = self._sessions.insert_one(doc)
            return self._sessions.find_one({"_id": result.inserted_id})
        else:
            result = self._sessions.find_one_and_update(filter={"_id": ObjectId(session_id)},
                                                        update={"$set": doc}, return_document=ReturnDocument.AFTER)
            return result

    def get_session(self, session_id, refresh_session=True):
        logger.debug("#### {}".format(session_id))
        if isinstance(session_id, ObjectId):
            _id = session_id
        else:
            _id = ObjectId(session_id)
        result = self._sessions.find_one({"_id": ObjectId(session_id)})

        if result is not None:
            if refresh_session:
                self._sessions.update_one(filter={"_id": _id},
                                          update={
                                              "$set": {
                                                  "_expires_at": self._get_expiration_date(result["_expires_in"])
                                              }
                                          })
            return result
        else:
            return None

    def delete_session(self, session_id):
        if isinstance(session_id, ObjectId):
            _id = session_id
        else:
            _id = ObjectId(session_id)

        result = self._sessions.delete_one({"_id": _id})
        return result.deleted_count > 0

    # Cache methods

    def save_to_cache(self, data, expires_in=300):
        doc = {
            "_expires_in": expires_in,
            "_expires_at": self._get_expiration_date(expires_in),
            "data": data
        }

        result = self._cache.insert_one(doc)
        return result.inserted_id

    def find_one_from_cache(self, matching_data):
        if isinstance(matching_data, Mapping):
            return self._cache.find_one(self._flatten_dict({"data": matching_data}))
        else:
            return self._cache.find_one({"data": matching_data})

    def find_from_cache(self, matching_data) -> Iterable:
        if isinstance(matching_data, Mapping):
            return self._cache.find(self._flatten_dict({"data": matching_data}))
        else:
            return self._cache.find({"data": matching_data})

    # Data dump methods

    def insert_data_dump(self, description, data, app_id=None, install_id=None, instance_id=None, force_dump=False):
        if current_app.config["DEBUG"] is True or current_app.config["TESTING"] is True or force_dump is True:
            self._data_dump.insert_one({
                "app_id": app_id or current_app.config.get("CLOUD_APP_CLIENT_ID"),
                "install_id": install_id,
                "instance_id": instance_id,
                "description": description,
                "created_at": datetime.datetime.utcnow(),
                "data": data
            })

    def insert_service_log(self, view_name, extra=None):
        extra = dict(sorted((extra or {}).items()))
        self._service_logs.insert_one({
            "_created_at": datetime.datetime.utcnow(),
            "_view_name": view_name,
            **extra,
        })

    # Executions

    def insert_execution(self, app_id, install_id, instance_id, execution_id):
        result = self._executions.insert_one({
            "_created_at": datetime.datetime.utcnow(),
            "app_id": app_id,
            "install_id": install_id,
            "instance_id": instance_id,
            "execution_id": execution_id,
            "instance_config": self.get_service_instance_custom_configuration(app_id, install_id, instance_id)
        })

        return result.inserted_id

    def get_execution(self, execution_id):
        return self._executions.find_one({"execution_id": execution_id})

    def get_instance(self, instance_id):
        return self._executions.find_one({"execution_id": instance_id})

    def get_qondor_project_id(self, app_id, install_id, instance_id):
        """
        same with method get_service_instance_custom_configuration but get one level deeper: project (id)
        """
        result = self._instances.find_one({
            "app_id": app_id,
            "install_id": install_id,
            "instance_id": instance_id
        })

        if result:
            return result.get("configuration", {}).get("custom", {}).get("project", None)

        return result
