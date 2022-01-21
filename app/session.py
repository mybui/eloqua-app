import logging
from datetime import datetime

from flask import session as flask_session, current_app
from oauthlib.oauth2 import WebApplicationClient
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session

from .auth import TokenManager, get_redirect_uri
from .database import get_db


logger = logging.getLogger(__name__)


class BaseSessionError(Exception):
    ...


class SessionExpired(BaseSessionError):
    ...


class SessionNotFound(BaseSessionError):
    ...


class Session(dict):
    def __init__(self, initial_data: dict = None, is_authed: bool = False, create_new=False):
        session_id = flask_session.get("session_id", None)
        expires_at = flask_session.get("expires_at", None)
        session_from_db = None

        # Try to get the session from the database if a session ID is set.
        if session_id:
            logger.debug("Session ID found.")
            session_from_db = get_db().get_session(session_id)

        # Check whether to create a new session or not; if yes, we skip the expiration/existence validations.
        if create_new:
            if session_from_db is not None:
                # Delete any existing sessions.
                get_db().delete_session(session_id)
                logger.debug("Deleted the existing session.")

            # Create a new session.
            session_from_db = get_db().set_session(initial_data or {}, is_authed=is_authed)
            logger.debug("Created a new session.")
        else:
            if (session_id and session_from_db is None) or (expires_at and datetime.utcnow().timestamp() >= expires_at):
                # Check if the session has expired or if the session is missing (i.e. expired as well).
                logger.debug("Session has expired.")
                flask_session.clear()
                raise SessionExpired()
            elif session_from_db is None:
                # No existing session; either raise an error.
                logger.debug("Session not found.")
                flask_session.clear()
                raise SessionNotFound()

        # We have a session! Let's initialize this.
        super(Session, self).__init__(session_from_db["data"])

        self.id = str(session_from_db["_id"])
        self.expires_at = session_from_db["_expires_at"]
        self.is_authed = session_from_db["is_authed"]

        flask_session["session_id"] = self.id
        flask_session["expires_at"] = int(self.expires_at.timestamp())

    def __setitem__(self, key, value):
        super(Session, self).__setitem__(key, value)
        result = get_db().set_session(self, self.id)
        if result is None:
            raise SessionExpired()

    @property
    def has_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at


def get_session():
    return Session(create_new=False)


def create_session(initial_data: dict = None, is_authed=False):
    return Session(initial_data=initial_data, is_authed=is_authed, create_new=True)


class EloquaOAuth2Session(OAuth2Session):
    def __init__(self, auto_refresh_auth=None, **kwargs):
        super().__init__(**kwargs)
        self.auto_refresh_auth = auto_refresh_auth

    def refresh_token(self, token_url, *args, **kwargs):
        if self.auto_refresh_auth is not None and kwargs.get("auth") is None:
            kwargs["auth"] = self.auto_refresh_auth
        return super().refresh_token(token_url, *args, **kwargs)


def get_eloqua_session(install_id):
    app_id = current_app.config["CLOUD_APP_CLIENT_ID"]
    token_manager = TokenManager(app_id, install_id)

    oauth = EloquaOAuth2Session(
        client_id=app_id,
        client=WebApplicationClient(client_id=app_id),
        token_updater=token_manager,
        auto_refresh_auth=HTTPBasicAuth(app_id, current_app.config["CLOUD_APP_CLIENT_SECRET"]),
        auto_refresh_url=current_app.config["ELOQUA_ENDPOINT_TOKEN"],
        redirect_uri=get_redirect_uri(),
        token=token_manager.get()
    )

    return oauth
