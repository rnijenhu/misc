#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# SSHplus
# A remote connect utlity, sshmenu compatible clone, and application starter.
#
# (C) 2011 Anil Gulecha
# Based on sshlist, incorporating changes by Benjamin Heil's simplestarter
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Instructions
#
# 1. Copy file sshplus.py (this file) to /usr/local/bin
# 2. Edit file .sshplus in your home directory to add menu entries, each
#    line in the format NAME|COMMAND|ARGS
# 3. Launch sshplus.py
# 4. Or better yet, add it to gnome startup programs list so it's run on login.

#todo: global section ins sshplus.cfg is not working

import gobject
import gtk
import appindicator
import os
import pynotify
import sys
import shlex
import re
import ConfigParser
#import subprocess
import socket
import getpass
import json


_USER=getpass.getuser()
_VERSION = "1.1"
_BIN_PATH=os.path.realpath(os.path.dirname(__file__))
_ETC_CONFIG = "/etc/sshplus/sshplus.cfg"
_SYS_CONFIG = "%s/sshplus/sshplus.cfg"%(_BIN_PATH)
_SETTINGS_FILE =  "%s/.sshplus"%(os.getenv("HOME"))
_SSHMENU_FILE = "%s/.sshmenu"%(os.getenv("HOME"))

_ABOUT_TXT = """A simple application starter as appindicator.

To add items to the menu, edit the file <i>.sshplus</i> in your home directory. Each entry must be on a new line in this format:

<tt>NAME|(ICON|)COMMAND|ARGS</tt>

If the item is clicked in the menu, COMMAND with arguments ARGS will be executed. ARGS can be empty. To insert a separator, add a line which only contains "sep". Lines starting with "#" will be ignored. You can set an unclickable label with the prefix "label:". Items from sshmenu configuration will be automatically added (except nested items). To insert a nested menu, use the prefix "folder:menu name". Subsequent items will be inserted in this menu, until a line containing an empty folder name is found: "folder:". After that, subsequent items get inserted in the parent menu. That means that more than one level of nested menus can be created.

Example file:
<tt><small>
Show top|gnome-terminal|-x top
sep

# this is a comment
label:SSH connections
# create a folder named "Home"
folder:Home
SSH Ex|gnome-terminal|-x ssh user@1.2.3.4
# to mark the end of items inside "Home", specify and empty folder:
folder:
# this item appears in the main menu with icon SSH
SSH Ex|SSH|gnome-terminal|-x ssh user@1.2.3.4

label:RDP connections
RDP Ex|rdesktop|-T "RDP-Server" -r sound:local 1.2.3.4

</small></tt>
Copyright 2011 Anil Gulecha 
Copyright 2016 rnijenhu, http://www.tenijenhuis.net
Incorporating changes from simplestarter, Benjamin Heil, http://www.bheil.net


Released under GPL3, http://www.gnu.org/licenses/gpl-3.0.html"""


_ICONS={}
_RECENT={}
_RECENT_DATA=[]
_RECENT_COUNTER=0
_SEPARATOR={'name':'sep','type':'seperator'}
_FOLDER_POP={'name':'FOLDER','type':'folder', 'caption':'', 'cmd':''}
_MENU_TITLE="Launch"
_MENU_ICON="gnome-netstatus-tx"
_MENUS=[]

def read_config(configfile):
   global _ICONS
   global _RECENT
   global _RECENT_DATA
   global _RECENT_COUNTER
   global _MENU_TITLE
   global _MENU_ICON

   if not os.path.exists(configfile):
	print("Config file not found: %s\n"%(configfile))
   	return []

   config = ConfigParser.ConfigParser({
		'title'	: _MENU_TITLE, 
		'icon'	: _MENU_ICON
	})
   config.read(configfile)

   menufiles=[]

   #read the config and update the settings
   sections=config.sections()

   for section in sections:
	if section.startswith("menu"):
	   menufiles.append(dict(config.items(section)))
   	elif section.startswith("icons"):
	   #read the icons we can use
	   _ICONS=dict(config.items(section))
	elif section.startswith("sshplus"):
	   _MENU_TITLE=config.get("sshplus","title")
	   _MENU_ICON=config.get("sshplus","icon").lower()
   	elif section.startswith("recent"):
	   #read the history files
	   _RECENT=dict(config.items(section))
	else:
	   print ("Unknown section ignored: %s\n"%(section))

   #for ubuntu this will work, others not I guess. maybe we should provide it
   if not 'broken' in _ICONS:
	_ICONS['broken']="/usr/share/icons/gnome/16x16/status/dialog-warning.png"
   if not 'missing' in _ICONS:
	_ICONS['missing']="/usr/share/icons/gnome/16x16/status/messagebox_critical.png"

   if 'file' in _RECENT:
	_RECENT['file']=os.path.expandvars(_RECENT['file'])

   if _MENU_ICON in _ICONS:
	_MENU_ICON=os.path.expandvars(_ICONS[_MENU_ICON])

   _RECENT_DATA=[]
   _RECENT_COUNTER=0

   return menufiles

def notify(msg1,msg2):
        pynotify.init("sshplus")
        pynotify.Notification(msg1,msg2).show()

def refresh():
	newmenu = build_menu()
        ind.set_menu(newmenu)

def menuitem_response(w, item):
    global _RECENT_DATA
    global _RECENT
    global _RECENT_COUNTER

    if 'cmd' in item and item['cmd']=='_about': 
        show_help_dlg(_ABOUT_TXT)
    elif 'cmd' in item and item['cmd']=='_refresh':
	refresh()
 	notify("SSHplus refreshed", "Menu list was refreshed from %s"%(_SETTINGS_FILE))
    elif 'cmd' in item and item['cmd']=='_quit':
        sys.exit(0)
    elif 'type' in item and item['type']=='folder': 
        pass
    else:
	myargs=[item['cmd']] + item['args']
	for i,s in enumerate(myargs):
		myargs[i]=os.path.expandvars(s)

        p = os.spawnvp(os.P_NOWAIT, os.path.expandvars(item['cmd']), myargs)
        os.wait3(os.WNOHANG)
	if not isinstance( p, int ): 
		notify(' '.join(myargs),p)
	
	#build the recent file
	if 'file' in _RECENT: 
		#clean up the (same) previous entry, we will add a new one at the top
		for i,d in enumerate(_RECENT_DATA):
			if 'name' in d and d['name']==item['name']: 
				del _RECENT_DATA[i]

		#append at the beginning and write the recent file		
  		d=[item]+_RECENT_DATA
		with open(_RECENT['file'], 'w') as outfile:
    			json.dump(d, outfile)
			_RECENT_DATA=d
			_RECENT_COUNTER=_RECENT_COUNTER+1

	#after x updates do a menu refresh
	if 'refresh' in _RECENT:
		if int(_RECENT['refresh'])>0 and  _RECENT_COUNTER >= int(_RECENT['refresh']):
			_RECENT_COUNTER=0
			refresh()

def show_help_dlg(msg, error=False):
    if error:
        dlg_icon = gtk.MESSAGE_ERROR
    else:
        dlg_icon = gtk.MESSAGE_INFO
    md = gtk.MessageDialog(None, 0, dlg_icon, gtk.BUTTONS_OK)
    try:
        md.set_markup("<b>SSHplus %s</b>" % _VERSION)
        md.format_secondary_markup(msg)
        md.run()
    finally:
        md.destroy()

def which(program):

    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

def ping(ip):

    ret = os.system("ping  -c2 -W1 %s"%(ip))
    if ret == 0:
	return True

    print "IP not found: %s\n"%(ip)
    return False

def add_menu_item2(menu, app):
   
    menu_item=None
    menu_item_sens=True

    #get the type
    if 'type' not in app:
	print "Error: app without type element:%s\n"%(app)
	return gtk.MenuItem("????") 
  
    #get the menu entry caption
    if 'caption' in app:
	caption=app['caption']
    else:
	caption="???????"

    if app['type']=='seperator':
	    menu_item = gtk.SeparatorMenuItem()

    #create the menu entry with icon
    elif 'icon' in app:
        menu_item = gtk.ImageMenuItem(caption)
	img = gtk.Image()
	iconame=app['icon'].lower()

	#execute items: check if the cmd exists, if not display the missing icon
	if app['type']=="execute" and not which(app['cmd']): 
		print("Command not found in path: %s\n"%(app['cmd']))
		img.set_from_file(os.path.expandvars(_ICONS['missing']))

	#folder items: check if the ip exists, if not disable the the folder
	elif app['type']=="folder" and 'ip' in app and not ping(app['ip']):	
		print("IP not found: %s\n"%(app['ip']))
		menu_item_sens=False
		img.set_from_file(os.path.expandvars(_ICONS[iconame]))		

	#add the icon, when the icon exists
	elif iconame in _ICONS and os.path.exists(os.path.expandvars(_ICONS[iconame])): 
		img.set_from_file(os.path.expandvars(_ICONS[iconame]))

	#if nothing is found but a icons was requested: use the broken icon
	else:
		img.set_from_file(os.path.expandvars(_ICONS['broken']))

        img.show()
        menu_item.set_image(img)

    #create the menu entry without icon
    else:
    	menu_item = gtk.MenuItem(caption)

    #add the menu action
    if app['type'] == "label":
	menu_item_sens=False
    elif app['type'] != "seperator":
    	menu_item.connect("activate", menuitem_response, app)

    #set the sensitivity    
    menu_item.set_sensitive(menu_item_sens)

    #enable the menu in the main menu
    menu_item.show()
    menu.append(menu_item)

    return menu_item 


def get_sshmenuconfig():
    if not os.path.exists(_SSHMENU_FILE):
        return []
    hostlist=open(_SSHMENU_FILE,"r").read()
    lines = hostlist.split("\n")
    lines.remove("items: ") #get rid of the first instance
    app_list = []
    
    smflag=0     # Flag to ignore submenu title items
    smtitle=""   # To hold the title while searching for parameters
    smparams=""  # To hold parameters values
    stackMenuIndex = []

    try:
        for line in lines:
            if re.search("title:",line):
                if smflag == 1:
                    smtitle=line.split(":", 1)[1]
                    continue
                smflag=1
                smtitle=line.split(":", 1)[1]

            elif re.search("sshparams:",line):
                smparams=line.split(":", 1)[1]
                smflag=2

            elif re.search("items:",line):
                app_list.append({
                    'name': 'FOLDER',
                    'type': 'folder',
		    'caption': 'SSHmenu',
                    'cmd': "SSHmenu",
                    'args':[],
                })
                stackMenuIndex.append(len(app_list) - 1)

            elif re.search("type: menu",line):
                if smflag == 1:
                    app_list[stackMenuIndex.pop()]["cmd"] = smtitle
                    app_list.append({
                    'name': 'FOLDER',
                    'type': 'folder',
		    'caption': '',
                    'cmd': "",
                    'args':[],
                })
                    smflag = 0

            if smflag == 2:
                arglist = ("-x ssh " + smparams).split(" ")
                for a in arglist:
                    if a == "":
                        arglist.remove("")
                app_list.append({
                    'name': smtitle,
                    'cmd': 'gnome-terminal',
                    'caption': smtitle,
                    'type': 'execute',
                    'args': arglist,
                 })
                smflag=0
        return app_list
    except:
        print "error in line:" + line
        return []

def get_sshplusconfig(settings_file):

    #init values
    _settings_file=os.path.expandvars(settings_file)
    app_list = []

    #does the file exists, if not return nothing 
    if not os.path.exists(_settings_file):
        return []
    else:
        print("Load menu: %s\n"%(_settings_file))


    #load the menus from a json file
    _settings_file_name, _settings_file_ext = os.path.splitext(_settings_file)
    if _settings_file_ext == ".json":
	with open(_settings_file) as json_data:
		try:
			d=json.load(json_data)

		except ValueError, e :
			print("Failed to load, syntax error \n")
        		return []

		if not isinstance(d,list):
			d=[]

		return d

    #load the user settings
    elif _settings_file_ext =="" and os.path.basename(_settings_file) == ".sshplus":
	print "User setting file: %s\n"%(_settings_file)

    #quit if the extension isn't known (eg conf for now)
    elif _settings_file_ext != ".conf":
	print "Unknown file format: %s\n"%(_settings_file_ext)
	sys.exit(0)
    
    #read the settings from the orginal macro format
    f = open(_settings_file, "r")
    try:
        for line in f.readlines():
            line = line.rstrip()
            if not line or line.startswith('#'):
                continue

	    #process SEPERATORS
            elif line == "sep":
                app_list.append(_SEPARATOR)

	    #process LABEL items
            elif line.startswith('label:'):
		if line.count(':')==1:
	                app_list.append({
	                    'name': 'LABEL',
	                    'cmd': line[6:], 
			    'caption': line[6:],
	                    'args': [],
			    'type':'label'
	                })

		elif line.count(':')==2:
			name, icon, cmd = line.split(':', 2)
	                app_list.append({
	                    'name': 'LABEL',
			    'icon': icon.lower(),
	                    'cmd': cmd, 
			    'caption': cmd,	
	                    'args': [],
			    'type':'label'
	                })

	    #process FOLDER items
            elif line.startswith('folder:'):
		if line.count(':')==1:
		        app_list.append({
		            'name': 'FOLDER',
			    'caption': line[7:],
		            'cmd': line[7:], 
		            'args': [],
			    'type':'folder'
		        })
		elif line.count(':')==2:
			name, icon, cmd = line.split(':', 2)
		        app_list.append({
		            'name': 'FOLDER',
			    'icon': icon.lower(),
			    'caption': cmd,
		            'cmd': cmd, 
		            'args': [],
			    'type':'folder'
		        })
		elif line.count(':')==3:
			name, icon, ip, cmd = line.split(':', 3)
		        app_list.append({
		            'name': 'FOLDER',
			    'icon': icon.lower(),
			    'ip': ip,
			    'caption': cmd,
		            'cmd': cmd, 
		            'args': [],
			    'type':'folder'
		        })

            #process EXECUTE items
            else:
                try:
		    if line.count('|') == 2 :
                        name, cmd, args = line.split('|', 2)
                        app_list.append({
                          'name': name,
			  'caption': name,
                          'cmd': cmd,
			  'type':'execute',
                          'args': [n.replace("\n", "") for n in shlex.split(args)],
                         })
		    elif line.count('|') == 3 :
                        name, icon, cmd, args = line.split('|', 3)
                        app_list.append({
			  'icon': icon.lower(),
                          'name': name,
			  'caption': name,
                          'cmd': cmd,
			  'type':'execute',
                          'args': [n.replace("\n", "") for n in shlex.split(args)],
                         })
		    else: print "The following line has an invalid amount of separators and will be ignored:\n%s" % line
                except ValueError:
                    print "The following line has errors and will be ignored:\n%s" % line
    finally:
        f.close()
    return app_list

def build_menu():
    global  _RECENT_DATA

    app_list=[]

    #read the recent items
    if 'file' in _RECENT:
	if 'count' in _RECENT and int(_RECENT['count'])>0: 
		_RECENT_DATA=get_sshplusconfig(_RECENT['file'])

    #strip down to the needed amount
    if 'name' in _RECENT: 
		name=_RECENT['name']
    else:
 		name="Recently Used:" 
    label={
	'cmd'	:  name, 
	'name'	: 'LABEL', 
	'type'  : 'label',
	'caption'  : name,
	'args': []}

    if 'count' in _RECENT and len(_RECENT_DATA)>0 and len(_RECENT_DATA)<=_RECENT['count']:
	app_list=[ _SEPARATOR, label, _SEPARATOR]+ _RECENT_DATA[0:int(_RECENT['count'])]+ [_FOLDER_POP,_SEPARATOR]
    else:
	app_list=[ _SEPARATOR, label, _SEPARATOR]+ _RECENT_DATA                   + [_FOLDER_POP,_SEPARATOR]

    #read the user menu
    u_list=get_sshplusconfig(_SETTINGS_FILE)
    if u_list != []:
    	app_list = app_list + ulist;


    #load the global menus
    for menu in _MENUS :

	if 'file' in menu: 
		m_list=get_sshplusconfig(menu['file'])
	else:
		print "Menu item found without file key: %s\n"%(menu)
		continue

        if m_list !=[]:

		#check if the menu is allowed for this user
		if 'users' in menu:
			users=menu['users'].split(',')

			if  not _USER in users:
				continue

		if 'name' in menu: 
			name=menu['name']
		else:
			name=menu['file']

		folder={
			'cmd'	:  menu['name'], 
			'name'	: 'FOLDER', 
			'type'  : 'folder',
			'caption'  : menu['name'],
			'args': []}

		if 'icon' in menu:
			folder['icon']=menu['icon']

		if 'ip' in menu:
			folder['ip']=menu['ip']

		if 'decoration' in menu and menu['decoration'].lower()=="false" :			
                	app_list=app_list + m_list 
		else:
			app_list=app_list + [ _SEPARATOR, _FOLDER_POP, folder, _SEPARATOR] + m_list 
	else:
		print "File not found or empty: %s\n"%(menu['file'])


    #Add sshmenu config items if any
    app_list2 = get_sshmenuconfig()
    if app_list2 != []:
        app_list = app_list + [_SEPARATOR,{'name': 'LABEL','cmd': "SSHmenu",'args': ''}] + app_list2

    menu = gtk.Menu()
    menus = [menu]


    if len(app_list) <=0:
        show_help_dlg("<b>ERROR: No menus found in $HOME/.sshmenu $HOME/.sshplus or /etc/sshplus/sshplus.cfg </b>\n\n%s" % \
             _ABOUT_TXT, error=True)
        sys.exit(1)



   #to make this work: add FOLDER|LABEL|COMMAND to the dict and let add_menu_item sort out what to do in each case
   # or juist provide the sec arg with 'name'

    for app in app_list:
	if app['name'] == "FOLDER" and not app['cmd']:
            if len(menus) > 1:
                menus.pop()
	else:
	    menu_item = add_menu_item2(menus[-1], app)
	    if app['name'] == "FOLDER":
            	menus.append(gtk.Menu())
            	menu_item.set_submenu(menus[-1])

   
    add_menu_item2(menus[-1], _SEPARATOR)
    add_menu_item2(menu, {'name': '_refresh','caption': 'Refresh','cmd': '_refresh','type':'execute','args': []})
    add_menu_item2(menu, {'name': '_about','caption': 'About','cmd': '_about','type':'execute','args': []})
    add_menu_item2(menus[-1], _SEPARATOR)
    add_menu_item2(menu, {'name': '_quit','caption': 'Quit','cmd': '_quit','type':'execute','args': []})
    return menu

def write_desktopfile(desktopfile):
        file = open(desktopfile, "w")
        file.write("[Desktop Entry]\n")
	file.write("Type=Application\n")
	file.write("Name=sshplus\n")
	file.write("Exec=%s\n"%(os.path.realpath(__file__)))
	#file.write("Icon=<full path to icon>\n")
	file.write("Comment=SSHplus Menu indicator\n")
	file.write("Hidden=false\n")
	file.write("NoDisplay=false\n")
	file.write("X-GNOME-Autostart-enabled=true\n")
	file.close()


if __name__ == "__main__":
    

    #display help
    if  "--help" in sys.argv :
	print(	"\n\n"+
		" .sshplus.py                       without arguments just creates the menu\n"+
	     	" .sshplus.py --start-on-login      creates the autostart for the user (only)\n"+	
	     	" .sshplus.py --start-on-login-sys  creates the autostart for the system, root privileges required\n"+
		"\n"+
		" FILES: /etc/sshplus/sshplus.cfg  /$HOME/.sshplus\n")
	sys.exit()

    #create startup files
    if  "--start-on-login" in sys.argv :
	write_desktopfile(os.path.expandvars("$HOME/.config/autostart/sshplus.py.desktop"))
	sys.exit()
    if  "--start-on-login-sys" in sys.argv :
	write_desktopfile("/etc/xdg/autostart/sshplus.py.desktop")
	sys.exit()

    #read the config file, it will set the SETTING_FILE to list
    _MENUS=read_config(_ETC_CONFIG)
    if not _MENUS:
	_MENUS=read_config(_SYS_CONFIG)

    #enable the icons in menus: http://www.pygtk.org/pygtk2reference/class-gtksettings.html
    window = gtk.Window(gtk.WINDOW_TOPLEVEL)
    window.get_settings().set_long_property('gtk-menu-images', True, '')

    #create and display the indicator
    ind = appindicator.Indicator("sshplu", _MENU_ICON,
                                 appindicator.CATEGORY_APPLICATION_STATUS)
    
    ind.set_label(_MENU_TITLE)
    ind.set_status(appindicator.STATUS_ACTIVE)

    appmenu = build_menu()
    ind.set_menu(appmenu)
    gtk.main()

