#!/usr/bin/python

'''
Plots intensity readings taken from a USB device and outputs heart rate and SpO2.
Author: Jonathan Thomson
Released Under the MIT License

GUI framework based on code by Michael Spiceland 
https://code.google.com/p/avr-libarduino-pulseoximeter/

USB code borrowed from DeviceAccessPy.py by Opendous Inc. under MIT License
http://code.google.com/p/micropendous/source/browse/trunk/Micropendous/Firmware/LoopBack/DeviceAccessPy.py?r=404
'''

import sys
import struct
import usb
import time
import threading
from PyQt4 import QtGui, QtCore
from math import sin, pi
from numpy import NaN, Inf, arange, array, append, diff, isnan, isscalar, log, mean, median, ceil

DEBUG_DATA = False
DEBUG_TIMING = True

# So that a heart rate of 250 bpm has a well defined trace take 40 samples per
# beat at 250 [bpm] which is 166.7 samples/sec. Therefore at a heart rate of
# 80 [bpm] (midrange normal) one beat will be composed of 125 samples.
#
# The microcontroller outputs 5 datasets every read. A dataset is a sample
# from the red LED, a sample from the IR LED, and the sample number. The
# microcontroller puts a new dataset in the output buffer every 6 milliseconds.
# Therefore the buffer is completely refreshed every 30 ms. If interruptRead()
# is called every 30 ms, that's 33.3 reads per second. Therefore the effective
# sample rate is 166.7 Hz (33.3[reads/s] * 5[dataset/read])
#
# A shorter READ_PERIOD results in more samples per heart beat and therefore
# a better looking trace. However since this heart beat trace is composed of
# more samples and the number of samples that will fit in a graph window is
# fixed, then fewer heart beats will fit in the graph window at one time. A
# shorter READ_PERIOD won't necessarily result in more accurate calculations.
# For example, when data was acquired at an effective rate of 1000 Hz and the
# SpO2 was calculated it barely differed from the SpO2 calculated from the same
# data downsampled to 10 Hz (i.e. SpO2 percent error was 0.258%). Additionally
# heart rate calculations will be inaccurate if a short READ_PERIOD results
# in only a few heart beats fitting within BUFFERSIZE.
#
# With a UC_SAMPLE_PERIOD of 0.005, a BUFFERSIZE of 1500, and a heart rate of 
# 60 [bpm] then 7.5 beats will fit in the buffer and plot window. Heart rates
# above 300 [bpm] will have less than 40 samples/beat.
# With a UC_SAMPLE_PERIOD of 0.006, a BUFFERSIZE of 1500, and a heart rate of 
# 60 [bpm] then 9 beats will fit in the buffer and plot window. Heart rates
# above 250 [bpm] will have less than 40 samples/beat.

# Start of hard constants. If you'd like to change these you'll have to
# modify the microcontroller code. UC_NUM_DATASETS cannot be greater
# than 5.
USB_VID = 0xFFFE
USB_PID = 0x0001
UC_NUM_DATASETS = 5
#UC_SAMPLE_PERIOD = 0.005 # seconds, new dataset buffered in uc every 5 ms
UC_SAMPLE_PERIOD = 0.006 # seconds, new dataset buffered in uc every 6 ms
READ_PERIOD = UC_NUM_DATASETS*UC_SAMPLE_PERIOD # seconds
# End of hard constants.


def set_constants(view):

    global GRAPH_HEIGHT, GRAPH_WIDTH
    global WINDOW_HEIGHT, WINDOW_WIDTH
    global BUFFERSIZE
    global NUM_POINTS_PER_PLOT, STEP, SAMPLES_PER_REFRESH
    global EDGE_THRESHOLD
    global HRBUFFERSIZE, SPO2BUFFERSIZE

    # Start of soft constants. You can adjust soft constants as you see fit.

    if (view == 'short'):
        # The short view is better for viewing a detailed photoplethysmogram.
        # Fewer beats are displayed on the screen, but more points are used
        # to plot each beat.
        GRAPH_HEIGHT = 680
        GRAPH_WIDTH = 780
        WINDOW_HEIGHT = GRAPH_HEIGHT+70
        WINDOW_WIDTH = GRAPH_WIDTH+20

        BUFFERSIZE = 1500

        NUM_POINTS_PER_PLOT = 500 # set this less than BUFFERSIZE for quicker plotting
        STEP = BUFFERSIZE/NUM_POINTS_PER_PLOT
        SAMPLES_PER_REFRESH = 15*STEP # must be a multiple of UC_NUM_DATASETS

    elif (view == 'long'):
        # The long view is better if you'd like to see a longer photoplethysmogram
        # to monitor respiration. More beats are displayed on the screen, but
        # fewer points are used to plot each beat.
        GRAPH_HEIGHT = 680
        GRAPH_WIDTH = 1210
        WINDOW_HEIGHT = GRAPH_HEIGHT+70
        WINDOW_WIDTH = GRAPH_WIDTH+20

        BUFFERSIZE = 12000

        NUM_POINTS_PER_PLOT = 1000
        STEP = BUFFERSIZE/NUM_POINTS_PER_PLOT
        SAMPLES_PER_REFRESH = 10*STEP

    # Beat detection at the edge of the data is unreliable. So any beats beyond
    # EDGE_THRESHOLD should be discarded. 83 is half the number of samples that
    # make up one beat at 60 [bpm] when the sample rate is 166.7 Hz.
    EDGE_THRESHOLD = BUFFERSIZE-round((1/UC_SAMPLE_PERIOD)/2)

    # buffer approx. the last 3 seconds
    HRBUFFERSIZE = int(round(3/(UC_SAMPLE_PERIOD*SAMPLES_PER_REFRESH)))

    # buffer approx. the last 20 seconds
    SPO2BUFFERSIZE = int(round(20/(UC_SAMPLE_PERIOD*SAMPLES_PER_REFRESH)))
    # End of soft contants.


class MainWindow(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        set_constants('short')

        self.pod = PulseOxData(self)

        self.thread = Worker(self)
        self.status = 'stopped'

        self.button = QtGui.QPushButton('Start',self)
        self.button.setGeometry(10, 10, 60, 35)

        self.rbshort = QtGui.QRadioButton('Short view',self)
        self.rbshort.setChecked(True)
        self.rblong = QtGui.QRadioButton('Long view',self)
        self.rblong.setGeometry(100, 0, 60, 35)

        self.heartrate_label = QtGui.QLabel('Heart Rate\n?', self)
        self.heartrate_label.setAlignment(QtCore.Qt.AlignHCenter)

        self.SpO2_label = QtGui.QLabel('SpO2\n?', self)
        self.SpO2_label.setAlignment(QtCore.Qt.AlignHCenter)

        self.plot = Graph(self)

        hbox_top = QtGui.QHBoxLayout()
        hbox_top.addWidget(self.button)

        vbox_rb = QtGui.QVBoxLayout()
        vbox_rb.addWidget(self.rbshort)
        vbox_rb.addWidget(self.rblong)
        hbox_top.addLayout(vbox_rb)

        hbox_top.addWidget(self.heartrate_label)
        hbox_top.addWidget(self.SpO2_label)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.plot)
        vbox = QtGui.QVBoxLayout()
        vbox.addStretch(1)
        vbox.addLayout(hbox_top)
        vbox.addLayout(hbox)
        self.setLayout(vbox)

        #self.setGeometry(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMaximumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowTitle('Pulse Oximeter')

        self.connect(self.button, QtCore.SIGNAL('clicked()'), self.clickedButton)
        self.connect(self.rbshort, QtCore.SIGNAL('toggled(bool)'), self.toggledButton)
        self.connect(self.thread, QtCore.SIGNAL('newData()'), self.newData)

        if (DEBUG_DATA == True):
            self.fo_rawdata = open('debug_data/rawdata.txt', 'w')
            self.fo_SpO2data = open('debug_data/SpO2data.txt', 'w')

        if (DEBUG_TIMING == True):
            self.fo_rdtime = open('debug_data/readDatatime.txt', 'w')
            self.fo_pdtime = open('debug_data/processDatatime.txt', 'w')
            self.fo_gtime = open('debug_data/Graphtime.txt', 'w')

    def init_USB(self):
        device_found = False
        busses = usb.busses()
        for bus in busses:
            if device_found == True:
                break
            devices = bus.devices
            for dev in devices:
                if (dev.idVendor == USB_VID) & (dev.idProduct == USB_PID):
                    device_found = True
                    vid = hex(int(dev.idVendor)).upper()
                    pid = hex(int(dev.idProduct)).upper()
                    print 'Found vendorid:'+vid+', productid:'+pid+'.'
                    break

        if device_found == True:
            self.handle = dev.open()
            self.handle.setConfiguration(1)
            self.handle.claimInterface(0)
        elif device_found == False:
            vid = hex(USB_VID).upper()
            pid = hex(USB_PID).upper()
            print 'Device (vendorid:'+vid+', productid:'+pid+') not found.'

        return device_found

    def clickedButton(self):
        if self.status == 'stopped':
            if not self.init_USB():
                return
            self.thread.start()
            self.button.setText('Stop')
            self.status = 'running'
            self.setWindowTitle('Pulse Oximeter (running)')
            self.plot.repaint()
        elif self.status == 'running':
            self.thread.stop()
            self.thread.wait()
            self.button.setText('Start')
            self.status = 'stopped'
            self.setWindowTitle('Pulse Oximeter (stopped)')
            self.plot.repaint()

    def toggledButton(self):
        if self.status == 'running':
            self.thread.stop()
            self.thread.wait()
            self.status = 'was running'
            #self.plot.repaint()

        if (self.rbshort.isChecked() == True):
            set_constants('short')
        elif (self.rblong.isChecked() == True):
            set_constants('long')

        self.thread.setup()
        self.plot.set_width_height()
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMaximumSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        if self.status == 'was running':
            if not self.init_USB():
                return
            self.thread.start()
            self.status = 'running'
            self.plot.repaint()

    def newData(self):
        self.plot.repaint()

    def closeEvent(self, event):
        self.thread.stop()
        self.thread.wait()
        if (DEBUG_DATA == True):
            self.fo_rawdata.close()
            self.fo_SpO2data.close()

        if (DEBUG_TIMING == True):
            self.fo_rdtime.close()
            self.fo_pdtime.close()
            self.fo_gtime.close()


class Graph(QtGui.QLabel):
    def __init__(self, parent):
        QtGui.QLabel.__init__(self, parent)
        self.parent = parent

        self.setMinimumSize(GRAPH_WIDTH, GRAPH_HEIGHT)
        self.setMaximumSize(GRAPH_WIDTH, GRAPH_HEIGHT)

        self.heart_peak = QtGui.QImage('heart_peak.png')
        self.heart_trough = QtGui.QImage('heart_trough.png')
        self.hw = self.heart_peak.width()/2
        self.hh = self.heart_peak.height()
        self.floor_red = (GRAPH_HEIGHT/2)-self.hh
        self.floor_ir = GRAPH_HEIGHT-self.hh
        self.sf = self.floor_red-self.hh

    def set_width_height(self):
        self.setMinimumSize(GRAPH_WIDTH, GRAPH_HEIGHT)
        self.setMaximumSize(GRAPH_WIDTH, GRAPH_HEIGHT)
        self.floor_red = (GRAPH_HEIGHT/2)-self.hh
        self.floor_ir = GRAPH_HEIGHT-self.hh
        self.sf = self.floor_red-self.hh # scaling factor

    def paintEvent(self, event):
        if (DEBUG_TIMING == True):
            t0 = time.time()

        paint = QtGui.QPainter()
        paint.begin(self)

        font = QtGui.QFont('Serif', 7, QtGui.QFont.Light)
        paint.setFont(font)

        size = self.size()

        # background
        paint.setPen(QtGui.QColor(255, 255, 255))
        paint.setBrush(QtGui.QColor(255, 255, 255))
        paint.drawRect(0, 0, size.width(), size.height())

        tn, nPPG_red, nPPG_ir, systole, diastole, hr_out, SpO2_out \
        = self.parent.pod.getData()
        self.parent.pod.lock.release()

        plot_red = self.sf*nPPG_red
        plot_ir = self.sf*nPPG_ir

        # plot red PPG (photoplethysmogram)
        paint.setPen(QtGui.QColor(255, 0, 0))
        paint.setBrush(QtGui.QColor(255, 255, 255))
        for i in range(0, BUFFERSIZE-STEP, STEP):
            cv = plot_red[i]
            nv = plot_red[i+STEP]
            paint.drawLine(tn[i], self.floor_red-cv, tn[i+STEP], self.floor_red-nv)

        # plot IR PPG
        paint.setPen(QtGui.QColor(0, 0, 0))
        paint.setBrush(QtGui.QColor(255, 255, 255))
        for i in range(0, BUFFERSIZE-STEP, STEP):
            cv = plot_ir[i]
            nv = plot_ir[i+STEP]
            paint.drawLine(tn[i], self.floor_ir-cv, tn[i+STEP], self.floor_ir-nv)

        # mark peaks and troughs
        paint.setPen(QtGui.QColor(0, 255, 0))
        paint.setBrush(QtGui.QColor(255, 255, 255))
        if (systole != 'NA' and diastole != 'NA'):
            for i in range(len(systole)):
                red_pk = plot_red[systole[i]]
                ir_pk = plot_ir[systole[i]]
                t1 = tn[systole[i]]-self.hw
                paint.drawImage(t1, self.floor_red-(red_pk+self.hh), self.heart_peak)
                paint.drawImage(t1, self.floor_ir-(ir_pk+self.hh), self.heart_peak)

                if i < len(diastole):
                    red_th = plot_red[diastole[i]]
                    ir_th = plot_ir[diastole[i]]
                    t1 = tn[diastole[i]]-self.hw
                    paint.drawImage(t1, self.floor_red-red_th, self.heart_trough)
                    paint.drawImage(t1, self.floor_ir-ir_th, self.heart_trough)

        self.parent.heartrate_label.setText('Heart Rate\n' + hr_out)
        self.parent.SpO2_label.setText('SpO2\n' + SpO2_out)
        paint.end()

        if (DEBUG_TIMING == True):
            t1 = time.time()
            self.parent.fo_gtime.write(str(t1-t0))
            self.parent.fo_gtime.write('\n')

class PulseOxData():
    def __init__(self, parent = None):
        self.lock = threading.Lock()

        self.tn = 0
        self.nPPG_red = 0
        self.nPPG_ir = 0
        self.systole = 0
        self.diastole = 0
        self.hr_out = 'NA'
        self.SpO2_out = 'NA'

    def getData(self):
        self.lock.acquire()
        return self.tn, self.nPPG_red, self.nPPG_ir, self.systole, \
               self.diastole, self.hr_out, self.SpO2_out
        # lock is released by getData() caller.

    def setData(self, tn, nPPG_red, nPPG_ir, systole, diastole, hr_out, SpO2_out):
        self.lock.acquire()
        self.tn = tn
        self.nPPG_red = nPPG_red
        self.nPPG_ir = nPPG_ir
        self.systole = systole
        self.diastole = diastole
        self.hr_out = hr_out
        self.SpO2_out = SpO2_out
        self.lock.release()

class Worker(QtCore.QThread):
    def __init__(self, parent = None):
        QtCore.QThread.__init__(self, parent)
        self.parent = parent

        self.in_ep = 0x81
        self.in_ep_size = 60

        self.setup()

    def setup(self):
        self.first_loop = True
        self.raw_data_ready = False
        self.plot_data_ready = True

        self.cb_red = array([0]*BUFFERSIZE) # red circular buffer
        self.cb_ir = array([0]*BUFFERSIZE)  # IR circular buffer
        self.cb_n = array([0]*BUFFERSIZE)  # sample number circular buffer
        self.i = 0

        self.heartrate_buffer = [60]*HRBUFFERSIZE
        self.hrbi = 0

        #self.K = 0.012
        #self.K = -0.005 # SpO2 calculation calibration constant, offtarget=?
        self.K = -0.024542 # SpO2 calculation calibration constant, offtarget=97, 98.7
        #self.K = -0.036883 # SpO2 calculation calibration constant, offtarget=96.5
        #self.K = -0.049273 # SpO2 calculation calibration constant, offtarget=96

        self.SpO2_buffer = [98]*SPO2BUFFERSIZE
        self.SpO2bi = 0

        tn = float(GRAPH_WIDTH)*array(range(BUFFERSIZE))/(BUFFERSIZE-1)
        nPPG_red = array([0.5*sin(2*pi*(1/150.0)*i)+0.5 for i in range(BUFFERSIZE)])
        nPPG_ir = nPPG_red
        systole, diastole = self.peakdet(nPPG_red, 0.25)
        systole = systole[:-1]
        self.parent.pod.setData(tn, nPPG_red, nPPG_ir, systole, diastole, 'NA', 'NA')

        self.read_t0 = 0

    def stop(self):
        self.thread_run = False

    def run(self):
        self.thread_run = True

        while self.thread_run:
            read_t1 = time.time()
            # A Timer object was being used but it has the problem that if one
            # timer's call is delayed nearly the entire timer period then
            # another call can follow just moments after the first call
            # finishes. If that happens duplicate data would be read.
            if (read_t1 - self.read_t0 > READ_PERIOD):
                # This sets raw_data_ready to True after several
                # calls once there's enough new raw data to process.
                self.readData()

                if (self.raw_data_ready == True):
                    self.raw_data_ready = False

                    # refresh so the GUI doesn't become unresponsive
                    #app.processEvents()

                    # Unroll the circular buffers and assign the data to new
                    # variables to indicate we're working with intensity. This
                    # is still the frequency data output from the TSL230 but
                    # it's proprotional to intensity.
                    Ired = self.cb_red[self.i:]
                    Ired = append(Ired, self.cb_red[:self.i])
                    Iir = self.cb_ir[self.i:]
                    Iir = append(Iir, self.cb_ir[:self.i])
                    n = self.cb_n[self.i:]
                    n = append(n, self.cb_n[:self.i])

                    self.processData(n, Ired, Iir)

                    # Because processing and plotting data take some time, it's
                    # better to do them separately and plot the data one timer
                    # period after processing the data.
                    self.plot_data_ready = True

                elif (self.plot_data_ready == True):
                    self.plot_data_ready = False

                    # I think this causes a crash if the window is moved while
                    # painting.
                    #self.parent.plot.repaint()
                    # Is this better? What about timing?
                    self.emit(QtCore.SIGNAL('newData()'))


    def readData(self):
        if (DEBUG_TIMING == True):
            t1 = time.time()
            self.parent.fo_rdtime.write(str(t1-self.read_t0))
            self.parent.fo_rdtime.write('\n')

        self.read_t0 = time.time()

        # rawdata holds the frequency data output from the TSL230
        # smoothed by a moving average
        data = self.parent.handle.interruptRead(self.in_ep, self.in_ep_size, 800)

        # heart beat --> more blood in light path --> more light absorbed
        # --> less light detected by sensor --> lower frequency output

        # dataset 0
        self.cb_red[self.i] = (data[3]<<24)+(data[2]<<16)+(data[1]<<8)+data[0]
        self.cb_ir[self.i] = (data[7]<<24)+(data[6]<<16)+(data[5]<<8)+data[4]
        self.cb_n[self.i] = (data[11]<<24)+(data[10]<<16)+(data[9]<<8)+data[8]

        # This makes for a nicer plot. Otherwise the the traces would be too
        # small to see until all the initial zeroes in the buffer are replaced
        # with new data.
        if (self.first_loop == True):
            self.first_loop = False
            self.cb_red[:] = self.cb_red[0]
            self.cb_ir[:] = self.cb_ir[0]
            cb_n0 = self.cb_n[0]
            self.cb_n[:] = range(cb_n0-len(self.cb_n), cb_n0)
            self.cb_n[0] = cb_n0

        # dataset 1
        self.cb_red[self.i+1] = (data[15]<<24)+(data[14]<<16)+(data[13]<<8)+data[12]
        self.cb_ir[self.i+1] = (data[19]<<24)+(data[18]<<16)+(data[17]<<8)+data[16]
        self.cb_n[self.i+1] = (data[23]<<24)+(data[22]<<16)+(data[21]<<8)+data[20]

        # dataset 2
        self.cb_red[self.i+2] = (data[27]<<24)+(data[26]<<16)+(data[25]<<8)+data[24]
        self.cb_ir[self.i+2] = (data[31]<<24)+(data[30]<<16)+(data[29]<<8)+data[28]
        self.cb_n[self.i+2] = (data[35]<<24)+(data[34]<<16)+(data[33]<<8)+data[32]

        # dataset 3
        self.cb_red[self.i+3] = (data[39]<<24)+(data[38]<<16)+(data[37]<<8)+data[36]
        self.cb_ir[self.i+3] = (data[43]<<24)+(data[42]<<16)+(data[41]<<8)+data[40]
        self.cb_n[self.i+3] = (data[47]<<24)+(data[46]<<16)+(data[45]<<8)+data[44]

        # dataset 4
        self.cb_red[self.i+4] = (data[51]<<24)+(data[50]<<16)+(data[49]<<8)+data[48]
        self.cb_ir[self.i+4] = (data[55]<<24)+(data[54]<<16)+(data[53]<<8)+data[52]
        self.cb_n[self.i+4] = (data[59]<<24)+(data[58]<<16)+(data[57]<<8)+data[56]

        if (DEBUG_DATA == True):
            self.parent.fo_rawdata.write(' '+str(self.read_t0)+ \
            ' '+str(self.cb_n[self.i])+' '+str(self.cb_red[self.i])+ \
            ' '+str(self.cb_ir[self.i]))
            self.parent.fo_rawdata.write('\n')

            self.parent.fo_rawdata.write(' '+str(self.read_t0)+ \
            ' '+str(self.cb_n[self.i+1])+' '+str(self.cb_red[self.i+1])+ \
            ' '+str(self.cb_ir[self.i+1]))
            self.parent.fo_rawdata.write('\n')

            self.parent.fo_rawdata.write(' '+str(self.read_t0)+ \
            ' '+str(self.cb_n[self.i+2])+' '+str(self.cb_red[self.i+2])+ \
            ' '+str(self.cb_ir[self.i+2]))
            self.parent.fo_rawdata.write('\n')

            self.parent.fo_rawdata.write(' '+str(self.read_t0)+ \
            ' '+str(self.cb_n[self.i+3])+' '+str(self.cb_red[self.i+3])+ \
            ' '+str(self.cb_ir[self.i+3]))
            self.parent.fo_rawdata.write('\n')

            self.parent.fo_rawdata.write(' '+str(self.read_t0)+ \
            ' '+str(self.cb_n[self.i+4])+' '+str(self.cb_red[self.i+4])+ \
            ' '+str(self.cb_ir[self.i+4]))
            self.parent.fo_rawdata.write('\n')

        self.i = (self.i + 5) % BUFFERSIZE # index of the oldest sample

        if (self.i % SAMPLES_PER_REFRESH == 0):
            self.raw_data_ready = True

    def processData(self, n, Ired, Iir):
        if (DEBUG_TIMING == True):
            t0 = time.time()

        tn = float(GRAPH_WIDTH)*(n - n[0])/(n[-1] - n[0])

        # photoplethysmograms
        PPG_red = -1*log(Ired/float(max(Ired)))
        PPG_ir = -1*log(Iir/float(max(Iir)))

        mxr = float(max(PPG_red))
        mxi = float(max(PPG_ir))

        if (mxr > mxi):
            nf = mxr
        else:
            nf = mxi

        # limiting the normalization factor will prevent the traces from getting
        # too small but may cause them to overlap.
        #if (nf > 0.10):
        #   nf = 0.10

        # normalize PPGs for plotting
        nPPG_red = PPG_red/nf
        nPPG_ir = PPG_ir/nf

        # Locate heartbeats
        # systole - PPG peak (heartbeat), intensity trough
        # diastole - PPG trough, intensity peak
        # Find peaks on mean of normalized PPGs so delta can be constant
        # and differences in the peak locations on the separate PPGs are
        # averaged out.
        #systole, diastole = self.peakdet(((PPG_red/mxr)+(PPG_ir/mxi)), 0.5)
        #systole, diastole = self.peakdet(((PPG_red/mxr)+(PPG_ir/mxi)), 0.25)
        systole, diastole = self.peakdet(((PPG_red/mxr)+(PPG_ir/mxi)), 0.15)
        if (len(systole) > 2 and len(diastole) > 2):

            # last PPG peak found is wrong if it's near the end of the data
            if (systole[-1] > EDGE_THRESHOLD):
                systole = systole[:-1]

            # last PPG trough found is wrong if it's near the end of the data
            if (diastole[-1] > EDGE_THRESHOLD):
                diastole = diastole[:-1]

            # to be consistent when calculating R, the first PPG 
            # trough should always be after the first PPG peak
            if (diastole[0] <= systole[0]):
                diastole = diastole[1:]

            time_elapsed = UC_SAMPLE_PERIOD*(n[systole[-1]] - n[systole[0]])
            self.heartrate_buffer[self.hrbi] = 60*(len(systole)-1)/time_elapsed
            self.hrbi = (self.hrbi + 1) % HRBUFFERSIZE
            hr_out = str(int(round(median(self.heartrate_buffer))))

            SpO2 = []
            for i in range(len(diastole)):
                # Introduction to Pulse oximetry, Sagar G V, August 21, 2012
                # page 4
                # R = ln(I_rxR_peak/I_rxR_trough)/ln(I_rxIR_peak/I_rxIR_trough) Eq. 7
                # for red LED light at 660 nm and infrared LED light at 940 nm:
                # SpO2 = ((0.81 - 0.18*R)./(0.63 + 0.11*R))*100%
                #
                # Intensity peaks occur during diastole and troughs
                # during systole

                # 5 points surrounding intensity trough
                rs = range(systole[i]-2, systole[i]+3)

                Rred = log(Ired[diastole[i]]/mean(Ired[rs]))
                Rir = log(Iir[diastole[i]]/mean(Iir[rs]))
                R = Rred/Rir

                #SpO2new = 100*(0.81 - 0.18*R[-1])/(0.63 + 0.11*R[-1])
                #SpO2new = 5.05*R[-1]**2 - 47.62*R[-1] + 129.57 # 96 --> 98.1 ***
                SpO2new = 100*(0.81 - 0.18*(R+self.K))/(0.63 + 0.11*(R+self.K))

                if (SpO2new > 85 and SpO2new < 100):
                    SpO2.append(SpO2new)

            mSpO2 = median(SpO2)
            if not isnan(mSpO2):
                self.SpO2_buffer[self.SpO2bi] = mSpO2
                self.SpO2bi = (self.SpO2bi + 1) % SPO2BUFFERSIZE
                SpO2_out = str( round(median(self.SpO2_buffer)*10)/10 )

                if (DEBUG_DATA == True):
                    self.parent.fo_SpO2data.write(' '+str(time.time())+' '+str(SpO2))
                    self.parent.fo_SpO2data.write('\n')
            else:
                SpO2_out = '--'
        else:
            systole = 'NA'
            diastole = 'NA'
            hr_out = 'NA'
            SpO2_out = 'NA'

        self.parent.pod.setData(tn, nPPG_red, nPPG_ir, systole, diastole, hr_out, SpO2_out)

        if (DEBUG_TIMING == True):
            t1 = time.time()
            self.parent.fo_pdtime.write(str(t1-t0))
            self.parent.fo_pdtime.write('\n')

    def peakdet(self, v, delta):
        """
        Converted from MATLAB script at http://billauer.co.il/peakdet.html
    
        Returns two arrays
    
        function [maxtab, mintab]=peakdet(v, delta, x)
        %PEAKDET Detect peaks in a vector
        %        [MAXTAB, MINTAB] = PEAKDET(V, DELTA) finds the local
        %        maxima and minima ("peaks") in the vector V.
        %        MAXTAB and MINTAB consists of two columns. Column 1
        %        contains indices in V, and column 2 the found values.
        %      
        %        With [MAXTAB, MINTAB] = PEAKDET(V, DELTA, X) the indices
        %        in MAXTAB and MINTAB are replaced with the corresponding
        %        X-values.
        %
        %        A point is considered a maximum peak if it has the maximal
        %        value, and was preceded (to the left) by a value lower by
        %        DELTA.
    
        % Eli Billauer, 3.4.05 (Explicitly not copyrighted).
        % This function is released to the public domain; Any use is allowed.
        """

        maxtab = []
        mintab = []

        if not isscalar(delta):
            sys.exit('Input argument delta must be a scalar')

        if delta <= 0:
            sys.exit('Input argument delta must be positive')

        mn, mx = Inf, -Inf
        mnpos, mxpos = NaN, NaN

        lookformax = True
        L = len(v)
        for i in arange(1,L+1):
            # detects heart beats better by scanning from right to left
            this = v[-i]
            if this > mx:
                mx = this
                mxpos = L-i
            if this < mn:
                mn = this
                mnpos = L-i

            if lookformax:
                if this < mx-delta:
                    maxtab.insert(0, mxpos) # lower indices are more to the left
                    mn = this
                    mnpos = L-i
                    lookformax = False
            else:
                if this > mn+delta:
                    mintab.insert(0, mnpos)
                    mx = this
                    mxpos = L-i
                    lookformax = True

        return maxtab, mintab

app = QtGui.QApplication(sys.argv)
mw = MainWindow()
mw.show()
app.exec_()
