"""
Streaming out large computed things using twisted and threads.
"""

import sys
import threading
import traceback

from twisted.internet import reactor
from twisted.internet.interfaces import IPushProducer
from twisted.python import threadable

from zope.interface import implements


class DataStreamer(threading.Thread):
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

	chunkSize = 8192 # XXX TODO: Figure out a good chunk size for the
		# network stack

	def __init__(self, writeStreamTo, consumer):
		threading.Thread.__init__(self)
		self.writeStreamTo, self.consumer = writeStreamTo, consumer
		self.setDaemon(True) # kill transfers on server restart
		self.writeLock = threading.Lock()

	def resumeProducing(self):
		self.writeLock.release()

	def pauseProducing(self):
		self.writeLock.acquire()

	def stopProducing(self):
		self.join(self, 0.01)  # if this fails, we'll probably have a
			# memory leak, but working around it would be a pain
			# Maybe have some other entity clean up dead threads now and then?

	def realWrite(self, data):
		if isinstance(data, unicode): # we don't support encoding here, but
			data = str(data)            # don't break on accidental unicode.
		self.writeLock.acquire()  # blocks if production stopped
		self.writeLock.release()  # don't let the main thread wait in its acquire
		return reactor.callFromThread(self.consumer.write, data)
	
	def write(self, data):
		if len(data)<self.chunkSize:
			self.realWrite(data)
		else:
			# would be cool if we could use buffers here, but twisted won't
			# let us.
			for offset in range(0, len(data), self.chunkSize):
				self.realWrite(data[offset:offset+self.chunkSize])

	def run(self):
		try:
			self.writeStreamTo(self)
		except:
			sys.stderr.write("Exception while streaming:\n")
			traceback.print_exc()
			sys.stderr.write("Ignored, closing connection.\n")
		# All producing is done in thread, so when no one's writing any
		# more, we should have delivered everything to the consumer
		reactor.callFromThread(self.consumer.unregisterProducer)
		reactor.callFromThread(self.consumer.finish)

	synchronized = ['resumeProducing', 'stopProducing']

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

