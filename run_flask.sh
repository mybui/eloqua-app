#!/bin/bash
source /home/mybui/apache/visma-qondor-integration.idbbn.visma-marketing-cloud.com/venv/bin/activate
FLASK_APP=visma_qondor_integration_app FLASK_ENV=development flask run --port=7022
