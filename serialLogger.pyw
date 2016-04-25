# Copyright (c) 2016 Shunya Sato
# Author: Shunya Sato
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

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)
log = logging.StreamHandler()
log.setLevel(logging.INFO)
logger.addHandler(log)

import os, sys, time
import json, re
from datetime import datetime
from collections import OrderedDict
from PyQt4 import QtCore, QtGui
import pyqtgraph as pg

import numpy as np
import serial

from ui_serialLogger import Ui_MainWindow

class SerialWorker(QtCore.QObject):
	# http://stackoverflow.com/questions/6783194/background-thread-with-qthread-in-pyqt
	finished = QtCore.pyqtSignal()
	dataReady = QtCore.pyqtSignal(str)

	def __init__(self):
		super(SerialWorker, self).__init__()
		self.addr  = "COM1"
		self.baud  = 115200 #9600
		self.running = False
		self.port = None
		self.fname = "magi_log.txt"
		self.use_file = False

	@QtCore.pyqtSlot()
	def processA(self):
		print("SerialWorker.processA")
		if self.use_file:
			self.port = open(self.fname, "r")
		else:
			try:
				print("Try opening serial port: {}".format(self.addr))
				self.port = serial.Serial(self.addr,self.baud)
			except:
				print("Error opening serial port!")
				self.port = None
				return None
		print("opened port")
		while self.running:
			#print "SerialWorker is running"
			line = self.port.readline()
			self.dataReady.emit(line)
			if self.use_file:
				time.sleep(0.01)

		print("SerialWorker finished processA")
		self.port.close()
		print("port is closed")
		self.finished.emit()

	def startRunning(self, portname):
		if portname == "FILE":
			self.use_file = True
		else:
			self.use_file = False
			self.addr = portname
		self.running = True

	def stopRunning(self):
		self.running = False

	def setFilename(self, fname):
		self.fname = fname

	def __del__(self):
		self.running = False
		if self.port:
			self.port.close()

class dataObject(object):
	def __init__(self, name, plotwdg, pen=pg.mkPen('r', width=1.0, style=QtCore.Qt.SolidLine)):
		self.pen = pen
		self.ydata = np.zeros(300)
		#self.dataplot = plotwdg.plot(self.ydata, symbol='o', symbolBrush=(255,0,0), symbolPen='w')
		self.dataplot = plotwdg.plot(self.ydata, symbol='o')
		self.dataplot.setPen(self.pen)
		self.name = name

		parent = None #self.groupBox_liveUpdate
		#TODO: start work here
		self.horizontalLayout = None
		self.checkbox_show = QtGui.QCheckBox(parent)
		self.checkbox_show.setChecked(True)
		self.lineedit_name = None
		self.botton_color = None
		self.checkbox_marker = None

	def hidePlot(self):
		self.dataplot.setPen(None)

	def showPlot(self):
		self.dataplot.setPen(self.pen)

	def resetData(self):
		self.ydata = np.zeros(300)
		self.dataplot.setData(self.ydata)

	def pushData(self, newData):
		self.ydata[:-1] = self.ydata[1:]
		self.ydata[-1] = newData
		self.dataplot.setData(self.ydata)

	def setPen(self, newPen):
		self.pen = newPen
		self.dataplot.setPen(self.pen)


class MainWindow(QtGui.QMainWindow, Ui_MainWindow):
	def __init__(self, parent=None):
		super(MainWindow, self).__init__(parent)
		self.setupUi(self)
		
		self.thread = QtCore.QThread()  # no parent!
		self.serialreader = SerialWorker()  # no parent!
		self.serialreader.moveToThread(self.thread)
		#self.serialreader.dataReady.connect(self.printPayload)
		self.serialreader.dataReady.connect(self.processPayload)
		self.thread.started.connect(self.serialreader.processA)

		# if you want the thread to stop after the worker is done
		# you can always call thread.start() again later
		# obj.finished.connect(thread.quit)

		# one way to do it is to start processing as soon as the thread starts
		# this is okay in some cases... but makes it harder to send data to
		# the worker object from the main gui thread.  As you can see I'm calling
		# processA() which takes no arguments
		#thread.started.connect(obj.processA)
		#thread.finished.connect(app.exit)
		#thread.start()

		#self._serialReader = serialreader()
		#self._serialReader.updated.connect(self.processPayload)
		self.pushButton.clicked.connect(self.start)
		self.pushButton_update.clicked.connect(self.populatePort)
		self.pushButtonUpdateFileName.clicked.connect(self.populateFileName)
		self.pushButton_AutoRange.clicked.connect(self.onAutoRange)

		self.populatePort()
		self.populateFileName()

		self.running = False
		self.logfileh = None

		self.dataObjects = {}
		self.dataObject_list = []
		dataNames = ['millis', 'a0', 'single', 'diff']
		pens = [
				pg.mkPen('r', width=1.0, style=QtCore.Qt.SolidLine),
				pg.mkPen('g', width=1.0, style=QtCore.Qt.SolidLine),
				pg.mkPen('b', width=1.0, style=QtCore.Qt.SolidLine),
				pg.mkPen('c', width=1.0, style=QtCore.Qt.SolidLine),
		]
		for i, dataName in enumerate(dataNames):
			self.dataObjects[dataName] = dataObject(dataName, self.plotwdg, pens[i])
			self.dataObject_list.append(self.dataObjects[dataName])
			#self.dataObjects[dataName].hidePlot()
		#self.dataObjects['a0'].showPlot()
		#self.dataObjects['single'].showPlot()

	def onAutoRange(self):
		self.plotwdg.enableAutoRange()

	def populatePort(self):
		self.comboBox.clear()
		serials = [('FILE', '', ''),]
		import serial.tools.list_ports
		#print list(serial.tools.list_ports.comports())
		serials += list(serial.tools.list_ports.comports())
		for device in serials:
			self.comboBox.addItem(device[0])

		myPortFound = self.comboBox.findText("/dev/cu.usbmodem534631")
		if myPortFound != -1:
			self.comboBox.setCurrentIndex(myPortFound)
		else:
			self.comboBox.setCurrentIndex(0)

	def populateFileName(self):
		now = datetime.now()
		fname = "magilog_{:04d}{:02d}{:02d}{:02d}{:02d}{:02d}.txt".format(now.year, now.month, now.day, now.hour, now.minute, now.second)
		self.lineEdit.setText(os.path.join("log", fname))

	def populateCheckBox(self, data):
		pass


	def start(self):
		if not self.running:
			print("Start running!")
			#self._serialReader.start()
			if str(self.comboBox.currentText()) == 'FILE':
				self.serialreader.setFilename(str(QtGui.QFileDialog.getOpenFileName(self, 'Open log file', 'log/', '*.txt')))
			self.serialreader.startRunning(str(self.comboBox.currentText()))
			self.thread.start()
			self.running = True
			self.pushButton.setText("STOP")
			if self.checkBox.isChecked():
				#TODO: except IOError. happens when log directory does not exist.
				self.logfileh = open(str(self.lineEdit.text()), 'w')

		else:
			print("Stop running.")
			# self._serialReader.quit()
			# self._serialReader.exit()
			# self._serialReader.wait()
			self.serialreader.stopRunning()
			self.thread.quit()
			self.running = False
			self.pushButton.setText("START")
			if self.logfileh:
				self.logfileh.close()
				self.logfileh = None

	def processPayload(self, payloadQs):
		"""
		Receive QString payload
		"""
		#convert QString payload to Python String
		payload = unicode(payloadQs).encode('latin-1')
		self.textBrowser.append(payload.strip())
		if self.logfileh:
			self.logfileh.write(payload)

		if self.radioButton_csv.isChecked():
			# parse as csv
			data_list = payload.split(',')
			#data = OrderedDict()
			data = []
			for i, item in enumerate(data_list):
				#name = "data{}".format(i)
				#data[name] = float(item.strip())
				try:
					data.append(float(item.strip()))
				except:
					#print("Not a number: {}".format(item))
					pass
		else:
			# format is json
			try:
				data_dic = json.loads(payload)
			except:
				#print("Not json: {}".format(payload))
				return None
			data = data_dic.values()

		self.updatePlot(data)

	def clearPlot(self, index):
		#TODO: do something?
		pass

	def updatePlot(self, data):
		checkBoxes = [self.checkBox_d0, self.checkBox_d1, self.checkBox_d2, self.checkBox_d3]
		for i, item in enumerate(data):
			if checkBoxes[i].isChecked():
				self.dataObject_list[i].pushData(item)

	def __del__(self):
		# make sure serial is closed.
		self.serialreader.stopRunning()
		self.thread.quit()
		if self.logfileh:
			self.logfileh.close()
			self.logfileh = None
		#super(MainWindow, self).__del__(parent)

	def closeEvent(self, event):
		pass
		
def main():
	app = QtGui.QApplication(sys.argv)
	form = MainWindow()
	form.show()
	app.exec_()

main()