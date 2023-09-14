# -*- coding: utf-8 -*-
"""Database module, including the SQLAlchemy database object and DB-related utilities."""
import datetime

from sqlalchemy.orm import relationship, load_only

from sqlalchemy import event, func

from slapbot.extensions import db

# Alias common SQLAlchemy names
Column = db.Column
relationship = relationship


class CRUDMixin(object):
    """Mixin that adds convenience methods for CRUD (create, read, update, delete) operations."""

    @classmethod
    def create(cls, **kwargs):
        """Create a new record and save it the database."""
        instance = cls(**kwargs)
        return instance.save()

    def update(self, commit=True, **kwargs):
        """Update specific fields of a record."""
        for attr, value in kwargs.items():
            setattr(self, attr, value)
        return commit and self.save() or self

    def save(self, commit=True):
        """Save the record."""

        try:
            db.session.add(self)
        except:
            db.session.merge(self)

        if commit:
            db.session.commit()
        return self

    def delete(self, commit=True):
        """Remove the record from the database."""
        db.session.delete(self)
        return commit and db.session.commit()


class TimeMixin(object):
    """
    Mixin that adds convenient methods to automatically handle when an object was created and last updated.
    """

    __table_args__ = {"extend_existing": True}

    created_at = db.Column("created_at", db.DateTime, nullable=False, default=datetime.datetime.utcnow())
    updated_at = db.Column('updated_at', db.DateTime, nullable=False, default=datetime.datetime.utcnow())

    @staticmethod
    def create_time(mapper, connection, instance):
        now = datetime.datetime.utcnow()
        instance.created_at = now
        instance.updated_at = now

    @staticmethod
    def update_time(mapper, connection, instance):
        now = datetime.datetime.utcnow()
        instance.updated_at = now

    @classmethod
    def register(cls):
        event.listen(cls, 'before_insert', cls.create_time)
        event.listen(cls, 'before_update', cls.update_time)

    def last_updated_within(self, days=0, hours_ago=0, minutes_ago=0) -> bool:
        """
        Whether or not the action was last performed within the specified range.
        """
        start_range = datetime.datetime.utcnow()
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=days, hours=hours_ago, minutes=minutes_ago)

        if type(self.updated_at) is str:
            updated_recently = start_range >= datetime.datetime.strptime(self.updated_at,
                                                                         '%Y-%m-%d %H:%M:%S.%f') >= days_ago
        else:
            updated_recently = start_range >= self.updated_at >= days_ago

        return updated_recently


# From Mike Bayer's "Building the app" talk
# https://speakerdeck.com/zzzeek/building-the-app
class SurrogatePK(object):
    """A mixin that adds a surrogate integer 'primary key' column named ``id`` to any declarative-mapped class."""

    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)

    @classmethod
    def get_by_id(cls, record_id):
        """Get record by ID."""
        if any(
                (isinstance(record_id, (str, bytes)) and record_id.isdigit(),
                 isinstance(record_id, (int, float))),
        ):
            return cls.query.get(int(record_id))
        return None


class SqlModel(CRUDMixin, db.Model):
    """Base model class that includes CRUD convenience methods."""

    __abstract__ = True

    def __init__(self, **kwargs):
        db.Model.__init__(
            self,
            **kwargs
        )
        if hasattr(self, 'register'):
            self.register()

    @classmethod
    def get_or_create(cls, **kwargs):
        instance = cls.query.filter_by(**kwargs).first()
        if instance:
            return instance
        else:
            instance = cls(**kwargs)
            db.session.add(instance)
            db.session.commit()
            return instance

    @classmethod
    def get_random(cls):
        try:
            total_count = db.session.query(func.count(cls.id)).scalar_subquery()

            return cls.query.options(load_only(getattr(cls, 'id'))).offset(
                func.floor(
                    func.random() *
                    total_count
                )).limit(1).first()
        except:
            return cls.query.first()


def foreign_key(tablename, nullable=False, pk_name='id', **kwargs):
    """Column that adds primary key foreign key reference.
    Usage: ::
        category_id = reference_col('category')
        category = relationship('Category', backref='categories')
    """
    return db.Column(
        db.ForeignKey('{0}.{1}'.format(tablename, pk_name)),
        nullable=nullable, **kwargs)


def get_or_create(model, **kwargs):
    instance = db.session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    else:
        instance = model(**kwargs)
        db.session.add(instance)
        db.session.commit()
        return instance
