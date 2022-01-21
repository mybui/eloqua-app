import logging

from flask import Blueprint, current_app, request, redirect, abort
from requests_oauthlib import OAuth2Session

from ..database import get_db
from ..decorators import validate_oauth_signature, required_args
from ..auth import get_redirect_uri, OAuth2State

logger = logging.getLogger(__name__)

bp = Blueprint("eloqua_lifecycle", __name__, url_prefix="/eloqua/lifecycle")


@bp.route("/install", methods=["POST"])
@validate_oauth_signature
@required_args(["install_id", "callback_url", "app_id", "site_id"])
def lifecycle_install():
    logger.info("Installing")
    oauth = OAuth2Session(client_id=current_app.config["CLOUD_APP_CLIENT_ID"],
                          redirect_uri=get_redirect_uri())
    session_id = get_db().set_session({"install_id": request.args["install_id"],
                                             "redirect_url": request.args["callback_url"]},
                                      expires_in=300)

    data = {k: v for k, v in request.args.items() if "oauth_" not in k and "callback_url" not in k}
    get_db().upsert_installation({"_name": current_app.config["CLOUD_APP_FRIENDLY_NAME"], **data})

    state = OAuth2State(session_id=session_id["_id"])
    auth_url, state = oauth.authorization_url(current_app.config["ELOQUA_ENDPOINT_AUTH"], state=state.to_str())

    return redirect(auth_url)


@bp.route("/uninstall", methods=["POST"])
@validate_oauth_signature
def lifecycle_uninstall():
    logger.info("Uninstalling")
    deleted = get_db().delete_installation(app_id=request.args["app_id"], install_id=request.args["install_id"])
    if not deleted:
        abort(400)

    return "Uninstalled", 204


@bp.route("/status", methods=["GET"])
@validate_oauth_signature
def lifecycle_status():
    return "OK", 200
