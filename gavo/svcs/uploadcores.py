"""
Cores to alter the DB state from the Web.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import grp
import os

from gavo import base
from gavo import rsc
from gavo.svcs import core


MS = base.makeStruct

uploadOutputDef = """<outputTable>
					<column name="nAffected" type="integer" 
						tablehead="Number touched" required="True"/>
				</outputTable>"""


class UploadCore(core.Core):
	"""A core handling uploads of files to the database.

	It allows users to upload individual files into a special staging
	area (taken from the stagingDir property of the destination data descriptor)
	and causes these files to be parsed using destDD.  Note that destDD
	*must* have ``updating="True"`` for this to work properly (it will otherwise
	drop the table on each update).  If uploads are the only way updates
	into the table occur, source management is not necessary for these, though.

	You can tell UploadCores to either insert or update the incoming data using
	the "mode" input key.
	"""
	name_ = "uploadCore"

	_destDD = base.ReferenceAttribute("destDD", default=base.Undefined,
		description="Reference to the data we are uploading into. The"
			" destination must be an updating data descriptor.")

	inputTableXML = """
		<inputTable id="inFields">
			<inputKey name="File" type="file" required="True"
				tablehead="Source to upload"/>
			<inputKey name="Mode" type="text" tablehead="Upload mode" 
				required="True" multiplicity="forced-single">
				<values default="i">
					<option title="Insert">i</option>
					<option title="Update">u</option>
				</values>
			</inputKey>
		</inputTable>
		"""
	outputTableXML = uploadOutputDef

	def _fixPermissions(self, fName):
		"""tries to chmod the newly created file to 0664 and change the group
		to config.gavoGroup.
		"""
		try:
			os.chmod(fName, 0664)
			os.chown(fName, -1, grp.getgrnam(base.getConfig("gavoGroup"))[2])
		except (KeyError, os.error):  # let someone else worry about it
			pass

	def _writeFile(self, srcFile, fName):
		"""writes the contents of srcFile to fName in destDD's staging dir.
		"""
		try:
			targetDir = os.path.join(self.rd.resdir, 
				self.destDD.getProperty("stagingDir"))
		except KeyError:
			raise base.ui.logOldExc(base.ValidationError("Uploading is only"
				" supported for data having a staging directory.", "File"))
		if not os.path.exists(targetDir):
			raise base.ValidationError("Staging directory does not exist.",
				"File")
		targetFName = fName.split("/")[-1].encode("iso-8859-1")
		if not targetFName:
			raise base.ValidationError("Bad file name", "File")
		targetPath = os.path.join(targetDir, targetFName)

		with open(targetPath, "w") as f:
			f.write(srcFile.read())

		try:
			self._fixPermissions(targetPath)
		except os.error:
			# Nothing we can do, and it may not even hurt
			pass
		return targetPath

	def _importData(self, sourcePath, mode):
		"""parses the input file at sourcePath and writes the result to the DB.
		"""
		base.ui.notifyInfo("Web upload ingesting %s in %s mode"%(sourcePath, mode))
		try:
			parseOptions = rsc.getParseOptions(
				validateRows=True, 
				doTableUpdates=mode=="u")
			with base.getWritableAdminConn() as conn:
				res = rsc.makeData(self.destDD, parseOptions=parseOptions, 
					forceSource=sourcePath, connection=conn)
		except Exception, msg:
			raise base.ui.logOldExc(base.ValidationError("Cannot enter %s in"
				" database: %s"%(os.path.basename(sourcePath), str(msg)), "File"))
		return res.nAffected

	def _saveData(self, srcFile, fName, mode):
		"""saves data read from srcFile to both fNames staging dir and to the
		database table(s) described by destDD.

		mode can be "u" (for update) or "i" for insert.

		If parsing or the database operations fail, the saved file will be removed.
		Errors will ususally be base.ValidationErrors on either File or Mode.

		The function returns the number of items modified.
		"""
		targetPath = self._writeFile(srcFile, fName)
		try:
			nAffected = self._importData(targetPath, mode)
		except:
			os.unlink(targetPath)
			raise
		return nAffected

	def run(self, service, inputTable, queryMeta):
		totalAffected = 0
		fName, srcFile = inputTable.getParam("File")
		mode = inputTable.getParam("Mode")
		totalAffected += self._saveData(srcFile, fName, mode)
		return rsc.TableForDef(self.outputTable, 
			rows=[{"nAffected": totalAffected}])
