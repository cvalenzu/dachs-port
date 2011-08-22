"""
Streaming out large computed things using twisted and threads.
"""

import collections
import sys
import time
import threading
import traceback

from nevow import appserver

from twisted.internet import reactor
from twisted.internet.interfaces import IPushProducer
from twisted.python import threadable

from zope.interface import implements

from gavo import base
from gavo import utils
from gavo.formats import votablewrite


class StopWriting(IOError):
	"""clients can raise this when they want the stream to abort.
	"""


class StreamBuffer(object):
	"""a buffer that takes data in arbitrary chunks and returns
	them in chops of chunkSize bytes.

	There's a lock in place so you can access add and get from
	different threads.

	When everything is written, you must all doneWriting.
	"""
	chunkSize = 10000 # XXX TODO: Figure out a good chunk size for the
	                  # network stack

	def __init__(self):
		self.buffer = collections.deque()
		self.curSize = 0
		self.lock = threading.Lock()
		self.finished = False
	
	def add(self, data):
		with self.lock:
			self.buffer.append(data)
			self.curSize += len(data)
	
	def get(self):
		if self.curSize<self.chunkSize and not self.finished:
			return None
		if not self.buffer:
			return None

		with self.lock:
			items, sz = [], 0
			# collect items till we've got a chunk
			while self.buffer:
				item = self.buffer.popleft()
				sz += len(item)
				self.curSize -= len(item)
				items.append(item)
				if sz>=self.chunkSize:
					break

			# make a chunk and push back what we didn't need
			chunk = "".join(items)
			leftOver = chunk[self.chunkSize:]
			if leftOver:
				self.buffer.appendleft(leftOver)
			self.curSize += len(leftOver)
			chunk = chunk[:self.chunkSize]

		return chunk
	
	def doneWriting(self):
		self.finished = True


class DataStreamer(threading.Thread):
# This is nasty (because it's a thread) and not necessary most of the
# time since the source may be a file or something that could just yield
# now and then.  We should really, really fix this.
	"""is a twisted-enabled Thread to stream out large files produced
	on the fly.

	It is basically a pull producer.  To use it, construct it with
	a data source and a twisted request (or any IFinishableConsumer)
	If in a nevow resource, you should then return request.deferred.

	The data source simply is a function writeStreamTo taking one
	argument; this will be the DataStreamer.  You can call its write
	method to deliver data.  There's no need to close anything, just
	let your function return.

	writeStream will be run in a thread to avoid blocking the reactor.
	This thread will be halted if the consumer calls stopProducing.  Since
	python threads cannot be halted from outside, this works by the
	consumer's thread acquiring the writeLock and only releasing it
	on resumeProducing.
	"""

	implements(IPushProducer)

	def __init__(self, writeStreamTo, consumer):
		threading.Thread.__init__(self)
		self.writeStreamTo, self.consumer = writeStreamTo, consumer
		self.paused, self.exceptionToRaise = False, None
		consumer.registerProducer(self, True)
		self.setDaemon(True) # kill transfers on server restart
		self.buffer = StreamBuffer()

	def resumeProducing(self):
		self.paused = False

	def pauseProducing(self):
		self.paused = True

	def stopProducing(self):
		self.exceptionToRaise = StopWriting("Stop writing, please")

	def _deliverBuffer(self):
		"""causes the accumulated data to be written if enough
		data is there.

		This must be called at least once after buffer.doneWriting()
		as been called.
		"""
		while True:
			data = self.buffer.get()
			if data is None: # nothing to write yet/any more
				return
			while self.paused:
				# consumer has requested a pause; let's busy-loop;
				# doesn't cost much and is easier than semaphores.
				time.sleep(0.1)

			reactor.callFromThread(self._writeToConsumer, data)

	def write(self, data):
		"""schedules data to be written to the consumer.
		"""
		if self.exceptionToRaise:
			raise self.exceptionToRaise

		# Allow unicode data in as long as it's actually ascii:
		if isinstance(data, unicode):
			data = str(data)

		self.buffer.add(data)
		self._deliverBuffer()

	def _writeToConsumer(self, data):
		# We want to catch errors occurring during writes.  This method
		# is called from the reactor (main) thread.
		# We assign to the exceptionToRaise instance variable, and this
		# races with stopProducing.  This race is harmless, though, since
		# in any case writing stops, and the exception raised is of secondary
		# importance.
		try:
			self.consumer.write(data)
		except IOError, ex:
			self.exceptionToRaise = ex
		except Exception, ex:
			base.ui.notifyError("Exception during streamed write.")
			self.exceptionToRaise = ex
	
	def cleanup(self, result=None):
		# Must be callFromThread'ed
		self.join(0.01)
		self.consumer.unregisterProducer()
		self.consumer.finish()
		self.consumer = None

	def run(self):
		try:
			try:
				self.writeStreamTo(self)
				self.buffer.doneWriting()
				self._deliverBuffer()
			except StopWriting:
				pass
			except IOError:
				# I/O errors are most likely not our fault, and I don't want
				# to make matters worse by pushing any dumps into a line
				# that's probably closed anyway.
				base.ui.notifyError("I/O Error while streaming:")
			except:
				base.ui.notifyError("Exception while streaming"
					" (closing connection):\n")
				self.consumer.write("\n\n\nXXXXXX Internal error in DaCHS software.\n"
					"If you are seeing this, please notify gavo@ari.uni-heidelberg.de\n"
					"with as many details (like a URL) as possible.\n"
					"Also, the following traceback may help people there figure out\n"
					"the problem:\n"+
					utils.getTracebackAsString())
		# All producing is done in the thread, so when no one's writing any
		# more, we should have delivered everything to the consumer
		finally:
			reactor.callFromThread(self.cleanup)

	synchronized = ['resumeProducing', 'pauseProducing', 'stopProducing']

threadable.synchronize(DataStreamer)


def streamOut(writeStreamTo, request):
	"""sets up the thread to have writeStreamTo write to request from
	a thread.

	For convenience, this function returns request.deferred, you
	you can write things like return streamOut(foo, request) in your
	renderHTTP (or analoguous).
	"""
	t = DataStreamer(writeStreamTo, request)
	t.start()
	return request.deferred


def streamVOTable(request, data, **contextOpts):
	"""streams out the payload of an SvcResult as a VOTable.
	"""
	def writeVOTable(outputFile):
		"""writes a VOTable representation of the SvcResult instance data
		to request.
		"""
		if "tablecoding" not in contextOpts:
			contextOpts["tablecoding"] = { 
				True: "td", False: "binary"}[data.queryMeta["tdEnc"]]
		if "version" not in contextOpts:
			contextOpts["version"] = data.queryMeta.get("VOTableVersion")
		tableMaker = votablewrite.writeAsVOTable(
			data.original, outputFile,
			ctx=votablewrite.VOTableContext(**contextOpts))
	return streamOut(writeVOTable, request)
