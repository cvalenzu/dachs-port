"""
An abstract processor and some helping code.

Currently, I assume a plain text interface for those.  It might be
a good idea to use the event mechanism here.
"""

import os
import sys


from gavo import base
from gavo.helpers import anet
from gavo.helpers import fitstricks
from gavo.utils import fitstools
from gavo.utils import pyfits


class FileProcessor(object):
	"""An abstract base for a source file processor.

	Processors are constructed with an optparse XXX value that
	is later available as the attribute opts.

	You then need to define a process method receiving a source as
	returned by the dd (i.e., usually a file name).
	"""
	def __init__(self, opts, dd):
		self.opts, self.dd = opts, dd
	
	def process(self, fName):
		pass


class HeaderProcessor(FileProcessor):
	"""is an abstract processor for FITS header manipulations.

	The processor builds naked FITS headers alongside the actual files, with an
	added extension .hdr.  The presence of a FITS header indicates that a file
	has been processed.  The headers on the actual FITS files are only replaced
	if necessary.

	The basic flow is: Check if there is a header.  If not, call
	_getNewHeader(srcFile) -> hdr.  Store hdr to cache.  Insert cached
	header in the new FITS if it's not there yet.

	You have to implement the _getHeader(srcName) -> pyfits header object
	function.  It must raise an exception if it cannot come up with a
	header.  You also have to implement _isProcessed(srcName) -> boolean
	returning True if you think srcName already has a processed header.

	This basic flow is influenced by the following opts attributes:

	* reProcess -- even if a cache is present, recompute header values
	* applyHeaders -- actually replace old headers with new headers
	* reHeader -- even if _isProcessed returns True, write a new header
	* compute -- perform computations

	The idea is that you can:

	* see if stuff works without touching the original files: proc
	* write all cached headers to files that don't have them
	  proc --applyheaders --nocompute
	* after a bugfix force all headers to be regenerated:
	  proc --reprocess --applyheaders --reheader
	
	All this leads to the messy logic.  Sorry 'bout this.
	"""
	headerExt = ".hdr"

	def _makeCacheName(self, srcName):
		return srcName+self.headerExt

	def _writeCache(self, srcName, hdr):
		hdu = pyfits.PrimaryHDU(header=hdr)
		dest = self._makeCacheName(srcName)
		if os.path.exists(dest):
			os.unlink(dest)
		hdu.writeto(dest)

	def _readCache(self, srcName):
		"""returns a pyfits header object for the cached result in srcName.

		If there is no cache, None is returned.
		"""
		src = self._makeCacheName(srcName)
		if os.path.exists(src):
			hdus = pyfits.open(src)
			hdr = hdus[0].header
			hdus.close()
			return hdr

	def _makeCache(self, srcName):
		if self.opts.compute:
			self._writeCache(srcName, self._getHeader(srcName))

	# headers copied from original file rather than the cached header
	keepKeys = set(["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2",
			"EXTEND", "BZERO", "BSCALE"])
	def _fixHeaderDataKeys(self, srcName, header):
		oldHeader = self.getPrimaryHeader(srcName)
		for key in self.keepKeys:
			if oldHeader.has_key(key):
				header.update(key, oldHeader[key])

	def commentFilter(self, value):
		"""returns true if the comment value should be preserved.

		You may want to override this.
		"""
		return True
	
	def historyFilter(self, value):
		"""returns true if the history item value should be preserved.
		"""
		return True

	def _writeHeader(self, srcName, header):
		self._fixHeaderDataKeys(srcName, header)
		fitstools.sortHeaders(header, commentFilter=self.commentFilter,
			historyFilter=self.historyFilter)
		fitstools.replacePrimaryHeaderInPlace(srcName, header)

	def _isProcessed(self, srcName):
		"""override.
		"""
		return False
	
	def _getHeader(self, srcName):
		"""override.
		"""
		return pyfits.open(srcName)[0].header

	def getPrimaryHeader(self, srcName):
		"""returns the primary header of srcName.

		This is a convenience function for user derived classes.
		"""
		hdus = pyfits.open(srcName)
		hdr = hdus[0].header
		hdus.close()
		return hdr

	def process(self, srcName):
		cache = self._readCache(srcName)
		if cache is None or self.opts.reProcess:
			self._makeCache(srcName)
			cache = self._readCache(srcName)
		if not self.opts.applyHeaders:
			return
		if self.opts.reHeader or not self._isProcessed(srcName):
			self._writeHeader(srcName, cache)

	@staticmethod
	def addOptions(optParser):
		optParser.add_option("--reprocess", help="Recompute all headers",
			action="store_true", dest="reProcess", default=False)
		optParser.add_option("--no-compute", help="Only use cached headers",
			action="store_false", dest="compute", default=True)
		optParser.add_option("--apply", help="Write cached headers to"
			" source files", action="store_true", dest="applyHeaders",
			default=False)
		optParser.add_option("--reheader", help="Write cached headers"
			" to source files even if it looks like they already have"
			" been written", action="store_true", dest="reHeader",
			default=False)
		optParser.add_option("--bail", help="Bail out on a processor error,"
			" dumping a traceback", action="store_true", dest="bailOnError",
			default=False)

	def processAll(self):
		"""calls the process method of processor for all sources of the data
		descriptor dd.
		"""
		processed, ignored = 0, 0
		for source in self.dd.sources:
			try:
				self.process(source)
			except KeyboardInterrupt:
				sys.exit(2)
			except Exception, msg:
				if self.opts.bailOnError:
					raise
				sys.stderr.write("Skipping %s (%s, %s)\n"%(
					source, msg.__class__.__name__, msg))
				ignored += 1
			processed += 1
			sys.stdout.write("%6d (-%5d)\r"%(processed, ignored))
			sys.stdout.flush()
		return processed, ignored


class AnetHeaderProcessor(HeaderProcessor):
	"""A file processor for calibrating FITS frames using astrometry.net.

	It might provide calibration for "simple" cases out of the box, but
	you will usually need to at least override solverParameters.
	
	To use SExtractor rather than anet's source extractor, override
	sexScript, to use an object filter (see anet.getWCSFieldsFor), override
	the objectFilter attribute.

	To add additional fields, override _getHeader and call the parent
	class' _getHeader method.  To change the way astrometry.net is
	called, override the _solveAnet method (it needs to return some
	result anet.of getWCSFieldsFor) and call _runAnet with your
	custom arguments for getWCSFieldsFor.
	"""
	solverParameters = {
		"indices": ["index-209.fits"],
		"lower_pix": 0.1,
		"upper_pix": 1.0,
		"depth": 40,
	}
	sexScript = None
	objectFilter = None

	noCopyHeaders = set(["simple", "bitpix", "naxis", "imageh", "imagew",
		"naxis1", "naxis2", "datamin", "datamax", "date"])

	def _isProcessed(self, srcName):
		return self.readPrimaryHeader(srcName).has_key("CD1_1")

	def _runAnet(self, srcName, solverParameters, sexScript, objectFilter):
		return anet.getWCSFieldsFor(srcName, solverParameters,
			sexScript, objectFilter)

	def _solveAnet(self, srcName):
		return self._runAnet(srcName, self.solverParameters, self.sexScript,
			self.objectFilter)

	def _getHeader(self, srcName):
		wcsCards = self._solveAnet(srcName)
		hdr = self.readPrimaryHeader(srcName)
		fitstricks.copyFields(hdr, wcsCards, self.noCopyHeaders)
		return hdr


def procmain(processorClass, rdId, ddId, **processorKws):
	"""is a "standard" main function for scripts manipulating source files.

	The function returns the instanciated processor so you can communicate
	from your processor back to your own "main".
	"""
	import optparse
	from gavo import rscdesc
	rd = base.caches.getRD(rdId)
	dd = rd.getById(ddId)
	parser = optparse.OptionParser()
	processorClass.addOptions(parser)
	opts, args = parser.parse_args()
	proc = processorClass(opts, dd)
	processed, ignored = proc.processAll()
	print "%s files processed, %s files with errors"%(processed, ignored)
	return proc
