import logging.config

import yaml

from flask import Flask

import visma_qondor_integration_app.settings

logger = logging.getLogger(__name__)


def create_app():
    """
    Application factory for creating Flask apps.
    """
    with open(visma_qondor_integration_app.settings.LOGGING_CONFIG, "r") as f:
        global logger
        logging.config.dictConfig(yaml.safe_load(f))
        logger = logging.getLogger(__name__)
        logger.debug("Logging configured.")

    app = Flask(__name__)
    app.config.from_object("visma_qondor_integration_app.settings")
    app.logger.debug("Configured Flask app.")

    register_blueprints(app)
    return app


def register_blueprints(app):
    """
    Registers all the blueprints for the Flask application.
    """
    # Cloud app lifecycle endpoints.
    import visma_qondor_integration_app.blueprints.lifecycle
    app.register_blueprint(visma_qondor_integration_app.blueprints.lifecycle.bp)

    # Cloud app OAuth endpoints.
    import visma_qondor_integration_app.blueprints.oauth
    app.register_blueprint(visma_qondor_integration_app.blueprints.oauth.bp)

    # Cloud app ops endpoints.
    import visma_qondor_integration_app.blueprints.ops
    app.register_blueprint(visma_qondor_integration_app.blueprints.ops.bp)

    app.logger.debug("Registered blueprints.")
