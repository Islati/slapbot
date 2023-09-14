import contextlib

import click
from flask import Flask, Response, make_response
from sqlalchemy import MetaData

from slapbot.extensions import db, migrations, cors
from slapbot import models
from slapbot.backend import add_headers

from slapbot.backend.routes import routes


def create_app(configuration=None) -> Flask:
    app: Flask = Flask(__name__)
    app.config.from_object(configuration)
    click.secho(f"Running flask with {type(configuration)} configuration connected to {app.config['SQLALCHEMY_DATABASE_URI']}", fg='green')

    db.init_app(app=app)
    migrations.init_app(app=app, db=db)

    app.register_blueprint(routes)
    click.secho("Registered routes for API", fg='green')

    app.app_context().push()

    try:
        db.create_all()
        click.secho("Created all tables in the database.", fg='green')
    except Exception as e:
        raise

    @app.shell_context_processor
    def shell_context():
        return {
            'db': db,
            'app': app
        }

    @app.after_request
    def after_request(response: Response):
        return add_headers(response)

    click.secho("Flask Application Created", fg="green")

    return app

def destroy_database():
    meta = db.metadata

    with contextlib.closing(db.engine.connect()) as con:
        trans = con.begin()
        deleted_tables = []
        for table in reversed(meta.sorted_tables):
            con.execute(table.delete())
            deleted_tables.append(f"{table}")
        trans.commit()
        print(f"Deleted tables: {', '.join(deleted_tables)}")

def teardown_app(app: Flask):
    try:
        app.app_context().pop()
    except:
        pass
