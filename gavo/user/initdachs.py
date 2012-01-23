"""
Initial setup for the file system hierarchy.

This module is supposed to create as much of the DaCHS file system environment
as possible.  Take care to give sensible error messages -- much can go wrong
here, and it's nice if the user has a way to figure out what's wrong.
"""

from __future__ import with_statement

import datetime
import grp
import os
import sys
import textwrap
import warnings

import psycopg2

from gavo import base


def bailOut(msg, hint=None):
	sys.stderr.write("*** Error: %s\n\n"%msg)
	if hint is not None:
		sys.stderr.write(textwrap.fill(hint)+"\n")
	sys.exit(1)


def unindentString(s):
	return "\n".join(s.strip() for s in s.split("\n"))+"\n"


def makeRoot():
	rootDir = base.getConfig("rootDir")
	if os.path.isdir(rootDir):
		return
	try:
		os.makedirs(rootDir)
	except os.error:
		bailOut("Cannot create root directory %s."%rootDir,
			"This usually means that the current user has insufficient privileges"
			" to write to the parent directory.  To fix this, either have rootDir"
			" somewhere you can write to (edit /etc/gavorc) or create the directory"
			" as root and grant it to your user id.")


def getGroupId():
	gavoGroup = base.getConfig("group")
	try:
		return grp.getgrnam(gavoGroup)[2]
	except KeyError, ex:
		bailOut("Group %s does not exist"%str(ex),
			"You should have created this (unix) group when you created the server"
			" user (usually, 'gavo').  Just do it now and re-run this program.")


def makeDirVerbose(path, setGroupTo=None):
	if not os.path.isdir(path):
		try:
			os.makedirs(path)
		except os.error, err:
			bailOut("Could not create directory %s (%s)"%(
				path, err))  # add hints
		except Exception, msg:
			bailOut("Could not create directory %s (%s)"%(
				path, msg))
	if setGroupTo is not None:
		stats = os.stat(path)
		if stats.st_mode&0060!=060 or stats.st_gid!=setGroupTo:
			try:
				os.chown(path, -1, setGroupTo)
				os.chmod(path, stats.st_mode | 0060)
			except Exception, msg:
				bailOut("Cannot set %s to group ownership %s, group writable"%(
					path, setGroupTo),
					hint="Certain directories must be writable by multiple user ids."
					"  They must therefore belong to the group %s and be group"
					" writeable.  The attempt to make sure that's so just failed"
					" with the error message %s."
					"  Either grant the directory in question to yourself, or"
					" fix permissions manually.  If you own the directory and"
					" sill see permission errors, try 'newgrp %s'"%(
						base.getConfig("group"), msg, base.getConfig("group")))


_GAVO_WRITABLE_DIRS = set([
	"stateDir",
	"cacheDir",
	"logDir",
	"tempDir",])


def makeDirForConfig(configKey, gavoGrpId):
	path = base.getConfig(configKey)
	if configKey in _GAVO_WRITABLE_DIRS:
		makeDirVerbose(path, gavoGrpId)
	else:
		makeDirVerbose(path)


def makeDefaultMeta():
	destPath = os.path.join(base.getConfig("configDir"), "defaultmeta.txt")
	if os.path.exists(destPath):
		return
	rawData = r"""publisher: Fill Out
		publisherID: ivo://x-unregistred
		contact.name: Fill Out
		contact.address: Ordinary street address.
		contact.email: Your email address
		contact.telephone: Delete this line if you don't want to give it
		creator.name: Could be same as contact.name
		creator.logo: a URL pointing to a small png

		_noresultwarning: Your query did not match any data.

		authority.creationDate: %s
		authority.title: Untitled data center
		authority.shortname: DaCHS standin
		authority.description: This should be a relatively terse \
			description of your data center.  You must give sensible values \
			for all authority.* things before publishing your registry endpoint.
		authority.referenceURL: (your DC's "contact" page, presumably)
		authority.managingOrg: ivo://x-unregistred/org
		organization.title: Unconfigured organization
		organization.description: Briefly describe the organization you're \
			running the dc for here.
		organization.referenceURL: http://your.institution/home
		"""%(datetime.datetime.utcnow())
	with open(destPath, "w") as f:
		f.write(unindentString(rawData))
	
	# load new new default meta
	from gavo.base import config
	config.makeFallbackMeta()

def prepareWeb():
	makeDirVerbose(os.path.join(base.getConfig("webDir"), "nv_static"))


def _genPW():
	"""returns a random string that may be suitable as a database password.

	The entropy of the generated passwords should be close to 80 bits, so
	the passwords themselves would probably not be a major issue.  Of course,
	within DaCHS they are stored in the file system in clear text...
	"""
	return os.urandom(10).encode("hex")


def makeProfiles(dbname, userPrefix=""):
	"""writes profiles with made-up passwords to DaCHS' config dir.

	This will mess everything up when the users already exist.  We
	should probably provide an option to drop standard users.

	userPrefix is mainly for the test infrastructure.
	"""
	profilePath = base.getConfig("configDir")
	for fName, content in [
			("dsn", "#host = computer.doma.in\n#port = 5432\ndatabase = %s\n"%(
				dbname)),
			("feed", "include dsn\nuser = %sgavoadmin\npassword = %s\n"%(
				userPrefix, _genPW())),
			("trustedquery", "include dsn\nuser = %sgavo\npassword = %s\n"%(
				userPrefix, _genPW())),
			("untrustedquery", "include dsn\nuser = %suntrusted\npassword = %s\n"%(
				userPrefix, _genPW())),]:
		destPath = os.path.join(profilePath, fName)
		if not os.path.exists(destPath):
			with open(destPath, "w") as f:
				f.write(content)


def createFSHierarchy(dbname, userPrefix=""):
	"""creates the directories required by DaCHS.

	userPrefix is for use of the test infrastructure.
	"""
	makeRoot()
	grpId = getGroupId()
	for configKey in ["configDir", "inputsDir", "cacheDir", "logDir", 
			"tempDir", "webDir", "stateDir"]:
		makeDirForConfig(configKey, grpId)
	makeDirVerbose(os.path.join(base.getConfig("inputsDir"), "__system"))
	makeDefaultMeta()
	makeProfiles(dbname, userPrefix)
	prepareWeb()


###################### DB interface
# This doesn't use much of sqlsupport since the roles are just being
# created and some of the operations may not be available for non-supervisors.

def _execDB(conn, query, args={}):
	"""returns the result of running query with args through conn.

	No transaction management is being done here.
	"""
	cursor = conn.cursor()
	cursor.execute(query, args)
	return list(cursor)


def _roleExists(conn, roleName):
	return _execDB(conn, 
		"SELECT rolname FROM pg_roles WHERE rolname=%(rolname)s",
		{"rolname": roleName})


def _createRoleFromProfile(conn, profile, privileges):
	cursor = conn.cursor()
	try:
		verb = "CREATE"
		if _roleExists(conn, profile.user):
			verb = "ALTER"
		cursor.execute(
			"%s ROLE %s PASSWORD %%(password)s %s LOGIN"%(
				verb, profile.user, privileges), {
			"password": profile.password,})
		conn.commit()
	except:
		warnings.warn("Could not create role %s (see db server log)"%
			profile.user)
		conn.rollback()
		

def _createRoles(dbname):
	"""creates the roles for the DaCHS profiles admin, trustedquery
	and untrustedquery.
	"""
	from gavo.base import config

	conn = psycopg2.connect("dbname=%s"%dbname)
	for profileName, privileges in [
			("admin", "CREATEROLE"),
			("trustedquery", ""),
			("untrustedquery", "")]:
		_createRoleFromProfile(conn, 
			config.getDBProfileByName(profileName),
			privileges)

	adminProfile = config.getDBProfileByName("admin")
	cursor = conn.cursor()
	cursor.execute("GRANT ALL ON DATABASE %s TO %s"%(dbname, adminProfile.user))
	conn.commit()


def _getServerScriptPath(conn):
	"""returns the path where a local postgres server would store its
	contrib scripts.

	This is probably Debian specific.  It's used by the the extension
	script upload.
	"""
	from gavo.base import sqlsupport
	version = sqlsupport.parseBannerString(
		_execDB(conn, "SELECT version()")[0][0])
	return "/usr/share/postgresql/%s/contrib"%version


def _readDBScript(conn, scriptPath, sourceName, procName):
	"""tries to execute the sql script in scriptPath within conn.

	sourceName is some user-targeted indicator what package the script
	comes from, procName the name of a procedure left by the script
	so we don't run the script again when it's already run.
	"""
	if not os.path.exists(scriptPath):
		warnings.warn("SQL script file for %s not found.  There are many"
			" reasons why that may be ok, but unless you know what you are"
			" doing, you probably should install the corresponding postgres"
			" extension.")
	from gavo.rscdef import scripting

	cursor = conn.cursor()
	if _execDB(conn, "SELECT * FROM pg_proc WHERE proname=%(procName)s",
			{"procName": procName}):
		# script has already run
		return

	try:
		for statement in scripting.getSQLScriptGrammar().parseString(
				open(scriptPath).read()):
			cursor.execute(statement)
	except:
		import traceback
		traceback.print_exc()
		conn.rollback()
		warnings.warn("SQL script file %s failed.  Try running manually"
			" using psql.  While it hasn't run, the %s extension is not"
			" available."%(scriptPath, sourceName))
	else:
		conn.commit()


def _readDBScripts(dbname):
	"""loads definitions of pgsphere, q3c and similar into the DB.

	This only works for local installations, and the script location
	is more or less hardcoded for Debian.
	"""
	conn = psycopg2.connect("dbname=%s"%dbname)
	scriptPath = _getServerScriptPath(conn)
	for extScript, pkgName, procName in [
			("pg_sphere.sql", "pgSphere", "spoint_in"),
			("q3c.sql", "q3c", "q3c_ang2ipix")]:
		_readDBScript(conn, 
			os.path.join(scriptPath, extScript), 
			pkgName,
			procName)


def _importBasicResources():
	from gavo import rsc
	from gavo.user import importing

	for rdId in ["//dc_tables", "//services", "//users", 
			"//uws", "//tap", "//products", "//obscore"]:
		base.ui.notifyInfo("Importing %s"%rdId)
		importing.process(rsc.getParseOptions(), [rdId])

	# publish //services so at least the authority has a record
	# (we want that at least for unit tests).
	from gavo.registry import publication
	publication.updateServiceList([base.caches.getRD("//services")])


def initDB(dbname):
	"""creates users and tables expected by DaCHS in dbname.

	The current user must be superuser on dbname.
	"""
	_createRoles(dbname)
	_readDBScripts(dbname)
	_importBasicResources()


def parseCommandLine():
	from gavo.imp import argparse
	parser = argparse.ArgumentParser(description="Create or update DaCHS'"
		" file system and database environment.")
	parser.add_argument("-d", "--dbname", help="Name of the database"
		" holding DaCHS' tables (the current user must be superuser on it.",
		action="store", type=str, dest="dbname", default="gavo")
	parser.add_argument("--nodb", help="Inhibit initialization of the"
		" database.  This may be necessary if your database server is"
		" remote.", action="store_false", dest="initDB")
	return parser.parse_args()


def main():
	opts = parseCommandLine()
	createFSHierarchy(opts.dbname)
	if opts.initDB:
		initDB(opts.dbname)
