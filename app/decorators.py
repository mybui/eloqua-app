import hashlib
import hmac
import logging
import time
from base64 import b64encode
from functools import wraps
from urllib.parse import quote_plus, quote

from flask import current_app, abort, request, jsonify

from .database import get_db
from .session import create_session

logger = logging.getLogger(__name__)


def require_dev(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        if current_app.env == "development":
            return f(*args, **kwargs)
        else:
            abort(404)

    return decorator


def required_args(keys):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            missing_keys = [key for key in keys if request.args.get(key) is None]
            if len(missing_keys) == 0:
                return f(*args, **kwargs)
            else:
                return jsonify(
                    {
                        "errors": [
                            {"message": "Missing argument '{}'".format(missing_key)} for missing_key in missing_keys
                        ]
                    }
                ), 400

        return decorated_function

    return decorator


def require_authed_session(_func=None, *, methods=None):
    def decorator(f):
        @wraps(f)
        def wrapper_decorator(*args, **kwargs):
            # Do nothing if methods isn't None or isn't listed in methods
            if methods is not None and request.method not in methods:
                return f(*args, **kwargs)

            # This should raise an exception if the session doesn't exist.
            session = create_session(is_authed=True)

            if session.is_authed:
                return f(*args, **kwargs)
            else:
                logger.debug("Session is not authed.")
                abort(401)

        return wrapper_decorator

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def validate_oauth_signature(_func=None, *, methods=None, create_new_session=False):
    def decorator(f):
        @wraps(f)
        def wrapper_decorator(*args, **kwargs):
            # Do nothing if methods isn't None or isn't listed in methods
            if methods is not None and request.method not in methods:
                return f(*args, **kwargs)

            if _oauth_is_signature_valid():
                logger.debug("OAuth signature was valid.")
                get_db().save_to_cache({
                    "oauth_nonce": request.args.get("oauth_nonce"),
                    "oauth_timestamp": request.args.get("oauth_timestamp")
                })

                if create_new_session:
                    create_session(is_authed=True)
                return f(*args, **kwargs)
            else:
                logger.warning("OAuth signature was invalid.")
                abort(401)

        return wrapper_decorator

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def _oauth_is_signature_valid():
    oauth_consumer_key = request.args.get("oauth_consumer_key")
    oauth_nonce = request.args.get("oauth_nonce")
    oauth_timestamp = request.args.get("oauth_timestamp")
    oauth_signature = request.args.get("oauth_signature")

    def has_duplicates_in_cache():
        return get_db().find_one_from_cache({
            "oauth_nonce": oauth_nonce,
            "oauth_timestamp": oauth_timestamp
        }) is not None

    def generate_signature():
        logger.debug("Generating signature...")
        # Contruct signature validation based on Eloqua documentation
        # We need to construct message to be hashed from request object
        # More detail can be found from:
        # https://docs.oracle.com/cloud/latest/marketingcs_gs/OMCAB/index.html#Developers/GettingStarted/Authentication/validating-a-call-signature.htm

        # Explanation time!
        # The signature message consists of three chunks, divided by an ampersand (&). The format is:
        # <method>&<base endpoint>&<query string parameters>
        # Each chunk is percent-encoded, so the resulting signature message should have exactly two ampersands.
        # Using a "GET https://test.com/endpoint?foo=bar&x=1&url=http%3A%2F%2Fredirect.com" request as an example,
        # the resulting signature would be:
        # GET&https%3A%2F%2Ftest.com%2Fendpoint&foo%3Dbar%26x%3D1%26url=http%253A%252F%252Fredirect.com

        # First chunk: HTTP method
        # E.g. with a "GET https://test.com/endpoint?foo=bar&x=1&url=http%3A%2F%2Fredirect.com" request the method
        # would be "GET"
        message = request.method + "&"

        # Second chunk: The URL endpoint without query string parameters, percent-encoded
        # E.g. with a "GET https://test.com/endpoint?foo=bar&x=1&url=http%3A%2F%2Fredirect.com" request the endpoint
        # would be "https://test.com/endpoint" (before encoding)
        # We use quote_plus instead of quote here because the / characters need to be encoded as well.
        # TODO Figure out why the base url is http when it should be https. Seems to relate to Flask/gunicorn?
        base_url = request.base_url.replace("http://", "https://")
        logger.debug("base_url is %s", base_url)
        message += quote_plus(base_url) + "&"

        # Third chunk: the query parameters, omitting the oauth_signature parameter, sorted alphabetically,
        # percent-encoded
        # E.g. with a "GET https://test.com/endpoint?foo=bar&x=1&url=http%3A%2F%2Ftest.com" request the query
        # parameters would be "foo=bar&x=1&url=http%3A%2F%2Fredirect.com" (before encoding)

        # Flask request object automatically decodes the arguments, so we need to encode them back again since the
        # original query string has them encoded and we need to encode the exact values given. Otherwise we get a
        # signature mismatch.
        logger.debug("Query parameters before encoding: %s", request.args.to_dict())
        query_parameters = {k: quote(v).replace("+", "%20").replace("/", "%2F") for k, v in
                            request.args.to_dict().items() if k != "oauth_signature"}
        message += quote("&".join("{}={}".format(k, v)
                                  for (k, v) in sorted(query_parameters.items())))
        message = message.encode("utf-8")
        key = current_app.config["CLOUD_APP_CLIENT_SECRET"] + "&"
        key = key.encode("utf-8")

        logger.debug("Query parameters after encoding: %s", query_parameters)
        logger.debug("Signature message before hashing: %s", message)

        hashed = hmac.digest(key, message, hashlib.sha1)

        return b64encode(hashed)

    # Check consumer key
    if oauth_consumer_key != current_app.config["CLOUD_APP_CLIENT_ID"]:
        logger.warning("OAuth signature validation failed: invalid consumer key")
        return False

    # Check if timestamp within last 5 min
    if int(time.time()) - 60 * 5 > int(oauth_timestamp):
        logger.warning("OAuth signature validation failed: invalid timestamp")
        return False

    # Check if nonce exists in cache and if not set request nonce to cache
    # with 5 min timeout
    if has_duplicates_in_cache():
        logger.warning("OAuth signature validation failed: duplicates in cache")
        return False

    # Validate oauth_signature against just created hash
    generated_signature = generate_signature()
    if oauth_signature.encode("utf-8") != generated_signature:
        logger.warning("OAuth signature validation failed: signature mismatch")
        logger.debug("Expected %s, got %s", generated_signature, oauth_signature.encode("utf-8"))
        return False

    return True
