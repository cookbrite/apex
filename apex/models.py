from cryptacular.bcrypt import BCRYPTPasswordManager
import transaction

from pyramid.security import authenticated_userid
from pyramid.threadlocal import get_current_request
from pyramid.threadlocal import get_current_registry
from pyramid.util import DottedNameResolver

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Table
from sqlalchemy import Unicode
from sqlalchemy import types
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref
from sqlalchemy.orm import relation
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import synonym
from sqlalchemy.sql import functions

from velruse.store.sqlstore import SQLBase

from zope.sqlalchemy import ZopeTransactionExtension 

from apex.lib.db import get_or_create

DBSession = scoped_session(sessionmaker(extension=ZopeTransactionExtension()))
Base = declarative_base()

user_group_table = Table('auth_user_groups', Base.metadata,
    Column('user_id', types.BigInteger(), \
        ForeignKey('auth_users.id', onupdate='CASCADE', ondelete='CASCADE')),
    Column('group_id', types.BigInteger(), \
        ForeignKey('auth_groups.id', onupdate='CASCADE', ondelete='CASCADE'))
)

class AuthGroup(Base):
    """ AuthGroup
    """
    __tablename__ = 'auth_groups'
    __table_args__ = {"sqlite_autoincrement": True}
    
    id = Column(types.BigInteger(), primary_key=True)
    name = Column(Unicode(80), unique=True, nullable=False)
    description = Column(Unicode(255), default=u'')

    users = relation('AuthUser', secondary=user_group_table, \
                     backref='auth_groups')

    def __repr__(self):
        return u'%s' % self.name

    def __unicode__(self):
        return self.name
    

class AuthUser(Base):
    """ AuthUser
    """
    __tablename__ = 'auth_users'
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(types.BigInteger(), primary_key=True)
    login = Column(Unicode(80), default=u'', index=True)
    username = Column(Unicode(80), default=u'', index=True)
    _password = Column('password', Unicode(80), default=u'', index=True)
    email = Column(Unicode(80), default=u'', index=True)
    active = Column(Unicode(1), default=u'Y')
    """ Yes, No, Disabled
    """

    groups = relation('AuthGroup', secondary=user_group_table, \
                      backref='auth_users')
    """
    Fix this to use association_proxy
    groups = association_proxy('user_group_table', 'authgroup')
    """

    def _set_password(self, password):
        self._password = BCRYPTPasswordManager().encode(password, rounds=12)

    def _get_password(self):
        return self._password

    password = synonym('_password', descriptor=property(_get_password, \
                       _set_password))

    def in_group(self, group):
        for g in self.groups:
            if g.name == group:
                return True
            else:
                return False

    @classmethod
    def get_by_id(cls, id):
        """ 
        Returns AuthUser object or None by id

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser().get_by_id(1)
        """
        return DBSession.query(cls).filter(cls.id==id).first()    

    @classmethod
    def get_by_login(cls, login):
        """ 
        Returns AuthUser object or None by login

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser().get_by_login('$G$1023001')
        """
        return DBSession.query(cls).filter(cls.login==login).first()

    @classmethod
    def get_by_username(cls, username):
        """ 
        Returns AuthUser object or None by username

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser().get_by_id('username')
        """
        return DBSession.query(cls).filter(cls.username==username).first()

    @classmethod
    def get_by_email(cls, email):
        """ 
        Returns AuthUser object or None by email

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser().get_by_id('email@address.com')
        """
        return DBSession.query(cls).filter(cls.email==email).first()

    @classmethod
    def check_password(cls, **kwargs):
        if kwargs.has_key('id'):
            user = cls.get_by_id(kwargs['id'])
        if kwargs.has_key('username'):
            user = cls.get_by_username(kwargs['username'])

        if not user:
            return False
        if BCRYPTPasswordManager().check(user.password, kwargs['password']):
            return True
        else:
            return False

    @classmethod   
    def get_profile(cls, request=None):
        """
        Returns AuthUser.profile object

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser().get_profile(MyClass, request)
        """
        if not request:
            request = get_current_request()

        if authenticated_userid(request):
            auth_profile = request.registry.settings.get('apex.auth_profile')
            if auth_profile:
                resolver = DottedNameResolver(auth_profile.split('.')[0])
                profile_cls = resolver.resolve(auth_profile)
                return get_or_create(DBSession, profile_cls, user_id=authenticated_userid(request))

def populate(settings):
    session = DBSession()
    
    default_groups = []
    if settings.has_key('apex.default_groups'):
        for name in settings['apex.default_groups'].split(','):
            default_groups.append((name.strip(),u''))
    else:
        default_groups = [(u'users',u'User Group'), \
                          (u'admin',u'Admin Group')]
    for name, description in default_groups:
        group = AuthGroup(name=name, description=description)
        session.add(group)

    session.flush()
    transaction.commit()

def initialize_sql(engine, settings):
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine
    Base.metadata.create_all(engine)
    SQLBase.metadata.bind = engine
    SQLBase.metadata.create_all(engine)
    try:
        populate(settings)
    except IntegrityError:
        transaction.abort()
