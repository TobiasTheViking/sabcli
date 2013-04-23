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

import os, sys, time, httplib
import xml.etree.ElementTree as ElementTree
import getopt, ConfigParser
from threading import Thread

VERSION="0.5-11"
APIVERSION="0.5.4"

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

class monitor(Thread):
   def __init__ (self, value):
        Thread.__init__(self)
	self.cont = True
	self.delay = value
   def run(self):
      time.sleep(2)
      sys.stdin.readline()
      print 'Exiting watch mode after next loop.'
      self.cont = False

class SABnzbdCore( object ):
    ''' Sabnzbd Automation Class '''
    def __init__(self, config = None):
	self.config = config
        if not self.config:
            self.config = { 'host' : 'localhost', 'port' : '8080', 
                       'username' : None, 'password;' : None,
                       'apikey' : None }, 

        # Public Variables
        self.fetchpath = ''
        self.servername = ''
        self.header = {}
        self.postdata = None
        self.command_status = 'ok'
        self.return_data = {}
	self.retval = ''
        self.url = 'http://' + self.servername + '/sabnzbd/'
	self.job_option = '3'
	self.debug = None
	self.watchdelay = None
	self.width = int(os.popen('stty size', 'r').read().split()[1])

    # Private Methods        
    def xml_to_dict(self, el):
	d={}

    	if el.text:
	    d[el.tag] = el.text
    	else:
    	    d[el.tag] = None

    	for child in el:
	    if child:
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
        self.retval = status_obj.lower().strip('\n')
        self.command_status = self.retval

        if self.retval == 'ok' :
            return True  
        if self.retval == 'error' :
            return False
	if command in ('version', 'move', 'priority'):
	    return self.retval

        ''' Convert status object to python dictionary '''
	# Fix broken xml from sabnzbd
	if command == 'warnings':
            temp = status_obj.replace("<warnings>","<root>\n<warnings>") 
	    status_obj = temp.replace("</warnings>","</warnings></root>")
        if command == 'details':
            temp = status_obj.replace("<files>","<root>\n<files>")
            status_obj = temp.replace("</files>","</files></root>")

        try:
            status_obj = status_obj.replace('&', '&amp;') 
            root = ElementTree.XML(status_obj.strip())
	    self.return_data = self.xml_to_dict(root) 

	    if self.debug:
		print
		for a in self.return_data.keys():
		    print "%s - %s" % ( a, self.return_data[a] )
		print

            self.command_status = 'ok'
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
            self.command_status = 'http://' + self.servername + path + ' -> ' + err.message
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
            	print 'unhandled command: ' + command
            	usage(2)

	elif len(args) == 1:
            if command in ('addfile', 'addurl', 'addid'):
                url_fragment += '&name=' + args[0] + '&pp=' + self.job_option
	    elif command == 'newapikey':
		if args[0] == 'confirm':	
                    url_fragment = 'config&name=set_apikey'
		else:
                    print 'unhandled command: ' + command
		    usage(2)
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
		else:
		    usage(2)
            else:
                print 'unhandled command: ' + command
                usage(2)

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
                print 'unhandled command: ' + command
                usage(2)
	else:
	    print 'unhandled command: ' + command
	    usage(2)

        self.url = 'http://' + self.servername + self.fetchpath + url_fragment

	if self.debug:
	    print self.url

        data = self.__send_request(command, self.fetchpath + url_fragment) 

	if data == False:
	    return False

        return self.__parse_status(command, data)

    def getNZO_id(self, index = '-1'):
        self.send_command('queue')
        nzo_id = None
        if self.return_data['slots'] != None:
            try:
                self.return_data['slots']['slot'].keys()
                slots = [ self.return_data['slots']['slot'] ]
            except AttributeError:
                slots = self.return_data['slots']['slot']
            for each in slots:
                if each['index'] == index:
                    nzo_id = each['nzo_id']
        return nzo_id

    def getName(self, nzo_id = ''):
	self.send_command('queue')
	name = ''
        if self.return_data['slots'] != None:
            try:
                self.return_data['slots']['slot'].keys()
                slots = [ self.return_data['slots']['slot'] ]
            except AttributeError:
                slots = self.return_data['slots']['slot']
            for each in slots:
                if each['nzo_id'] == nzo_id:
                    name = each['filename']
	return name

    def printLine(self, segments):
	# Calculate spacing between segments in line.
        space = self.width
	for segment in segments:
	    space -= len(segment)
	if len(segments) > 1:
	    space = space / (len(segments)-1)
	if space <= 0:
	    space = 1
	
	# Combine segments with equal spacing
	combined = ''
	for segment in segments:
	    combined += segment + " " * space

	# Remove trailing whitespaces from above.
        return combined.strip()
	
    def insert(self, original, new, pos):
	'''Inserts new inside original at pos.'''
	return original[:pos] + new + original[pos:]

    def print_header(self):
        ''' Print pretty table with status info '''
        if float(self.return_data['mbleft']) / 1024 > float(self.return_data['diskspace2']):
            print tc.red + tc.bold + "WARNING:" + tc.end + " Insufficient free disk space left to finish queue.\n"
        if float(self.return_data['mbleft']) / 1024 > float(self.return_data['diskspacetotal2']):
            print tc.red + tc.bold + "WARNING:" + tc.end + " Insufficient total disk space to finish queue.\n"

        preline = 'Free/Total Disk: %.2f / %.2f GB' % \
                ( float(self.return_data['diskspace2']),
                  float(self.return_data['diskspacetotal2']) )

        if self.return_data['paused'] == 'True':
            postline = "Speed: Paused"
        else:
            postline = "Speed: %.2f kb/s" %  float(self.return_data['kbpersec'])
	tempLine = self.printLine([preline, postline])

	# Adding color. Because of printLine it MUST be done with replace.
	tempLine = tempLine.replace('Speed: ', 'Speed: ' + tc.cyan)
	tempLine = tempLine.replace('kb/s', tc.end + 'kb/s')
        tempLine = tempLine.replace('Paused', 'Paused' + tc.end)

 	print tempLine

        if 'total_size' in self.return_data:
            # History view
            print(str('Transferred Total: %s - Month: %s - Week: %s' %  \
                ( self.return_data['total_size'], self.return_data['month_size'], self.return_data['week_size'])).center(self.width))
        else:
            # Queue view or pre 0.5.2 view
            print(str('Queue: %.2f / %.2f GB [%2.0f%%] [Up: %s]' % \
                ( ( float(self.return_data['mb']) -
                    float(self.return_data['mbleft']) ) / 1024 ,
                  float(self.return_data['mb']) / 1024,
                  100*( float(self.return_data['mb']) -
                    float(self.return_data['mbleft']))/(float(self.return_data['mb'])+0.01), self.return_data['uptime'])).center(self.width))

    def print_queue(self):
	self.print_header()
        print self.printLine(['# - Filename [Age/Priority/Options] (Status)', 'Downloaded/Total (MB) [pct]'])
        print '-' * self.width

        if self.return_data['slots'] != None:
            try:
                self.return_data['slots']['slot'].keys()
                slots = [ self.return_data['slots']['slot'] ]
            except AttributeError:
                slots = self.return_data['slots']['slot']

	    tailLength = 0
            for each in slots:
		if tailLength < len(each['mb']):
		    tailLength = len(each['mb'])
	    tailLength += tailLength

	    for each in slots:
                opts = ['Download', 'Repair', 'Unpack', 'Delete']

		# Line 1
                print "%s - %s [%s/%s/%s] (%s)" % ( tc.green + each['index'] + tc.end, each['filename'], tc.green + each['avg_age'] + tc.end, tc.green + each['priority'] + tc.end, \
			tc.green + opts[int(each['unpackopts'])] + tc.end, tc.green + each['status'] + tc.end )

		# Line 2
		time = each['timeleft']
		if len(each['timeleft']) == 7:
		    time = "0" + time

                tail = "%.2f / %.2f [%2.0f%%]" % ( float(each['mb'])-float(each['mbleft']), float(each['mb']), float(each['percentage']) )
                tail2 = "%s%.2f %s/ %s%.2f %s[%s%2.0f%%%s]" % (tc.red, float(each['mb'])-float(each['mbleft']), tc.end, tc.red, float(each['mb']), \
			tc.end, tc.red, float(each['percentage']), tc.end )
                tail2= " " * ( tailLength + 9 - len(tail)) + tail2

                charsLeft = self.width - len(time) - len(tail) - 9 - ( tailLength + 9 - len(tail))
                pct = (charsLeft)/100.0 * float(each['percentage'])
		progress = "="* int(pct) + ">" + " " * (charsLeft-int(pct))

                print "    " + tc.red + time + tc.end + " " + tc.bold + tc.yellow + "[" + progress + "]" + tc.end + " " + tail2 
		print 

        return True

    def print_details(self):
	print 'Filename'
        print '-' * self.width

        if self.return_data['files'] != None:
            try:
                self.return_data['files']['file'].keys()
                files = [ self.return_data['files']['file'] ]
            except AttributeError:
                files = self.return_data['files']['file']
            for each in files:
		print each['filename']
                print " - [Status: %s] [Downloaded: %s/%s MB]" % ( each['status'], float(each['mb']) - float(each['mbleft']), float(each['mb']) )
		print

        return True

    def print_history(self):
        self.print_header()
        print 'Filename'
        print '-' * self.width

        if self.return_data['slots'] != None:
            try:
                self.return_data['slots']['slot'].keys()
                slots = [ self.return_data['slots']['slot'] ]
            except AttributeError:
                slots = self.return_data['slots']['slot']

	    slots.reverse()
            for each in slots:
		print each['name']
		par2 = ''
		unpack = ''
		log = ''
		stage_log = each['stage_log']
		if stage_log != None:
		    try:
			stage_log['slot'].keys()
			items = [ stage_log['slot'] ]
		    except AttributeError:
			items = stage_log['slot']

		    for item in items:
			if item['name'] == "Unpack":
                            if type(item['actions']['item']) == str:
                                data = [item['actions']['item']]
                            else:
                                data = item['actions']['item']
                            fail = 0

                            for subdata in data:
                                if str.find(subdata, 'Unpacked') != -1:
                                    unpack = '[unpack: ' + tc.green + tc.bold + 'OK' + tc.end +']'
                                else:
                                    log += " - " + tc.red + subdata + tc.end + "\n"
                                    fail += 1
                            if fail > 0:                                                                                                                     
                                unpack = '[unpack: ' + tc.red + 'FAIL' + tc.end + ']'

			elif item['name'] == "Repair":
			    if type(item['actions']['item']) == str:
				data = [item['actions']['item']]
		    	    else:
				data = item['actions']['item']
			    fail = 0

		    	    for subdata in data:
		        	if str.find(subdata, 'Quick Check OK') != -1:
			    	    par2 = '[par2: ' + tc.green + tc.bold + 'OK' + tc.end +']'
				elif str.find(subdata, 'Repaired in') != -1:
				    par2 = '[par2: ' + tc.green + tc.bold + 'OK' + tc.end +']'
				else:
				    log += " - " + subdata.replace("Repair failed", tc.red + "Repair failed") + tc.end + "\n"
			    	    fail += 1
			    if fail > 0:
				par2 = '[par2: ' + tc.red + tc.bold + 'FAIL' + tc.end + ']'

		print ' - [download: %s] %s %s' % ( each['size'], par2, unpack )
		print log

        return True

    def print_warnings(self): 
        ''' Print pretty table with status info '''
        if self.return_data['warnings'] != None:
            try:
                self.return_data['warnings'].keys()
                slots = [ self.return_data['warnings']['warning'] ]
            except AttributeError:
                slots = self.return_data['warnings']['warning']

	    if slots[0][0] != 1:
	        slots = slots[0]
            for each in slots:
		warning = each.split("\n")
		line = "[%s] %s" % ( warning[0], warning[1] )
		if len(line) < 33:
		    line = line + " " * (33-len(line))
		line += " | " + warning[2]
		print line
	print 

        return True

    def print_version(self):
        print 'sabcli: ' + VERSION + '\nAPI Version: ' + APIVERSION + '\nSABnzbd Version: ' + self.retval + '\n'

	if APIVERSION == self.retval:
	    print 'Versions match'
	else:
            print 'Versions mismatch'

	return True

    def watch(self, command, command_arg):
#	s = monitor(self.watchdelay)
#	s.start()
#	cont = s.cont
        while True:
            print '\x1B[2J'
            print '\x1B[1;1H'
            print self.printLine(['Refreshing in : ' + str(self.watchdelay) + ' seconds. Press CTRL-C to quit (can take up to '+ str(self.watchdelay) + ' seconds to quit).', 'Last refresh: ' + time.strftime("%H:%M:%S", time.localtime())])
	    print
            run_commands(self, command, command_arg)
	    time.sleep(self.watchdelay)    
#	s.join()
	print 
	    

def usage(exitval):
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

    sys.stderr.write(msg + '\n')
    sys.exit(exitval)

def parse_options(sabnzbd, options):
    ''' Parse Cli options '''
    default_opts = ("hj:H:P:u:p:a:w:" , ["help" , "job-option=", "hostname=", "port=", "username=", "password=", "apikey=", "watch="])
    command = None
    command_args = None

    try:
        opt , args = getopt.getopt(options, default_opts[0], default_opts[1])
    except getopt.GetoptError:
        usage(2)
    for option , arguement in opt:
        if option in ("-h", "--help"):
            usage(2)
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
        elif option in ("-w", "--watch"):
            sabnzbd.watchdelay = int(arguement)

    if len(args) == 0:
	command = 'queue'
    else:
        command = args[0]
        if len(args) > 1:
	    command_args = args[1:]

    return (command, command_args)

def parse_config(config):
    ''' Parse config file for server info '''
    parser = ConfigParser.ConfigParser()
    config_dict = {}
    try:
        config_file = open(config)
        parser.readfp(config_file)
        config_file.close()
    except IOError:
	usage(1)
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
        usage(1)

    return config_dict

def run_commands(sabnzbd, command, command_arg):
    if command in ('rename', 'move', 'priority', 'postprocessing', 'pause', 'resume', 'details'):
	if command_arg != None:
	    command_arg[0] = sabnzbd.getNZO_id(command_arg[0])
	    if command_arg[0] == None:
		print tc.red + 'Error:' + tc.end + ' No NZO_ID returned, please make sure you provided the correct index id.\n'
		return 2

    if command == 'delete':
        if command_arg != None:
	    if command_arg[0] != 'all':
		temp = None
		for each in command_arg:
		    pretemp = sabnzbd.getNZO_id(each)
		    if pretemp:
			temp = str(pretemp) + ','
		    else:
                	print tc.red + 'Error:' + tc.end + ' No NZO_ID returned, please make sure you provided the correct index id.\n'
		if temp:
		    command_arg = [temp[:-1]]
		else:
		    return 2

    if sabnzbd.send_command(command, command_arg):
        if command == 'queue':
            sabnzbd.print_queue()
        elif command == 'history':
            if command_arg == None:
                sabnzbd.print_history()
            else:
                print 'History Cleared'
		print
	elif command == 'details':
	    sabnzbd.print_details()
        elif command == 'warnings':
            sabnzbd.print_warnings()
        elif command == 'version':
            sabnzbd.print_version()
        elif command == 'priority':
	    if sabnzbd.debug:
                print 'New position in queue: ' + sabnzbd.retval
                sabnzbd.command_status = sabnzbd.command_status.replace(sabnzbd.retval, "ok\n");
        elif command == 'move':
            value = sabnzbd.retval.split(' ')
            if sabnzbd.debug:
                print 'New position in queue: ' + value[0]
                sabnzbd.command_status = sabnzbd.command_status.replace(sabnzbd.retval, "ok");
	elif command == 'speedlimit':
	    if command_arg[0] == '0':
		print 'Speedlimit set to: Unlimited'
	    else:
		print 'Speedlimit set to: ' + command_arg[0] + 'KB/s'
        elif command in ('newapikey', 'shutdown', 'restart', 'queuecompleted'):
            print command + ' -> ' + sabnzbd.command_status
        elif command in ('addurl', 'addfile', 'addid', 'delete', 'pause', 'resume', 'rename', 'postprocessing'):
            if sabnzbd.debug:
		print command + ' -> ' + sabnzbd.command_status
        else:
            print 'No command run: ' + sabnzbd.url
    if command in ('newapikey'):
        print sabnzbd.command_status

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

    	if sabnzbd.debug:
	    print 'SABnzbd+ CLI ' + VERSION + '\n'
        else:
	    print

    	command, command_arg = parse_options(sabnzbd, sys.argv[1:])
    	sabnzbd.setConnectionVariables()

    	if sabnzbd.debug:
            print 'command:' + str(command) + ' - ' + str(command_arg)

    	if sabnzbd.watchdelay:
	    if command not in ('warnings', 'queue', 'details', 'history'):
	        print tc.red + tc.bold + 'WARNING:' + tc.end + ' Watch can not be used in conjunction with the "'+ command + '" command.'
	        print '         Check help screen for valid watch commands\n'
	    else:    
	        try:
		    sabnzbd.watch(command, command_arg)
	        except KeyboardInterrupt:
		    print '\nCatched CTRL-C, exiting watch\n'
	        except:
		    print 'General exception in watch'
    	else:
	    run_commands(sabnzbd, command, command_arg)

    	if command in ('move', 'addurl', 'addfile', 'addid', 'delete', 'priority', 'resume', 'pause', 'temppause', 'rename', 'postprocessing'):
            run_commands(sabnzbd, 'queue', None)

    	if sabnzbd.debug:
	    print command + ' -> ' + sabnzbd.command_status

if __name__ == '__main__':
    main()
    sys.exit(0)
