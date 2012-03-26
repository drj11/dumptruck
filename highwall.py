import json
import sqlite3
from copy import copy
import re
import datetime

# Mappings between Python types and SQLite types
SQLITE_PYTHON_TYPE_MAP={
  u"text": unicode,
  u"integer": int,
  u"bool": bool,
  u"real": float,
  u"date": datetime.date,
  u"datetime": datetime.datetime,
  #u"null": ??
  #BLOB: ??? The value is a blob of data, stored exactly as it was input.
}

PYTHON_SQLITE_TYPE_MAP={
  unicode: u"text",
  str: u"text",

  int: u"integer",
  long: u"integer",
  bool: u"boolean",

  float: u"real",
  datetime.date: u"date",
  datetime.datetime: u"datetime",
}

# Only for compatibility with scraperwiki;
# we should use the SQLite names
SWVARIABLES_PYTHON_TYPE_MAP={
  u"float": float
}

class Highwall:
  "A relaxing interface to SQLite"

  def __init__(self, dbname = "highwall.db", vars_table = "_highwallvars", auto_commit = True):
    pass
    # Should database changes be committed automatically after each command?
    if type(auto_commit) != bool:
      raise TypeError("auto_commit must be True or False.")
    else:
      self.auto_commit = auto_commit

    # Database connection
    if type(dbname) not in [unicode, str]:
      raise TypeError("dbname must be a string")
    else:
      self.connection=sqlite3.connect(dbname)
      self.cursor=self.connection.cursor()

    # Make sure it's a good table name
    if type(vars_table) not in [unicode, str]:
      raise TypeError("vars_table must be a string")
    else:
      self.__vars_table = vars_table

  def __check_or_create_table(self, table_name, startdata):
    for k, v in startdata.items():
      if v != None:
        break
    print k,v

    if self.__is_table(table_name):
      pass #Do something
    else:
      # This is vulnerable to injection.
      self.cursor.execute("""
        CREATE TABLE `%s` (
          `%s` %s
        );""" % (table_name, k, PYTHON_SQLITE_TYPE_MAP[type(startdata[k])]))
      self.connection.commit()

  def __check_or_create_vars_table(self):
    if self.__vars_table in self.show_tables():
      pass #Do something
    else:
      self.__is_table(self.__vars_table)
      # This is vulnerable to injection.
      self.cursor.execute("""
        CREATE TABLE `%s` (
          name TEXT,
          value_blob BLOB,
          type TEXT
        );""" % self.__vars_table)
      self.connection.commit()

  def execute(self, sql, *args, **kwargs):
    """
    Run raw SQL on the database, and receive relaxing output.
    This is sort of the foundational method that most of the
    others build on.
    """
    self.cursor.execute(sql, *args)
    rows =self.cursor.fetchall()

    if 'commit' in kwargs and kwargs['commit']:
      self.commit()

    if None == self.cursor.description:
      return None
    else:
      colnames = [d[0] for d in self.cursor.description] 
      return [dict(zip(colnames,row)) for row in rows]

  def commit(self):
    "Commit database transactions."
    return self.connection.commit()

  def close(self):
    return self.connection.close()

  def create_unique_index(table_name, columns):
    self.create_index(table_name, columns, unique = True)

  def create_index(table_name, columns, unique = False):
    "Create a unique index on the column(s) passed."
    index_name = table_name + '__' + '_'.join(columns)
    arbitrary_number = 0
    while True:
      try:
        # This is vulnerable to injection.
        if unique:
          sql = "CREATE UNIQUE INDEX ? ON [%s] ([%s])"
        else:
          sql = "CREATE INDEX ? ON [%s] ([%s])"
        self.execute(sql % (table_name, '],['.join(columns)), index_name+str(arbitrary_number))
      except:
        arbitrary_number += 1

  def __add_column(self, table_name, column_name, column_type):
    # This is vulnerable to injection.
    sql = 'ALTER TABLE `%s` ADD COLUMN %s %s ' % (table_name, column_name, column_type)
    self.execute(sql, commit = True)

  def __column_types(self, table_name):
    # This is vulnerable to injection.
    self.cursor.execute("PRAGMA table_info(`%s`)" % table_name)
    return {column[1]:column[2] for column in self.cursor.fetchall()}

  def __is_table(self,table_name):
    return table_name in self.show_tables()

  def __check_and_add_columns(self, table_name, conved_data_row):
    column_types = self.__column_types(table_name)
    for key,value in conved_data_row.items():
      if key not in column_types:
        #raise NotImplementedError("Pretend this alters the table to add the column.")
        self.__add_column(table_name, key, PYTHON_SQLITE_TYPE_MAP[type(value)])

  def __cast_data_to_column_type(self, data):
    column_types = self.__column_types(table_name)
    for key,value in data.items():
      if SQLITE_TYPE_MAP[type(key)] != column_types[key]:
        try:
          data[key] = type(key)(value)
        except ValueError:
          raise TypeError("Data could not be converted to match the existing `%s` column type.")

  def insert(self, data, table_name, commit = True):

    # Allow single rows to be dictionaries.
    if type(data)==dict:
      data = [data]

    # http://stackoverflow.com/questions/1952464/
    # in-python-how-do-i-determine-if-a-variable-is-iterable
    try:
      set([ type(e) for e in data])==set([dict])
    except TypeError:
      raise TypeError('The data argument must be a dict or an iterable of dicts.')

    self.__check_or_create_table(table_name, data[0])

    conved_data = [DataDump(row).dump() for row in data]
    for row in conved_data:
      self.__check_and_add_columns(table_name, row)
    
    # .keys() and .items() are in the same order
    # http://www.python.org/dev/peps/pep-3106/
    for row in conved_data:
      question_marks = ','.join('?'*len(row.keys()))
      # This is vulnerable to injection.
      sql = "INSERT INTO [%s] ([%s]) VALUES (%s);" % (table_name, '],['.join(row.keys()), question_marks)
      self.execute(sql, row.values(), commit=False)
    self.commit()

  def get_var(self, key):
    "Retrieve one saved variable from the database."
    # This is vulnerable to injection.
    data = self.execute("SELECT * FROM `%s` WHERE `name` = ?" % self.__vars_table, [key], commit = False)
    if data == []:
      raise NameError("The Highwall variables table doesn't have a value for %s." % key)
    else:
      row = data[0]
      if SQLITE_PYTHON_TYPE_MAP.has_key(row['type']):
        cast = SQLITE_PYTHON_TYPE_MAP[row['type']]
      elif SWVARIABLES_PYTHON_TYPE_MAP.has_key(row['type']):
        cast = SWVARIABLES_PYTHON_TYPE_MAP[row['type']]
      else:
        raise TypeError("A Python type for '%s' could not be found." % row['type'])
      return cast(row['value_blob'])

  def save_var(self, key, value, commit = True):
    "Save one variable to the database."

    # Check whether Highwall's variables table exists
    self.__check_or_create_vars_table()

    # Prepare for save
    valuetype = PYTHON_SQLITE_TYPE_MAP[type(value)]
    #valuetype in ("json", "unicode", "str", &c)
    data = {"name":key, "value_blob":value, "type":valuetype}

    return self.insert(data, self.__vars_table, commit = commit)

  def show_tables(self):
    result = self.execute("SELECT name FROM sqlite_master WHERE TYPE='table'", commit = False)
    return set([row['name'] for row in result])

  def drop(self, table_name, commit = True):
    # This is vulnerable to injection.
    return self.execute('DROP IF EXISTS `%s`;' % table_name, commit = commit)

class DataDump:
  "A data dictionary converter"
  def __init__(self, data):
    self.raw = data

  def dump(self):
    self.data = copy(self.raw)
    self.__remove_null()
    self.__checkdata()
    self.__jsonify()
    self.__convdata()
    return self.data

  def __remove_null(self):
    for key, value in self.data.items():
      if value == None:
        del(self.data[key])

  def __jsonify(self):
    for key, value in self.data.items():
      if type(value)==set:
        # Convert sets to dicts
        self.data[key] = dict(zip( list(value), [None]*len(value) ))

      if type(value) in (list, dict):
        try:
          value = dumps(value)
        except TypeError:
          raise TypeError("The value for %s is a complex object that could not be dumped to JSON.")

  def __checkdata(self):
    #Based on scraperlibs
    for key in self.data.keys():
      if not key:
        raise ValueError('key must not be blank')
      elif type(key) not in (unicode, str):
        raise ValueError('key must be string type')
      elif not re.match("[a-zA-Z0-9_\- ]+$", key):
        raise ValueError('key must be simple text')
      elif key[0] == '[' and key[-1] == ']':
        #Remove the brackets so we can add them back later.
        self.data[key[1:-1]] = self.data[key]
        del(self.data[key])

  def __convdata(self):
    #Based on scraperlibs
    jdata = {}
    for key, value in self.data.items():
      if type(value) == datetime.date:
        value = value.isoformat()
      elif type(value) == datetime.datetime:
        if value.tzinfo is None:
          value = value.isoformat()
        else:
          value = value.astimezone(pytz.timezone('UTC')).isoformat()
          assert "+00:00" in value
          value = value.replace("+00:00", "")
      elif value == None:
        pass
      elif type(value) == str:
        try:
          value = value.decode("utf-8")
        except:
          raise UnicodeEncodeError("Binary strings must be utf-8 encoded")
      elif type(value) not in [int, bool, float, unicode, str]:
        value = unicode(value)
      jdata[key] = value
    self.data = jdata
