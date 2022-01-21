import logging

from flask import url_for
from oauthlib.common import generate_token

from .database import get_db

logger = logging.getLogger(__name__)


class TokenManager:
    def __init__(self, app_id, install_id, token=None):
        self._app_id = app_id
        self._install_id = install_id
        self._token = token

    def __call__(self, token):
        get_db().set_token(self._app_id, self._install_id, token=token)
        self._token = token

    def set(self, token):
        self(token)

    def get(self):
        if self._token is None:
            self._token = get_db().get_token(self._app_id, self._install_id)

        return self._token


# TODO Decouple this. This is required, but the actual url isn't used in anything else than the initial
#  authentication process.
def get_redirect_uri():
    return url_for("eloqua_oauth.oauth_callback", _external=True, _scheme="https")


class OAuth2State:
    def __init__(self, session_id, token=None):
        self.session_id = session_id
        self.token = token or generate_token()

    def to_str(self):
        return "{}.{}".format(self.session_id, self.token)

    @staticmethod
    def from_str(v: str):
        if not isinstance(v, str):
            raise ValueError("Must be a string")
        split = v.split(".")
        return OAuth2State(session_id=split[0], token=split[1])
