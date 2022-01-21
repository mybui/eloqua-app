import logging
from abc import ABC, abstractmethod
from typing import Tuple

from flask import request, current_app, redirect, Blueprint
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session

from .common import BaseEloquaView
from ..database import get_db
from ..auth import OAuth2State, TokenManager, get_redirect_uri

logger = logging.getLogger(__name__)


class BaseOAuthCallbackView(BaseEloquaView, ABC):
    methods = ["GET"]

    @abstractmethod
    def before_redirect(self, *args, **kwargs):
        pass

    @property
    def default_response(self) -> Tuple[str, int]:
        # Not used, so the default response doesn't actually matter in this case.
        return "", 500

    def dispatch_request(self, *args, **kwargs):
        # TODO if error=access_denied -> do something
        # Parse the state
        state = OAuth2State.from_str(request.args["state"])

        # Get session data using the session_id provided by the state.
        session_ = get_db().get_session(state.session_id)
        if session_ is None:
            return "Session expired", 400

        app_id = current_app.config["CLOUD_APP_CLIENT_ID"]
        redirect_url = session_["data"]["redirect_url"]
        install_id = session_["data"]["install_id"]
        token_manager = TokenManager(app_id=app_id, install_id=install_id)

        # Fetch the token.
        oauth = OAuth2Session(current_app.config["CLOUD_APP_CLIENT_ID"], state=state.to_str(),
                              redirect_uri=get_redirect_uri(),
                              token_updater=token_manager)
        token = oauth.fetch_token(current_app.config["ELOQUA_ENDPOINT_TOKEN"],
                                  auth=HTTPBasicAuth(current_app.config["CLOUD_APP_CLIENT_ID"],
                                                     current_app.config["CLOUD_APP_CLIENT_SECRET"]),
                                  authorization_response=request.url.replace("http://", "https://"))

        # Need to explicitly save the token to the database; fetch_token doesn't update the token automatically.
        token_manager.set(token)

        # Get the base URL for the installation.
        # TODO create a defaults file for default values, like the id endpoint
        r_json = oauth.get(current_app.config["ELOQUA_ENDPOINT_ID"]).json()
        get_db().update_installation(app_id=current_app.config["CLOUD_APP_CLIENT_ID"], install_id=install_id,
                                     data={"base_url": r_json["urls"]["base"]})

        self.before_redirect(*args, **kwargs)

        return redirect(redirect_url)


class DefaultOAuthCallbackView(BaseOAuthCallbackView):
    default_name = "oauth_callback"
    default_url_rule = "/callback"

    def before_redirect(self, *args, **kwargs):
        # NOP
        pass


bp = Blueprint("eloqua_oauth", __name__, url_prefix="/eloqua/oauth")
DefaultOAuthCallbackView.add_url_rule_to(bp)
