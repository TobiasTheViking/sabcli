#!/usr/bin/env python
''' Command Line Interface for sabnzbd+

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

    COPYING: http://www.gnu.org/licenses/gpl.txt

    Copyright 2010 Tobias Ussing

    Acknowledgements:
    Meethune Bhowmick - For the original code for the 0.4 api
    Henrik Mosgaard Jensen - For testing, critique layout and usability.
'''

# export TERM=linux; sabcurses.py

import os, sys, time, httplib, curses, traceback, signal
import xml.etree.ElementTree as ElementTree
import getopt, ConfigParser
import curses.textpad
#import cProfile

VERSION="0.7-1"
APIVERSION="0.7.11"

# TextColour
class tc:
    black = '\x1B[30;49m'
    red = "\x1B[31;49m"
    green = '\x1B[32;49m'
    yellow = '\x1B[33;49m'
    blue = '\x1B[34;49m'
    magenta = '\x1B[35;49m'
    cyan = '\x1B[36;49m'
    white = '\x1B[37;49m'
    bold = '\x1B[1;49m'
    end = '\x1B[m'

class SABnzbdCore( object ):
    ''' Sabnzbd Automation Class '''
    def __init__(self, config = None):
	self.config = config
        if not self.config:
            self.config = { 'host' : 'localhost', 'port' : '8080', 
                       'username' : None, 'password;' : None,
                       'apikey' : None }, 

        self.stdscr = curses.initscr()

        curses.start_color()
	curses.use_default_colors()
        curses.noecho()   
        curses.cbreak()   
        self.stdscr.keypad(1)
        curses.curs_set(0)

	#curses.color_pair(7)
	curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_BLUE, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)
        curses.init_pair(7, curses.COLOR_CYAN, -1)
        curses.init_pair(8, curses.COLOR_WHITE, -1)

        # Public Variables
        self.size = os.popen('stty size', 'r').read().split()
	self.win = curses.newwin(int(self.size[0]), int(self.size[1]), 0, 0)
	self.pad = curses.newpad(10000, int(self.size[1])-2)
        self.fetchpath = ''
        self.servername = ''
        self.header = {}
        self.postdata = None
        self.command_status = 'ok'
        self.return_data = {}
	self.last_fetch = {'fetch': '', 'refresh': 10, 'time': time.mktime(time.localtime())}
	self.retval = ''
	self.index = [-1, -1, -1, -1, -1, -1]
	self.indexCount = [-1, -1, -1, 5, -1, 2]
	self.historyID = []
	self.scroll = { 'firstline': 0, 'totallines': 0, 'item': [], 'lastitem': -1}
	self.details = {'move': None, 'nzo_id': [], 'filename': [], 'unpackopts': [], 'priority': [], 'newname': None}
	self.speedlimit = 0
        self.url = 'http://' + self.servername + '/sabnzbd/'
	self.job_option = '3'
	self.debug = None
	self.action = 0
	self.quit = 0
	self.view = 0
	self.selection = -1
	self.statusLine = ''
	self.disk = ''
	self.speed = ''
	self.newapikey = None
	signal.signal(signal.SIGWINCH, self.sigwinch_handler)

    # Private Methods        
    def sigwinch_handler(self, n, frame):
	self.last_fetch['fetch'] = ''
        self.size = os.popen('stty size', 'r').read().split()

    def xml_to_dict(self, el):
	d={}

    	if el.text:
	    d[el.tag] = el.text
    	else:
    	    d[el.tag] = None

    	for child in el:
	    if len(child):
            	if len(child) == 1 or child[0].tag != child[1].tag:
		    d[child.tag] = self.xml_to_dict(child)
		else:
		    temp = []
                    for subitem in child:
			if subitem.text != None:
	    		    temp.append(subitem.text)
			else:
			    temp2 = self.xml_to_dict(subitem)
			    temp.append(temp2)
			d[child.tag] = { subitem.tag : temp }
	    else:
		d[child.tag] = child.text

    	return d

    def __parse_status(self, command, status_obj):
        ''' Convert web output to boolean value '''
        # Web output should only be 'ok\n' or 'error\n'
        if not status_obj:
            return False
        
        self.retval = status_obj.lower().strip('\n')
        self.command_status = self.retval

	if command == 'shutdown':
	    self.quit = 1

        if self.retval == 'ok' :
            return True  
        if self.retval.find('error') == 0 :
            return False

	if command == 'priority':
	    self.index[self.view] = int(self.retval)

	if command in ('version', 'move', 'priority', 'newapikey', 'addlocalfile', 'addurl', 'addid'):
	    return self.retval

        ''' Convert status object to python dictionary '''
	# Fix broken xml from sabnzbd
	if command == 'warnings':
            status_obj = status_obj.replace("<warnings>","<root>\n<warnings>") 
	    status_obj = status_obj.replace("</warnings>","</warnings></root>")
        if command == 'details':
            status_obj = status_obj.replace("<files>","<root>\n<files>")
            status_obj = status_obj.replace("</files>","</files></root>")

        try:
            status_obj = status_obj.replace('&', '&amp;') 
            root = ElementTree.XML(status_obj.strip())
	    self.return_data = self.xml_to_dict(root)
	    self.command_status = 'ok'

#	    if self.debug:
#		self.stdscr.addstr('')
#		for a in self.return_data.keys():
#		    self.stdscr.addstr("%s - %s\n" % ( a, self.return_data[a] ))

        except ValueError:
            self.command_status = 'error'
            return False
        return True

    def __send_request(self, command, path):
        ''' Send command to server '''
	data = ''
        try:
            conn = httplib.HTTPConnection(self.servername)
            conn.request('POST' if self.postdata else 'GET', path, self.postdata, self.header)

            try:
                response = conn.getresponse()

            except httplib.BadStatusLine:
		raise Exception

            if response.status != 200:
                msg = str(response.status) + ':' + response.reason
                raise httplib.HTTPException(msg)

            data = response.read()
            conn.close()

        except httplib.HTTPException, err:
            self.command_status = 'http://' + self.servername + path + ' -> ' + str(err)
            return False

        except:
            self.command_status = "Cannot connect to " + self.servername + path
            return False

        return data

    # Public Methods
    def setConnectionVariables(self):
        # Set Connection Variables
        self.fetchpath = '/api?apikey=' + self.config ['apikey'] + '&mode='
        self.servername = self.config['host'] + ':' + self.config['port']
        self.header = { 'User-Agent' : 'SabnzbdAutomation' }
        # Setup authentication if needed.
        if self.config['username'] and self.config['password']:
            self.postdata = 'ma_password=' + self.config['password'] + '&' +\
                              'ma_username=' + self.config['username']
            self.header['Content-type'] = 'application/x-www-form-urlencoded'
        else:
            self.postdata = None
        self.url = 'http://' + self.servername + '/sabnzbd/'

    def send_command(self, command, args = None,):
        ''' http://sabnzbdplus.wiki.sourceforge.net/Automation+Support '''
        #self.stdscr.addstr(1, 0, command)
	
        url_fragment = command

	if args == None:
	    if command in ('version', 'shutdown', 'restart'):
            	url_fragment += ''
            elif command == 'queue':
            	url_fragment += '&start=START&limit=LIMIT&output=xml'
            elif command == 'history':
                url_fragment += '&start=START&limit=LIMIT&output=xml'
            elif command == 'warnings':
            	url_fragment += '&output=xml'
            elif command == 'pause':
                url_fragment = 'pause'
            elif command == 'resume':
                url_fragment = 'resume'
            else:
            	self.stdscr.addstr('unhandled command: ' + command)
            	usage(self, 2)

	elif len(args) == 1:
            if command in ('addlocalfile', 'addurl', 'addid'):
                url_fragment += '&name=' + args[0] + '&pp=' + self.job_option
	    elif command == 'newapikey':
		if args[0] == 'confirm':	
                    url_fragment = 'config&name=set_apikey'
		else:
                    self.stdscr.addstr('unhandled command: ' + command)
		    usage(self, 2)
            elif command == 'queuecompleted':
            	url_fragment = 'queue&name=change_complete_action&value=' + args[0]
            elif command == 'pathget':
            	url_fragment = 'addlocalfile&name=' + args[0]
            elif command == 'delete':
            	url_fragment = 'queue&name=delete&value=' + args[0]
            elif command == 'details':
                url_fragment = 'get_files&output=xml&value=' + args[0]
            elif command == 'speedlimit':
            	url_fragment = 'config&name=speedlimit&value=' + args[0]
            elif command == 'autoshutdown':
            	if args not in ('0', '1'):
                    return False
            	else:
                    url_fragment += '&name=' + args[0]
            elif command == 'pause':
            	url_fragment = 'queue&name=pause&value=' + args[0]
            elif command == 'temppause':
                url_fragment = 'config&name=set_pause&value=' + args[0]
            elif command == 'resume':
                url_fragment = 'queue&name=resume&value=' + args[0]
            elif command == 'history':
		if args[0] == 'clear':
                    url_fragment += '&name=delete&value=all'
		elif args[0].find('SABnzbd_nzo_') != -1:
		    url_fragment += '&name=delete&value=' + args[0]
		else:
		    usage(self, 2)
            else:
                self.stdscr.addstr('unhandled command: ' + command)
                usage(self, 2)

        elif len(args) == 2:
	    if command == 'rename':
            	url_fragment = 'queue&name=rename&value=' + str(args[0]) + '&value2=' + str(args[1])
            elif command == 'priority':
                url_fragment = 'queue&name=priority&value=' + str(args[0]) + '&value2=' + str(args[1]) 
            elif command == 'postprocessing':
                url_fragment = 'change_opts&value=' + str(args[0]) + '&value2=' + str(args[1]) 
            elif command == 'move':
                url_fragment = 'switch&value=' + str(args[0]) + '&value2=' + str(args[1])     
            else:
                self.stdscr.addstr('unhandled command: ' + command)
                usage(self, 2)
	else:
	    self.stdscr.addstr('unhandled command: ' + command)
	    usage(self, 2)

        self.url = 'http://' + self.servername + self.fetchpath + url_fragment

	data = self.__send_request(command, str(self.fetchpath + url_fragment).replace(' ', '%20'))

	if data == False and self.debug:
	    self.stdscr.addstr(self.command_status)
	    self.stdscr.refresh()
	    time.sleep(5)

        return self.__parse_status(command, data)

    def printLine(self, segments):
	# Calculate spacing between segments in line.
        space = int(self.size[1])
	ls = len(segments)

	for segment in segments:
	    space -= len(segment)

	if ls > 1:
	    space = space / (ls-1)

	if space <= 0:
	    space = 1
	
	# Combine segments with equal spacing
	combined = ''
	for segment in segments:
            # Don't add segment if the combined line is wider than the screen
            if (len(combined) + len(segment) < int(self.size[1])):
                combined += segment + " " * space

	# Remove trailing whitespaces from above.
        return combined.strip()

    def print_diskwarnings(self):
	rd = self.return_data
        ''' Print pretty table with status info '''
        if float(rd['mbleft']) / 1024 > float(rd['diskspace2']):
            self.stdscr.addstr(1, 3, "WARNING:", curses.color_pair(2))
	    self.stdscr.addstr(" Insufficient free disk space left to finish queue.\n")
        if float(rd['mbleft']) / 1024 > float(rd['diskspacetotal2']):
            self.stdscr.addstr(1, 3, "WARNING:", curses.color_pair(2))
	    self.stdscr.addstr(" Insufficient total disk space to finish queue.\n")

    def print_queue(self):
	self.pad.clear()
	self.indexCount[self.view] = -1
	self.scroll['item'] = []

        if self.return_data['slots'] != None:
            try:
                self.return_data['slots']['slot'].keys()
                slots = [ self.return_data['slots']['slot'] ]
            except AttributeError:
                slots = self.return_data['slots']['slot']

	    self.indexCount[self.view] = len(slots) -1

	    tailLength = 0
            for each in slots:
		if tailLength < len(each['mb']):
		    tailLength = len(each['mb'])
                if not each["unpackopts"]:
                    each["unpackopts"] = 0
	    tailLength += tailLength

	    priority = { 'Low': -1, 'Normal': 0, 'High': 1, 'Force': 2, 'Repair': 3}
	    self.details['nzo_id'] = []
	    self.details['unpackopts'] = []
	    self.details['filename'] = []
	    self.details['priority'] = []

	    i = 0
	    for each in slots:
		itemp = []
		# Save details
		self.details['nzo_id'].append(each['nzo_id'])
                self.details['unpackopts'].append(int(each['unpackopts']))
		self.details['filename'].append(each['filename'])
		self.details['priority'].append(priority[each['priority']])

		# Line 1
		self.pad.addstr('   ' +each['index'], curses.color_pair(3))
		itemp.append(self.pad.getyx()[0])
                self.pad.addstr(' - ')
		if self.selection == 0 and self.index[self.view] == i:
			self.pad.addstr(each['filename'], curses.color_pair(2))
		else:
			self.pad.addstr(each['filename'])
		self.pad.addstr(' [')
                self.pad.addstr(each['avg_age'], curses.color_pair(3))
                self.pad.addstr('/')
		if self.selection == 1 and self.index[self.view] == i:
			self.pad.addstr(each['priority'], curses.color_pair(2))
		else:
			self.pad.addstr(each['priority'], curses.color_pair(3))
                self.pad.addstr('/')
		opts = ['Download', 'Repair', 'Unpack', 'Delete']
		if self.selection == 2 and self.index[self.view] == i:
			self.pad.addstr(opts[int(each['unpackopts'])], curses.color_pair(2))
		else:
			self.pad.addstr(opts[int(each['unpackopts'])], curses.color_pair(3))
                self.pad.addstr('] (')
		self.pad.addstr(each['status'], curses.color_pair(2))
		self.pad.addstr(')\n')

		# Line 2
                self.pad.addstr('      ')
                itemp.append(self.pad.getyx()[0])

		timeleft = each['timeleft']
		if len(each['timeleft']) == 7:
		    timeleft = "0" + timeleft

                tail = "%.2f / %.2f [%2.0f%%]" % ( float(each['mb'])-float(each['mbleft']), float(each['mb']), float(each['percentage']) )

		tl = len(tail)

                charsLeft = int(self.size[1]) - len(timeleft) - tl - 9 - ( tailLength + 9 - tl) - 5
                pct = (charsLeft)/100.0 * float(each['percentage'])
		progress = "="* int(pct) + ">" + " " * (charsLeft-int(pct))

		self.pad.addstr(timeleft, curses.color_pair(2))
                self.pad.addstr(' ')
                self.pad.addstr('[' + progress + ']', curses.color_pair(5) | curses.A_BOLD) #
		self.pad.addstr(' ' * ( tailLength + 10 - tl) )
                self.pad.addstr("%.2f" % (float(each['mb'])-float(each['mbleft'])), curses.color_pair(2))
                self.pad.addstr(' / ')
                self.pad.addstr("%.2f" % (float(each['mb'])), curses.color_pair(2))
                self.pad.addstr(' [')
		self.pad.addstr("%2.0f%%" % (float(each['percentage'])), curses.color_pair(2))
		self.pad.addstr(']\n\n')

		self.scroll['item'].append(itemp)
		i += 1

	self.scroll['totallines'] = self.pad.getyx()[0]

        return True

    def print_details(self):
        self.pad.clear()

	self.scroll['item'] = []
        if self.return_data['files'] != None:
            try:
                self.return_data['files']['file'].keys()
                files = [ self.return_data['files']['file'] ]
            except AttributeError:
                files = self.return_data['files']['file']

            self.indexCount[self.view] = len(files) -1

	    i = 0
	    self.pad.addstr(0, 0, '')
            for each in files:
		itemp = []
                self.pad.addstr('   ')
		itemp.append(self.pad.getyx()[0])
		self.pad.addstr(each['filename'] + '\n')

                self.pad.addstr('   ')

		itemp.append(self.pad.getyx()[0])

                #self.pad.addstr('   ' +each['index'], curses.color_pair(3))
                if each['status'] == "finished":                    
                    self.pad.addstr(" - [Status: %s] [Downloaded: %s/%s MB]\n\n" % ( each['status'], float(each['mb']) - float(each['mbleft']), float(each['mb']) ))
                else:
                    self.pad.addstr(" - [Status: ")
                    self.pad.addstr(each['status'], curses.color_pair(2))
                    self.pad.addstr("] [Downloaded: ")
                    self.pad.addstr(str(float(each['mb']) - float(each['mbleft'])), curses.color_pair(2))
                    self.pad.addstr("/%s MB]\n\n" % float(each['mb']) )

		self.scroll['item'].append(itemp)

		i += 1

	self.scroll['totallines'] = self.pad.getyx()[0]

        return True

    def print_history(self):
	self.pad.clear()
        if self.return_data['slots'] != None:
            try:
                self.return_data['slots']['slot'].keys()
                slots = [ self.return_data['slots']['slot'] ]
            except AttributeError:
                slots = self.return_data['slots']['slot']

	    self.indexCount[self.view] = len(slots)-1

	    i = 0
	    test = -1
	    self.historyID = []
            slots.reverse()
	    self.scroll['item'] = []
            for each in slots:
		itemp = []
                self.historyID.append(each['nzo_id'])

		if i < 10:
		    self.pad.addstr(' ')

                self.pad.addstr('  ' + str(i), curses.color_pair(3))
		itemp.append(self.pad.getyx()[0])
		self.pad.addstr(' - ' + each['name'] + '\n')

		i += 1
		log = ''
		stage_log = each['stage_log']
		if stage_log != None:
		    try:
			stage_log['slot'].keys()
			items = [ stage_log['slot'] ]
		    except AttributeError:
			items = stage_log['slot']

                    if not 'size' in each:
                        each['size'] = ""

		    self.pad.addstr('       [download: ' + each['size'] + '] ')

		    # If there is no data besides for download data, add an empty line.
		    if len(items) == 1:
			self.pad.addstr('\n')

		    itemp.append(self.pad.getyx()[0])
		    for item in items:
			if item['name'] == "Unpack":
                            if type(item['actions']['item']) == str:
                                data = [item['actions']['item']]
                            else:
                                data = item['actions']['item']
                            fail = 0

			    unpack = 0
			    log = []
                            for subdata in data:
                                if str.find(subdata, 'Unpacked') != -1:
				    unpack += 1
                                else:
                                    log.append(subdata)
                                    fail += 1
			    self.pad.addstr('[unpack: ')
                            if fail > 0:
				self.pad.addstr('FAIL', curses.color_pair(2))
			    elif unpack > 0:
				self.pad.addstr('OK', curses.color_pair(3))
                            self.pad.addstr('] ')

			    for logitem in log:
				self.pad.addstr("       " + logitem + '\n', curses.color_pair(2))

			elif item['name'] == "Repair":
			    if type(item['actions']['item']) == str:
				data = [item['actions']['item']]
		    	    else:
				data = item['actions']['item']
			    fail = 0

			    par2 = 0
                            log = []
		    	    for subdata in data:
		        	if str.find(subdata, 'Quick Check OK') != -1 or str.find(subdata, 'Repaired in') != -1:
				    par2 += 1
				else:
				    log.append(subdata)
			    	    fail += 1
			    self.pad.addstr('[par2: ')
			    if fail > 0:
				self.pad.addstr('FAIL', curses.color_pair(2))
			    elif par2 > 0:
				self.pad.addstr('OK', curses.color_pair(3))
			    self.pad.addstr(']')

			    self.pad.addstr('\n')

                            for logitem in log:
				if logitem.find("Repair failed") > -1:
				    part1, part2  = logitem.split("Repair failed")
				    self.pad.addstr("       " + part1)
                                    self.pad.addstr("Repair failed" + part2 + '\n', curses.color_pair(2))
				else:
				    self.pad.addstr("       " + logitem + '\n')

		    self.pad.addstr("\n")
		self.scroll['item'].append(itemp)

	    #unreverse. For some reason it will remember the reverse.
	    slots.reverse()

	self.scroll['totallines'] = self.pad.getyx()[0]

        return True

    def print_warnings(self):
	self.pad.clear()
        if self.return_data['warnings'] != None:
            try:
                self.return_data['warnings'].keys()
                slots = [ self.return_data['warnings']['warning'] ]
            except AttributeError:
                slots = self.return_data['warnings']['warning']

	    if slots[0][0] != 1:
	        slots = slots[0]
	    if type(slots) == str:
		slots = [slots]

	    self.indexCount[self.view] = len(slots)-1
	    i = 0
	    self.scroll['item'] = []
            for each in slots:
		itemp = []
		line = ''
		warning = each.split("\n")

		self.pad.addstr('   [' + warning[0] + '] ')
		itemp.append(self.pad.getyx()[0])

		if warning[1] == 'ERROR':
		    self.pad.addstr(warning[1], curses.color_pair(2))
		else:
		    self.pad.addstr(warning[1])
		wl = len(warning[0]) + len(warning[1])

		if wl < 32:
		    self.pad.addstr(" " * (32-wl))
		self.pad.addstr('|')

		temp = warning[2].replace('&lt;','<').replace('&gt;','>').split(' ')

		for item in temp:
			if len(item)+self.pad.getyx()[1] >= self.pad.getmaxyx()[1]-1:
				self.pad.addstr('\n ' + " " * 36 + " | ")
				itemp.append(self.pad.getyx()[0])
			self.pad.addstr(' ' + item.strip())

		self.pad.addstr('\n\n')
		i += 1
		self.scroll['item'].append(itemp)

	self.scroll['totallines'] = self.pad.getyx()[0]
        return True

    def print_scroll(self):
	while self.index[self.view] > self.indexCount[self.view]:
		self.index[self.view] -= 1
	index = self.index[self.view]

	# Redraw * in front of selected item.
	if index == -1:
		self.scroll['firstline'] = 0

	if len(self.scroll['item']) > 0:
		# removing *
		if self.scroll['lastitem'] > -1 and self.scroll['lastitem'] < len(self.scroll['item']):
			for i in self.scroll['item'][self.scroll['lastitem']]:
				self.pad.addstr(i, 0, ' ')

		if index > -1:
			for i in self.scroll['item'][index]:
				if i > -1:	
					if self.details['move'] == None:
						self.pad.addstr(i, 0, '*')
					else:
						self.pad.addstr(i, 0, '*', curses.color_pair(2))
					self.scroll['firstline'] = self.scroll['item'][index][0]
					self.scroll['lastitem'] = index

	# Hack to work properly with print_warnings(only one line per item apparantly causes problems, this fixes it).
#	if self.scroll['totallines']-int(self.size[0]) <= 0:
#		self.scroll['totallines'] = self.scroll['totallines'] + 1 

	if self.scroll['totallines'] >= int(self.size[0])-1:
		if self.scroll['totallines']-int(self.size[0]) <= 0:
			self.scroll['totallines'] = self.scroll['totallines'] + 1

		i = 0
		temp = -1
		while i < int(self.size[0])-5 :
		    percentage = self.scroll['firstline'] * 100 / (self.scroll['totallines']-2)
            	    pct = i * 100 / ( int(self.size[0]) - 7 )

            	    if percentage < 5: percentage = 4

		    if temp == -1:
			if pct > percentage - 5 and pct < percentage + 5:
			    temp = 3

		    if temp > 0:
                	self.stdscr.addstr(i+4, int(self.size[1])-1, '#')
			temp = temp -1
            	    else:
                	self.stdscr.addstr(i+4, int(self.size[1])-1, '|')

            	    i += 1

#	if self.debug:
#	        self.stdscr.addstr(1, 97, 'test: ' + str(self.scroll['firstline']) + ' > ' + str(self.scroll['totallines']-int(self.size[0])))

        # If total lines is less than the size of the window, then show the entire window, always.
        if self.scroll['totallines'] < int(self.size[0])-3:
                self.scroll['firstline'] = 0

        # If firstline is less than halfway down the screen, print everything.
        if self.scroll['firstline'] < (int(self.size[0]))/2:     
                self.scroll['firstline'] = 0

	# Makes sure there are no empty lines in the bottom of the screen.
	elif self.scroll['firstline']-(self.scroll['totallines']-int(self.size[0])) > (int(self.size[0]))/2:
		self.scroll['firstline'] = self.scroll['totallines'] - int(self.size[0])+4
	else:
		self.scroll['firstline'] -= (int(self.size[0])-7)/2

    def print_help(self):
	self.stdscr.clear()
	self.pad.clear()
	self.last_fetch['fetch'] = ''
	self.scroll['item'] = []
	self.stdscr.addstr(2, 0, 'Keymapping:\n')
	self.stdscr.addstr(3, 0, '-' * int(self.size[1] + '\n'))

	self.pad.addstr('\n')
        self.pad.addstr('|' + '-' * 45 + '|' + '\n')
        self.pad.addstr('| General and Navigation \t\t      |\n')
        self.pad.addstr('|' + '-' * 45 + '|' + '\n')
        self.pad.addstr('| 1\t\tQueue screen\t\t      |\n')
        self.pad.addstr('| 2\t\tHistory screen\t\t      |\n')
        self.pad.addstr('| 3\t\tWarnings screen\t\t      |\n')
        self.pad.addstr('| 4\t\tMore screen\t\t      |\n')
        self.pad.addstr('| 5/?\t\tHelp screen\t\t      |\n')
        self.pad.addstr('| Q\t\tQuit\t\t\t      |\n')
        self.pad.addstr('| S\t\tShutdown\t\t      |\n')
        self.pad.addstr('| R\t\tRestart\t\t\t      |\n')
        self.pad.addstr('| Up/Down\tSelect item/setting\t      |\n')
        self.pad.addstr('| PageUp/Down\tSelect item (jump 5)\t      |\n')
        self.pad.addstr('| Home/End\tJump to first or last item    |\n')
        self.pad.addstr('| Enter\t\tAccess/Apply changes\t      |\n')
        self.pad.addstr('| Del/Backspace\tDelete (all* or selected)     |\n')
        self.pad.addstr('| \t\t*only on history screen       |\n')
        self.pad.addstr('|' + '-' * 45 + '|' + '\n')
        self.pad.addstr('\n')

	i = 1
        self.pad.addstr(i + 0, 48, '|' + '-' * 45 + '|' + '\n')
        self.pad.addstr(i + 1, 48, '| Queue view \t\t\t\t      |\n')
        self.pad.addstr(i + 2, 48, '|' + '-' * 45 + '|' + '\n')
        self.pad.addstr(i + 3, 48, '| Left/Right\tAccess settings\t\t      |\n')
        self.pad.addstr(i + 4, 48, '| m\t\tMove (select and place)       |\n')
        self.pad.addstr(i + 5, 48, '| r\t\tResume (all or selected)      |\n')
        self.pad.addstr(i + 6, 48, '| p\t\tPause (all or selected)       |\n')
	self.pad.addstr(i + 7, 48, '| d\t\tEnter/Exit details view       |\n')
#        self.pad.addstr(i + 9, 48, '| h/j/k/l\tSet priority\t\t      |\n')
#        self.pad.addstr(i + 10, 48, '| H/J/K/L\tSet post processing\t      |\n')
        self.pad.addstr(i + 8, 48, '|' + '-' * 45 + '|' + '\n')

	self.scroll['firstline'] = 0
	self.scroll['totallines'] = self.pad.getyx()[0]

    def print_more(self):
	self.stdscr.clear()
	self.pad.clear()
	self.scroll['item'] = []
	self.run_commands('version',  None)

	if APIVERSION != self.retval:
            self.stdscr.addstr(1, 3, "WARNING:", curses.color_pair(2))
            self.stdscr.addstr(" API version mismatch between SABCurses (%s) and daemon (%s)" % (APIVERSION, self.retval ) )

        self.stdscr.addstr(2, 3, 'Option - Description\n')
	version = 'SABCurses: ' + VERSION
	self.stdscr.addstr(2, int(self.size[1]) - len(version), version)
        self.stdscr.addstr(3, 0, '-' * int(self.size[1] + '\n'))
	self.stdscr.addstr('\n')

	if self.index[self.view] == -1:
	    self.scroll['firstline'] = 0

	self.pad.addstr('   Add file or link')
	self.pad.addstr(0, 35, '- Add a nzb file location or URL to sabnzbd+')

	self.pad.addstr(1, 8, 'URL or file :\n\n')

        self.pad.addstr('   Add newzbin')
	self.pad.addstr(3, 35, '- Add a nzb from Newzbin.com to sabnzbd+ by entering a Newzbin Id')

        self.pad.addstr(4, 8, 'Newzbin ID :\n\n')

        self.pad.addstr('   Speed limit: ' + str(self.speedlimit))
	self.pad.addstr(6, 35, '- Limit the download speed of sabnzbd+ (Useful to avoid network congestion)')
	self.pad.addstr(7, 8, 'New limit :\n\n')

        self.pad.addstr('   Set temporary pause')
	self.pad.addstr(9, 35, '- Pause queue for X minutes\n')
	self.pad.addstr(10, 8, 'Duration :\n\n')

        self.pad.addstr('   Set queue completed script')
	self.pad.addstr(12, 35, '- Enter path to a local shell script that will be executed once sabnzbd+ finishes its queue\n\n')
	self.pad.addstr(13, 8, 'Path :\n\n')

        self.pad.addstr("   Generate newapikey")
	self.pad.addstr(15, 35, '- Change the current API Key of sabnzbd+ (WARNING this will disable use of SABCurses)\n')
	self.pad.addstr(16, 8, 'Are you Sure? :\n')
	self.pad.addstr(16, 35, "- Write 'yes' to confirm")

	self.scroll['item'] = [[0, 1], [3, 4], [6, 7], [9, 10], [12, 13], [15,16]]
	self.scroll['totallines'] = self.pad.getyx()[0]

        return True

    def run_commands(self, command, command_arg = None):
	data = False
	cached = False
        if self.last_fetch['fetch'] == str(command) + str(command_arg) and time.mktime(time.localtime()) - self.last_fetch['time'] < self.last_fetch['refresh']:
            data = True
	    cached = True
        else:
            try:
                self.stdscr.addstr(int(self.size[0])-1, 0, ' ' * len(self.disk))
                self.stdscr.addstr(int(self.size[0])-1, 0, 'Fetching...')
                if self.debug and False:
                    self.stdscr.addstr(' ' + self.url)
                self.stdscr.refresh()
            except:
                pass

            self.last_fetch['time'] = time.mktime(time.localtime())
            self.last_fetch['fetch'] = str(command) + str(command_arg)
	    data = self.send_command(command, command_arg)

        if data:
            if command == 'queue':
		self.stdscr.clear()
		self.print_diskwarnings()
		self.stdscr.addstr(2, 3, self.printLine(['   # - Filename [Age/Priority/Options] (Status)', 'Downloaded/Total (MB) [pct]   ']))
		self.stdscr.addstr(3, 0, '-' * int(self.size[1]) + '\n')

		if not cached or self.selection == -2 or self.selection > -1:
		    self.print_queue()
		    if self.selection == -2:
			self.selection = -1
            elif command == 'history':
                if command_arg == None:
		    self.stdscr.clear()
		    self.print_diskwarnings()
		    self.stdscr.addstr(2, 3, '# - Filename')
		    self.stdscr.addstr(3, 0, '-' * int(self.size[1]))
		    if not cached:
			self.print_history()
                else:
		    if self.debug:
                        self.stdscr.addstr(1, 0, 'History Cleared\n\n')
            elif command == 'details':
		self.stdscr.clear()
		self.stdscr.addstr(2, 3, 'Details for ' + self.details['filename'][self.index[0]] + '\n')
		self.stdscr.addstr('-' * int(self.size[1]))
		self.stdscr.addstr('\n')
		if not cached:
		    self.print_details()
            elif command == 'warnings':
		''' Print pretty table with status info '''
		self.stdscr.clear()
		self.stdscr.addstr(2, 3, '[Date/Timestamp         ] Type     | System message\n')
		self.stdscr.addstr(3, 0, '-' * int(self.size[1]))
		if not cached:
                    self.print_warnings()
            elif command == 'priority':
                if self.debug:
                    self.stdscr.addstr('New position in queue: ' + self.retval)
                    self.command_status = self.command_status.replace(self.retval, "ok\n");
            elif command == 'move':
                value = self.retval.split(' ')
                if self.debug:
                    self.stdscr.addstr('New position in queue: ' + value[0])
                    self.command_status = self.command_status.replace(self.retval, "ok");
	    elif command == 'newapikey':
		self.newapikey = self.command_status
            elif command in ('shutdown', 'restart', 'queuecompleted'):
                self.stdscr.addstr(command + ' -> ' + self.command_status)
            elif command in ('addurl', 'addlocalfile', 'addid', 'delete', 'pause', 'resume', 'rename', 'postprocessing', 'version', 'speedlimit'):
                if self.debug:
                    self.stdscr.addstr(command + ' -> ' + self.command_status)
            else:
                self.stdscr.addstr('No command run: ' + self.url)

    def display(self):
	self.stdscr.addstr(0, 0, '')
        self.pad.addstr(0, 0, '')

	if self.view == 1: 
	    if self.action == 6:
		if self.index[self.view] == -1:
		    self.stdscr.addstr(0, int(self.size[1])-60, 'all')
                    self.run_commands('history', ['clear'])
		else:    
		    self.run_commands('history', [self.historyID[self.index[self.view]]])
		self.action = 0
	    if self.action == 0:
		self.run_commands('history', None)
	elif self.view == 2: self.run_commands('warnings', None)
	elif self.view == 3: 
	    if self.action == 0:
		self.print_more()
        elif self.view == 4: self.print_help()
        elif self.view == 5:   
	    if self.action == 10:
		    self.run_commands('rename', [self.details['nzo_id'][self.index[0]], self.details['newname']])
		    self.details['filename'][self.index[0]] = self.details['newname']
		    self.details['newname'] = None
		    self.view = 0
		    self.action = 0
		    self.last_fetch['fetch'] = ''
            if self.action == 11:         
                    self.index[self.view] = -1
                    self.run_commands('priority', [self.details['nzo_id'][self.index[0]], self.details['priority'][self.index[0]]])
		    self.action = 0
		    self.view = 0
		    self.last_fetch['fetch'] = ''
            if self.action == 12:
                    self.run_commands('postprocessing', [self.details['nzo_id'][self.index[0]], self.details['unpackopts'][self.index[0]]])
		    self.action = 0
		    self.view = 0
		    self.last_fetch['fetch'] = ''
            if self.action == 0:
                if self.index[0] > -1:
                    self.run_commands('details', [self.details['nzo_id'][self.index[0]]])
	elif self.action == 7:
	    self.run_commands('shutdown', None)
	elif self.action == 8:
	    self.run_commands('restart', None)
	elif self.action == 9:
	    if self.details['move'] == None:
	        self.details['move'] = self.details['nzo_id'][self.index[self.view]]
	    else:
	        self.run_commands('move', [self.details['move'], self.details['nzo_id'][self.index[self.view]]])
	        self.details['move'] = None
	    self.action = 0

	if self.view == 0:
            if self.action == 10:
                    self.run_commands('rename', [self.details['nzo_id'][self.index[0]], self.details['newname']])
                    self.details['filename'][self.index[0]] = self.details['newname']
                    self.details['newname'] = None
                    self.action = 0
                    self.last_fetch['fetch'] = ''
            if self.action == 11:
                    self.run_commands('priority', [self.details['nzo_id'][self.index[0]], self.details['priority'][self.index[0]]])
                    self.action = 0
                    self.last_fetch['fetch'] = ''
            if self.action == 12:
                    self.run_commands('postprocessing', [self.details['nzo_id'][self.index[0]], self.details['unpackopts'][self.index[0]]])
                    self.action = 0
                    self.last_fetch['fetch'] = ''

            if self.action == 4:
                if self.index[self.view] == -1:
                    self.run_commands('pause', None)
                else:
                    self.run_commands('pause', [self.details['nzo_id'][self.index[self.view]]])
                self.action = 0

            elif self.action == 5:
                if self.index[self.view] == -1:
                    self.run_commands('resume', None)
                else:
                    self.run_commands('resume', [self.details['nzo_id'][self.index[self.view]]])
                self.action = 0

            elif self.action == 6:
                if self.index[self.view] != -1:
                    self.run_commands('delete', [self.details['nzo_id'][self.index[self.view]]])
                self.action = 0

            if self.action == 0:
                 self.run_commands('queue', None)

        self.pad.addstr(0, 0, '')
        self.printMenu()
        if self.debug:
		self.stdscr.addstr(0, 55, 'index: ' + str(self.index[self.view]) + ' count: ' + str(self.indexCount[self.view]) +' action: ' + str(self.action) + ' view: ' + str(self.view) + ' selection: ' + str(self.selection))

	if self.view in ( 0, 1):
		self.statusLine = self.status().strip()

        try:
            self.stdscr.addstr(int(self.size[0])-1, 0, self.statusLine)
        except:
            pass

        try:
            self.stdscr.addstr(0, int(self.size[1]) - 7 - len(self.speed), 'Speed: ')
        except:
            pass

        try:
            self.stdscr.addstr(0, int(self.size[1]) - len(self.speed), self.speed, curses.color_pair(7))
        except:
            pass

        self.print_scroll()
        self.stdscr.noutrefresh()
	top = 4
#	if self.view == 5:
#		top = 6
        try:
            self.pad.noutrefresh(self.scroll['firstline'], 0, top, 0, int(self.size[0])-2, int(self.size[1])-2)
        except:
            pass
        curses.doupdate()

    def status(self):
	rd = self.return_data
        self.speed = "--"
        
        if ( not rd ):
            return "Server not responding."

        if rd['paused'] == 'True':
            self.speed = "Paused"
        else:
            self.speed = "%.2f kb/s" %  float(rd['kbpersec'])

	self.speedlimit = rd['speedlimit']

	statusLine = ''
	update = '[Updated: ' + time.strftime("%H:%M:%S", time.localtime(self.last_fetch['time'])) + '] '
	if self.debug and False:
		self.stdscr.addstr(int(self.size[0])-1, 0, self.url)
	else:
		queuetransfer = ''
		if 'total_size' in rd:
			# History view
			queuetransfer = str('[Transfered: %s / %s / %s]' %  \
                	( rd['total_size'], rd['month_size'], rd['week_size']))
		else:
			# Queue view or pre 0.5.2 view
			queuetransfer = str('[Queue: %.2f / %.2f GB (%2.0f%%)] [Up: %s]' % \
                ( ( float(rd['mb']) -
                    float(rd['mbleft']) ) / 1024 ,
                  float(rd['mb']) / 1024,
                  100*( float(rd['mb']) -
                    float(rd['mbleft']))/(float(rd['mb'])+0.01), rd['uptime']))
	self.disk = '[Disk: %.2f / %.2f GB]' % \
                        ( float(rd['diskspace2']), float(rd['diskspacetotal2']))

	return self.printLine([self.disk, queuetransfer, update])

    def printMenu(self):
        self.stdscr.addstr(0, 0, '')
        if self.view in (0, 5):
            self.stdscr.addstr('[1-Queue]', curses.color_pair(7))
        else:
            self.stdscr.addstr('[1-Queue]')
            
        if self.view == 1:
            self.stdscr.addstr(' [2-History]', curses.color_pair(7))
        else:
            self.stdscr.addstr(' [2-History]')
            
        if self.view == 2:
            self.stdscr.addstr(' [3-Warnings]', curses.color_pair(7))
        else:
            self.stdscr.addstr(' [3-Warnings]')
            
        if self.view == 3:
            self.stdscr.addstr(' [4-More]', curses.color_pair(7))
        else:
            self.stdscr.addstr(' [4-More]')
            
        if self.view == 4:
            self.stdscr.addstr(' [5-Help]', curses.color_pair(7))
        else:
            self.stdscr.addstr(' [5-Help]')

def usage(sabnzbd, exitval):
    ''' Usage '''
    msg = sys.argv[0].split('/').pop()
    msg += " " + tc.cyan + "<command> <args>" + tc.end + "\n\n"
    msg += "Compatible with SABnzbd+: " + APIVERSION + "\n\n"
    msg += "Commands:\n\tpause " + tc.cyan + "[id]" + tc.end + "\n\tresume " + tc.cyan + "[id]" + tc.end + "\n\tshutdown\n\trestart\n\tversion\n\tqueue\t\t\t\t(watchable)\n\twarnings\t\t\t(watchable)\n\tdetails " + tc.cyan + "<id>" + tc.end + "\t\t\t(watchable)\n\tmove " + tc.cyan + "<id> <new position>" + tc.end + " \n"
    msg += "\thistory " + tc.cyan + "[clear]" + tc.end + "\t\t\t(watchable)\n\tnewapikey " + tc.cyan + "<confirm>" + tc.end + "\n\tspeedlimit " + tc.cyan + "<value>" + tc.end + "\n\tnewzbin " + tc.cyan + "<id>" + tc.end + "\n\taddurl " + tc.cyan + "<nzb url>" + tc.end + "\n\tpathget " + tc.cyan + "<nzb path>" + tc.end + "\n\ttemppause " + tc.cyan + "<minutes>" + tc.end + "\n"
    msg += "\trename " + tc.cyan + "<id> <newname>" + tc.end + "\n\tdelete " + tc.cyan + "<id>" + tc.end + "\t\t\t| all = clear queue. Multiple id's can be given\n\tpriority " + tc.cyan + "<id> <value>" + tc.end + "\t\t| -1 = Low, 0 = Normal, 1 = High, 2 = Force\n"
    msg += "\tpostprocessing " + tc.cyan + "<id> <value>" + tc.end + "\t| 0 = Skip, 1 = Repair, 2 = Unpack, 3 = Delete\n"
    msg += "\tqueuecompleted " + tc.cyan + "<path to script>" + tc.end + "\t| implemented, not confirmed\n";
    msg += "\nArguments:\n\t-h [--help]\t\t\tHelp screen\n\t-j [--job-option=3]\t\tSet job-option\n\t-H [--hostname=localhost]\tHostname\n\t-P [--port=8080]\t\tPort\n"
    msg += "\t-u [--username=user]\t\tUsername\n\t-p [--password=pass]\t\tPassword\n\t-a [--apikey=15433acd...]\tApikey\n\t-w [--watch=X]\t\t\tRerun command every X seconds\n\t\t\t\t\tStandard action is 'queue'\n\t\t\t\t\tCan watch all commands marked (watchable)\n"
    msg += "\nEnvironment variables:\n\tSABCLICFG=~/.nzbrc (default)\n\tDEBUG=1\t\t\t\t| Enable debug\n"

    sabnzbd.stdscr.addstr(msg + '\n')
    sys.exit(exitval)

def parse_options(sabnzbd, options):
    ''' Parse Cli options '''
    default_opts = ("hj:H:P:u:p:a:w:" , ["help" , "job-option=", "hostname=", "port=", "username=", "password=", "apikey=", "watch="])
    command = None
    command_args = None

    try:
        opt , args = getopt.getopt(options, default_opts[0], default_opts[1])
    except getopt.GetoptError:
        usage(self, OB2)
    for option , arguement in opt:
        if option in ("-h", "--help"):
            usage(self, 2)
        elif option in ("-j", "--job-option"):
            self.job_option = str(arguement)
        elif option in ("-H", "--hostname"):
            sabnzbd.config['host'] = str(arguement)
        elif option in ("-P", "--port"):
            sabnzbd.config['port'] = str(arguement)
        elif option in ("-u", "--username"):
            sabnzbd.config['password'] = str(arguement)
        elif option in ("-p", "--password"):
            sabnzbd.config['password'] = str(arguement)
        elif option in ("-a", "--apikey"):
            sabnzbd.config['apikey'] = str(arguement)

def parse_config(config):
    ''' Parse config file for server info '''
    parser = ConfigParser.ConfigParser()
    config_dict = {}
    try:
        config_file = open(config)
        parser.readfp(config_file)
        config_file.close()
    except IOError:
	usage(self, 1)
        sys.stderr.write('Unable to open ' + config + '\n')


    try:
        for each in ('host', 'port', 'username', 'password', 'apikey'):
            config_dict[each] = parser.get('server', each)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        sys.stderr.write('Unable to parse ' + config + '\n')
        sys.stderr.write('Format should be:\n')
        sys.stderr.write('[server]\n')
        sys.stderr.write('host = <sabnzbd server>\n')
        sys.stderr.write('port = <sabnzbd port>\n')
        sys.stderr.write('username = <sabnzbd name> | None\n')
        sys.stderr.write('password = <sabnzbd password> | None\n') 
        sys.stderr.write('apikey = <sabnzbd apikey> | None\n') 
        usage(self, 1)

    return config_dict

def editfield(editwin):
    curses.curs_set(1)
    newname = curses.textpad.Textbox(editwin, insert_mode = True).edit().strip()
    curses.curs_set(0)

    return newname

def restorescreen(sabnzbd):
    # Cleanup of exit for FreeBSD.
    #sabnzbd.stdscr.addstr(int(sabnzbd.size[0])-1, 0, " " * (int(sabnzbd.size[1])-1) )                                                                    
    #sabnzbd.stdscr.refresh()
    curses.curs_set(1)
    curses.nocbreak();
    sabnzbd.stdscr.keypad(0);
    curses.echo()
    curses.endwin()
    sys.stderr.write(sabnzbd.size[0] + " - " + sabnzbd.size[1] + "\n")

def mainloop(sabnzbd):
        sabnzbd.printMenu()
        command = 0
        sabnzbd.action = 0
	help = -1
        while sabnzbd.quit == 0:
            sabnzbd.display()
	    delay = int((sabnzbd.last_fetch['refresh'] - ( time.mktime(time.localtime()) - sabnzbd.last_fetch['time'] )) * 1000 + 100)
	    if delay > 10100:
		delay = 10100
	    if sabnzbd.quit:
		delay = 100;
	    sabnzbd.stdscr.timeout(delay)
            c = sabnzbd.stdscr.getch()
	    sabnzbd.action = 0
            if help != -1:
                sabnzbd.view = help
                help = -2
            if c == ord('Q'): sabnzbd.quit = 1 # quit
            elif c == ord('1'): sabnzbd.view = 0 # queue
            elif c == ord('2'): sabnzbd.view = 1 # history
            elif c == ord('3'): sabnzbd.view = 2 # warnings
            elif c == ord('4'): sabnzbd.view = 3 # more
            elif c == ord('5'): sabnzbd.view = 4 # help
	    elif c == ord('?'):
		if help == -1: help = sabnzbd.view; sabnzbd.view = 4; # help
            elif c == ord('p'): sabnzbd.action = 4 # pause
            elif c == ord('r'): sabnzbd.action = 5 # resume
            elif c in ( 330, 263, 127): sabnzbd.action = 6 # delete #263 (backspace linux) #127 (backspace freebsd) 330 (delete freebsd/linux)
            elif c == ord('S'): sabnzbd.action = 7 # shutdown
            elif c == ord('R'): sabnzbd.action = 8 # restart
	    elif c == ord('m'): sabnzbd.action = 9 # move
            elif c == ord('h') and sabnzbd.view == 0:
                sabnzbd.view = 5
                sabnzbd.action = 11
                sabnzbd.details['priority'][sabnzbd.index[sabnzbd.view]] = -1 # priority
            elif c == ord('j') and sabnzbd.view == 0:
                sabnzbd.view = 5
                sabnzbd.action = 11
                sabnzbd.details['priority'][sabnzbd.index[sabnzbd.view]] = 0 # priority
            elif c == ord('k') and sabnzbd.view == 0:
                sabnzbd.view = 5
                sabnzbd.action = 11
                sabnzbd.details['priority'][sabnzbd.index[sabnzbd.view]] = 1 # priority
            elif c == ord('l') and sabnzbd.view == 0 and sabnzbd.index[sabnzbd.view] != -1:
                sabnzbd.view = 5
                sabnzbd.action = 11
                sabnzbd.details['priority'][sabnzbd.index[sabnzbd.view]] = 2 # priority
            elif c == ord('H') and sabnzbd.view == 0 and sabnzbd.index[sabnzbd.view] != -1:
                sabnzbd.view = 5
                sabnzbd.action = 12
                sabnzbd.details['unpackopts'][sabnzbd.index[sabnzbd.view]] = 0 # postprocessing
            elif c == ord('J') and sabnzbd.view == 0 and sabnzbd.index[sabnzbd.view] != -1:
                sabnzbd.view = 5
                sabnzbd.action = 12
                sabnzbd.details['unpackopts'][sabnzbd.index[sabnzbd.view]] = 1 # postprocessing
            elif c == ord('K') and sabnzbd.view == 0 and sabnzbd.index[sabnzbd.view] != -1:
                sabnzbd.view = 5
                sabnzbd.action = 12
                sabnzbd.details['unpackopts'][sabnzbd.index[sabnzbd.view]] = 2 # postprocessing
            elif c == ord('L') and sabnzbd.view == 0 and sabnzbd.index[sabnzbd.view] != -1:
                sabnzbd.view = 5
                sabnzbd.action = 12
                sabnzbd.details['unpackopts'][sabnzbd.index[sabnzbd.view]] = 3 # postprocessing
	    elif c == ord('d'):
                if sabnzbd.view == 0 and sabnzbd.index[sabnzbd.view] > -1:
                    sabnzbd.view = 5
                    sabnzbd.index[sabnzbd.view] = -1
		elif sabnzbd.view == 5:
		    sabnzbd.view = 0
	# Curser up
            elif c == 259: 
		if sabnzbd.view in ( 0, 1, 2, 3, 4, 5 ) and sabnzbd.selection == -1:
                    if sabnzbd.index[sabnzbd.view] > -1:
                        sabnzbd.index[sabnzbd.view] = sabnzbd.index[sabnzbd.view] - 1
                    else:
                        sabnzbd.index[sabnzbd.view] = sabnzbd.indexCount[sabnzbd.view] 
		if sabnzbd.view == 0 and sabnzbd.selection == 1 and sabnzbd.details['priority'][sabnzbd.index[0]] < 2:
			sabnzbd.details['priority'][sabnzbd.index[0]] += 1
			sabnzbd.action = 11
                if sabnzbd.view == 0 and sabnzbd.selection == 2 and sabnzbd.details['unpackopts'][sabnzbd.index[0]] > 0:
                        sabnzbd.details['unpackopts'][sabnzbd.index[0]] -= 1
                        sabnzbd.action = 12
	# Curser down
            elif c == 258: 
            	if sabnzbd.view in ( 0, 1, 2, 3, 4, 5 ) and sabnzbd.selection == -1:
                    if sabnzbd.index[sabnzbd.view] < sabnzbd.indexCount[sabnzbd.view]:
                        sabnzbd.index[sabnzbd.view] = sabnzbd.index[sabnzbd.view] + 1
                    else:
                        sabnzbd.index[sabnzbd.view] = -1
		if sabnzbd.view == 0 and sabnzbd.selection == 1 and sabnzbd.details['priority'][sabnzbd.index[0]] > -1:
			sabnzbd.details['priority'][sabnzbd.index[0]] -= 1
			sabnzbd.action = 11
                if sabnzbd.view == 0 and sabnzbd.selection == 2 and sabnzbd.details['unpackopts'][sabnzbd.index[0]] < 3:
                        sabnzbd.details['unpackopts'][sabnzbd.index[0]] += 1
                        sabnzbd.action = 12
	# Curser left
            elif c == 260: 
            	if ( sabnzbd.view == 0 and sabnzbd.index[sabnzbd.view] > -1 ) or ( sabnzbd.view == 5 and sabnzbd.index[sabnzbd.view] == -1 ):
                    sabnzbd.action = 0
                    sabnzbd.view = 0
		    if sabnzbd.selection > -1:
			sabnzbd.selection -= 1
		    if sabnzbd.selection == -1:
			sabnzbd.selection = -2
            	if sabnzbd.view == 5 and sabnzbd.index[sabnzbd.view] == 0:
		    if sabnzbd.details['priority'][sabnzbd.index[0]] > -1:
			sabnzbd.details['priority'][sabnzbd.index[0]] -= 1
                if sabnzbd.view == 5 and sabnzbd.index[sabnzbd.view] == 1: 
		    if sabnzbd.details['unpackopts'][sabnzbd.index[0]] > 0:
			sabnzbd.details['unpackopts'][sabnzbd.index[0]] -= 1
	# Curser right
            elif c == 261: 
            	if sabnzbd.view == 0 and sabnzbd.index[sabnzbd.view] > -1:
		    if sabnzbd.selection < 2:
			sabnzbd.selection += 1
                if sabnzbd.view == 5 and sabnzbd.index[sabnzbd.view] == 0: 
                    if sabnzbd.details['priority'][sabnzbd.index[0]] < 2:
                        sabnzbd.details['priority'][sabnzbd.index[0]] += 1
                if sabnzbd.view == 5 and sabnzbd.index[sabnzbd.view] == 1:
                    if sabnzbd.details['unpackopts'][sabnzbd.index[0]] < 3:
                        sabnzbd.details['unpackopts'][sabnzbd.index[0]] += 1
	# Page up
            elif c == 339: 
            	if sabnzbd.index[sabnzbd.view] -5 > -1:
                    sabnzbd.index[sabnzbd.view] = sabnzbd.index[sabnzbd.view] - 5
                else:
                    sabnzbd.index[sabnzbd.view] = -1
	# Page down
            elif c == 338: 
            	if sabnzbd.index[sabnzbd.view] == -1:
		    if sabnzbd.indexCount[sabnzbd.view] >= 5:
			sabnzbd.index[sabnzbd.view] = 5
		    else:
			sabnzbd.index[sabnzbd.view] = sabnzbd.indexCount[sabnzbd.view]
            	elif sabnzbd.index[sabnzbd.view] +5 <= sabnzbd.indexCount[sabnzbd.view]:
                    sabnzbd.index[sabnzbd.view] = sabnzbd.index[sabnzbd.view] + 5
            	else:
                    sabnzbd.index[sabnzbd.view] = sabnzbd.indexCount[sabnzbd.view] 

        # Home
            elif c == 262:
		sabnzbd.index[sabnzbd.view] = -1
        # Home   
            elif c in ( 360, 385 ):
                sabnzbd.index[sabnzbd.view] = sabnzbd.indexCount[sabnzbd.view]

	# Space
	    elif c == 32:
                if sabnzbd.view == 0:
                    if sabnzbd.selection == -1:
                        sabnzbd.action = 9
	# Enter
            elif c == 10:
		if sabnzbd.view == 0:
		    if sabnzbd.selection == 0:
			line = 4 + sabnzbd.scroll['item'][sabnzbd.index[sabnzbd.view]][0]
			editwin = sabnzbd.win.subwin(1, int(sabnzbd.size[1])-33, line, 7)
			editwin.addstr(0, 0, ' ' * ( int(sabnzbd.size[1]) - 34 ) )
                        editwin.addstr(0, 0, sabnzbd.details['filename'][sabnzbd.index[0]][:( int(sabnzbd.size[1]) - 34 )])
			newname = editfield(editwin)
			if newname != '':
			    sabnzbd.details['newname'] = newname
			    sabnzbd.action = 10

                if sabnzbd.view == 5 and sabnzbd.index[sabnzbd.view] == 0:
                    sabnzbd.action = 11

                if sabnzbd.view == 5 and sabnzbd.index[sabnzbd.view] == 1:
                    sabnzbd.action = 12

            	if sabnzbd.view == 5 and sabnzbd.index[sabnzbd.view] == 2:	
		    editwin = sabnzbd.win.subwin(1, int(sabnzbd.size[1])-33, 4, 33)
		    editwin.addstr(0, 0, ' ' * ( int(sabnzbd.size[1]) - 34 ) )
		    editwin.addstr(0, 0, sabnzbd.details['filename'][sabnzbd.index[0]])

		    newname = editfield(editwin)

		    if newname != '':
			sabnzbd.details['newname'] = newname
			sabnzbd.action = 10

		# More view
		if sabnzbd.view == 3:
		    posy = 0
		    posx = 0
		    width = int(sabnzbd.size[1])-40
		    if sabnzbd.index[sabnzbd.view] == 0:
			posy = 5
			posx = 22
		    elif sabnzbd.index[sabnzbd.view] == 1:
			posy = 8
			posx = 21
                    elif sabnzbd.index[sabnzbd.view] == 2:
                        posy = 11
                        posx = 20
			width = 7
                    elif sabnzbd.index[sabnzbd.view] == 3:
                        posy = 14
                        posx = 19
			width = 5
                    elif sabnzbd.index[sabnzbd.view] == 4:
                        posy = 17
                        posx = 15
                    elif sabnzbd.index[sabnzbd.view] == 5:
                        posy = 20
                        posx = 24
			width = 4
			
		    editwin = sabnzbd.win.subwin(1, width, posy , posx)
		    editwin.addstr(0, 0, ' ' * ( width - 1 ) )
		    editwin.addstr(0, 0, '')
		    data = editfield(editwin)
		    sabnzbd.action = 0

		    if sabnzbd.index[sabnzbd.view] == 0:
			# Add file or link
			if data.find('http') > -1:
			    sabnzbd.run_commands('addurl', [data])
			else:
			    sabnzbd.run_commands('addlocalfile', [data])

		    elif sabnzbd.index[sabnzbd.view] == 1:
			# add newzbin
			sabnzbd.run_commands('addid', [data])

		    elif sabnzbd.index[sabnzbd.view] == 2:
			# set speed limit
			try:
			    if data == '':
				data = '0'
			    if data == '0':
				sabnzbd.speedlimit = None
			    else:
				sabnzbd.speedlimit = int(data)
			    sabnzbd.run_commands('speedlimit', [data])
			except ValueError:
			    sabnzbd.speedlimit = None

		    elif sabnzbd.index[sabnzbd.view] == 3:
			# set temporary pause
			sabnzbd.run_commands('temppause', [data])

		    elif sabnzbd.index[sabnzbd.view] == 4:
			# queue complete script
                        sabnzbd.run_commands('queuecompleted', [data])

		    elif sabnzbd.index[sabnzbd.view] == 5:
			if data == 'yes':
			    sabnzbd.run_commands('newapikey', ['confirm'])
			    sabnzbd.quit = 1 # quit

            elif c != -1:
		if sabnzbd.debug:
		    sabnzbd.stdscr.addstr(1, 0, 'Captured key: ' + str(c))
		    sabnzbd.stdscr.refresh()
		    time.sleep(2)

	    if help == -2:
		help = -1

def main():
    ''' Command line front end to sabnzbd+ '''
    configFile = os.environ.get("SABCLICFG");
    if configFile == None:
        configFile = os.environ['HOME'] + "/.nzbrc"
    commands = None
            
    if not os.path.exists(configFile):
        sys.stderr.write('\nUnable to open ' + configFile + '\n\n')
    else:   
        config_dict = parse_config(configFile)
        sabnzbd = SABnzbdCore(config_dict)
        sabnzbd.debug = os.environ.get("DEBUG");
	parse_options(sabnzbd, sys.argv[1:])
        sabnzbd.setConnectionVariables()

	try:
	    mainloop(sabnzbd)
	    restorescreen(sabnzbd)
	except:
	    restorescreen(sabnzbd)
	    traceback.print_exc()

	if sabnzbd.newapikey != None:
	    print 'New API key: ' + str(sabnzbd.newapikey)

if __name__ == '__main__':
    main()
#    cProfile.run('main()')
    sys.exit(0)
