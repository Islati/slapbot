from flask_caching import Cache
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrations = Migrate()
cors = CORS(supports_credentials=True)
cache = Cache()