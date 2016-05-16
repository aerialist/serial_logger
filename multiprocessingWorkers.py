# Copyright (c) 2016 Shunya Sato
# Author: Shunya Sato
#
# Heart of the code is take from https://gist.github.com/pklaus/4039175
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
This version uses Python's multiprocessing; Process and Queue.
This is very good for normal Python environment like on Raspberry Pi.
But Multiprocessing does not play nice with PyQT...

"""

# make this code Py2 and Py3 compatible
# make sure you have "pip install future"
from __future__ import (absolute_import, division,
						print_function, unicode_literals)
from builtins import (
		 bytes, dict, int, list, object, range, str,
		 ascii, chr, hex, input, next, oct, open,
		 pow, round, super,
		 filter, map, zip)

import time
import json
import multiprocessing
from multiprocessing import Process, Queue
try:
	from queue import Empty
except ImportError:
	from Queue import Empty
				
import serial

import logging
#logging.basicConfig(level=logging.DEBUG,
#					format='[%(levelname)s] (%(threadName)-10s) %(message)s',
#					)
logger = multiprocessing.log_to_stderr()
logger.setLevel(multiprocessing.SUBDEBUG)

class SerialManager(Process):
	""" This class has been written by
		Philipp Klaus and can be found on
		https://gist.github.com/4039175 .  
		
		modified by Shunya
	"""

	def __init__(self, device, kwargs):
		settings = dict()
		settings['baudrate'] = 9600
		settings['bytesize'] = serial.EIGHTBITS
		settings['parity'] = serial.PARITY_NONE
		settings['stopbits'] = serial.STOPBITS_ONE
		settings['timeout'] = 0.0005
		settings.update(kwargs)
		self._kwargs = settings
		self.ser = serial.Serial(device, **self._kwargs)
		self.outgoings = []
		self.out_queue = Queue()
		self.closing = False # A flag to indicate thread shutdown
		self.read_num_bytes  = 256
		self.sleeptime = None
		Process.__init__(self, target=self.loop)

	def loop(self):
		try:
			while not self.closing:
				if self.sleeptime: time.sleep(self.sleeptime)
				in_data = self.ser.read(self.read_num_bytes)
				if in_data:
					#logger.debug(in_data)
					for q in self.outgoings:
						q.put(in_data)
				try:
					out_buffer = self.out_queue.get_nowait()
					self.ser.write(out_buffer)
				except Empty:
					pass
		except (KeyboardInterrupt, SystemExit):
			pass
		self.ser.close()

	def appendOutgoingQueue(self, anotherQueue):
		self.outgoings.append(anotherQueue)

	def close(self):
		self.closing = True

class Dump2file(Process):
	"""
		Class to save to file
	"""
	def __init__(self, incomingQ, fname, mode='a', sleeptime=5):
		self.incomingQ = incomingQ
		self.fname = fname
		self.closing = False
		self.sleeptime = sleeptime
		self.mode = mode
		Process.__init__(self, target=self.loop)
	
	def loop(self):
		buffer=""
		while not self.closing:
			if self.sleeptime: time.sleep(self.sleeptime)
			try:
				while not self.closing:
					buffer += self.incomingQ.get(block=False)
			except Empty:
				with open(self.fname, mode=self.mode) as f:
					f.write(buffer)
					buffer=""
	def close(self):
		self.closing = True
		
		
class LineSplitter(Process):
	"""
		Class to split lines
	"""

	def __init__(self, incomingQ, outgoingQ=None):
		self.incomingQ = incomingQ
		if outgoingQ:
			self.outgoings = [outgoingQ]
		else:
			self.outgoings = {}
		self.closing = False # A flag to indicate thread shutdown
		self.sleeptime = None
		Process.__init__(self, target=self.loop)

	def loop(self):
		buffer = ""
		while not self.closing:
			if self.sleeptime: time.sleep(self.sleeptime)
			try:
				while True:
					buffer += self.incomingQ.get(block=False)
			except Empty:
				if '\n' in buffer:
					lines = buffer.split('\n')
					if lines[:-2]:
						for q in self.outgoings:
							for line in lines[:-1]:
								q.put(line)
					buffer = lines[-1]

	def appendOutgoingQueue(self, anotherQueue):
		self.outgoings.append(anotherQueue)

	def close(self):
		self.closing = True

class CsvParser(Process):
	"""
		Class to parse each line as csv
	"""

	def __init__(self, incomingQ, outgoingQ=None):
		self.incomingQ = incomingQ
		if outgoingQ:
			self.outgoings = [outgoingQ]
		else:
			self.outgoings = {}
		self.closing = False # A flag to indicate thread shutdown
		Process.__init__(self, target=self.loop)

	def loop(self):
		while not self.closing:
			try:
				line = self.incomingQ.get()
			except Empty:
				continue
			for q in self.outgoings:
				stripped = line.split(',').strip()
				q.put(stripped)

	def appendOutgoingQueue(self, anotherQueue):
		self.outgoings.append(anotherQueue)

	def close(self):
		self.closing = True

class Raw2Box(Process):
	"""
		Class to append QTextBrowser
	"""

	def __init__(self, incomingQ, qTextBrowser, end=None):
		self.incomingQ = incomingQ
		self.qTextBrowser = qTextBrowser
		self.end = end
		self.closing = False # A flag to indicate thread shutdown
		Process.__init__(self, target=self.loop)

	def loop(self):
		while not self.closing:
			try:
				data = self.incomingQ.get()
				logger.debug(data)
			except Empty:
				continue
			self.qTextBrowser.append(data)
			# handle auto scroll
			if self.end:
				self.qTextBrowser.moveCursor(self.end)

	def close(self):
		self.closing = True

def main():
#	import argparse
#	parser = argparse.ArgumentParser(description='A class to manage reading and writing from and to a serial port.')
#	parser.add_argument('--timeout', '-t', type=float, default=0.0005, help='Seconds until reading from serial port times out [default: 0.0005].')
#	parser.add_argument('--sleeptime', '-s', type=float, default=None, help='Seconds to sleep before reading from serial port again [default: none].')
#	parser.add_argument('--baudrate', '-b', type=int, default=9600, help='Baudrate of serial port [default: 9600].')
#	parser.add_argument('device', help='The serial port to use (COM4, /dev/ttyUSB1 or similar).')
#	args = parser.parse_args()
#
#	s1 = SerialManager(args.device, baudrate=args.baudrate, timeout=args.timeout)
#	s1.sleeptime = args.sleeptime
	arg = {}
	arg['baudrate'] = 115200
	arg['timeout'] = None
	s1 = SerialManager("/dev/cu.usbserial-AH00RZ5C", arg)	
	s1.read_num_size = 512
	qraw = Queue()
	qraw2 = Queue()
	qlines = Queue()
	qcsvs = Queue()
	s1.appendOutgoingQueue(qraw)
	s1.appendOutgoingQueue(qraw2)
	s2 = Dump2file(qraw, "log.txt")
	s3 = LineSplitter(qraw2, qlines)
	s4 = CsvParser(qlines, qcsvs)
	workers = [s1, s2, s3, s4]
	for worker in workers:
		worker.start()

	try:
		while True:
			print(qcsvs.get())
	except KeyboardInterrupt:
		for worker in workers:
			worker.close()
	finally:
		for worker in workers:
			worker.close()
	for worker in workers:
		worker.join()

#	#port = serial.Serial("/dev/cu.usbserial-A901O8YI", 115200, timeout=5)
#	port = serial.Serial("/dev/cu.usbserial-AH00RZ5C", 115200, timeout=5)	
#	fname = "log.csv"

if __name__ == "__main__":
	main()

