import os
from flask import Flask
from . import about, auth, contact, learn, main, nmr, plot


def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        ALLOWED_EXTENSIONS = {"zip"},
        SECRET_KEY = "dev",
        UPLOAD_FOLDER = os.path.join(app.instance_path, "uploads"),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    app.register_blueprint(about.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(contact.bp)
    app.register_blueprint(learn.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(nmr.bp)
    app.register_blueprint(plot.bp)

    return app 