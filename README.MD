# Qondor Integration

Add participants to Qondor projects

## Deployment to server

Create a site for the project in your server and upload the project there.

Once done, create a virtual environment for the project, for example:

```
# Use whatever Python version you want, >=3.7 is recommended.
$ python3.7 -m venv /path/to/new/virtual/environment
```

Activate the virtual environment with:
```
$ source /path/to/new/virtual/environment/bin/activate
```

Run the Flask app with gunicorn, for example:

```
# Change the port number
$ FLASK_CONFIG=production FLASK_ENV=production SERVER_NAME=visma_qondor_integration.isotammi.fi gunicorn -w 4 -b localhost:<port_number> "qondor_integration_app:create_app()"
```

Creating a script for running gunicorn (e.g. `run_gunicorn`) is recommended so anyone can  run the app without too 
much difficulty.


### Default URLs and routes

#### Lifecycle Setup

| Step       | Route | URL 
| ---------- | ----- | ---
| Enable     | `/eloqua/lifecycle/install` |`https://visma_qondor_integration.isotammi.fi/eloqua/lifecycle/install?install_id={InstallId}&site_name={SiteName}&site_id={SiteId}&app_id={AppId}&callback_url={CallbackUrl}` |
| Configure  | *None* | *None*
| Status     | `/eloqua/lifecycle/status` |`https://visma_qondor_integration.isotammi.fi/eloqua/lifecycle/status`
| Uninstall  | `/eloqua/lifecycle/uninstall` |`https://visma_qondor_integration.isotammi.fi/eloqua/lifecycle/uninstall?install_id={InstallId}&app_id={AppId}`


#### Authentication to Eloqua

| Step           | Route | URL 
| -------------- | ----- | ---
| OAuth Callback | `/eloqua/oauth/callback` |`https://visma_qondor_integration.isotammi.fi/eloqua/oauth/callback`


## Authors

Current author: [My Bui](my.bui.fi@gmail.com)


