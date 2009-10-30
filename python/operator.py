# -*- coding: utf-8 -*-
###
# Copyright (c) 2009 by Elián Hanisch <lambdae2@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
###

###
#  Helper script for IRC operators
#
#  TODO for v1.0
#  * unban command
#  * implement freenode's remove and mute commands
#  * command for switch channel moderation on/off
#  * default kick reason config option
#  * wait until got op before sending commands
#  
#  TODO for later
#  * bans expire time
#  * bantracker (keeps a record of ban and kicks)
#  * user tracker (for ban even when they already parted)
###

SCRIPT_NAME    = "operator"
SCRIPT_AUTHOR  = "Elián Hanisch <lambdae2@gmail.com>"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "GPL3"
SCRIPT_DESC    = "Helper script for IRC operators"

try:
	import weechat
	WEECHAT_RC_OK = weechat.WEECHAT_RC_OK
	#WEECHAT_RC_ERROR = weechat.WEECHAT_RC_ERROR
	import_ok = True
except ImportError:
	print "This script must be run under WeeChat."
	print "Get WeeChat now at: http://weechat.flashtux.org/"
	import_ok = False

try:
	from weeutils import *
	weeutils_module = True
except:
	weeutils_module = False

import getopt
#import fnmatch


class CommandQueue(object):
	commands = []
	wait = 0
	def queue(self, buffer, cmd, wait=1):
		self.commands.append((buffer, cmd, wait))

	def run(self):
		for buffer, cmd, wait in self.commands:
			if self.wait:
				#debug('running with wait(%s) %s' %(self.wait, cmd))
				weechat.command(buffer, '/wait %s %s' %(self.wait, cmd))
			else:
				#debug('running %s' %cmd)
				weechat.command(buffer, cmd)
			self.wait += wait
		self.clear()

	def clear(self):
		self.commands = []
		self.wait = 0


class CommandOperator(Command):
	queue = CommandQueue()
	def __call__(self, *args):
		Command.__call__(self, *args)
		self.queue.run()
		return WEECHAT_RC_OK

	def _parse(self, *args):
		Command._parse(self, *args)
		self.server = weechat.buffer_get_string(self.buffer, 'localvar_server')
		self.channel = weechat.buffer_get_string(self.buffer, 'localvar_channel')
		self.nick = weechat.info_get('irc_nick', self.server)

	def replace_vars(self, s):
		if '$channel' in s:
			s = s.replace('$channel', self.channel)
		if '$nick' in s:
			s = s.replace('$nick', self.nick)
		if '$server' in s:
			s = s.replace('$server', self.server)
		return s

	def get_config(self, config):
		string = '%s_%s_%s' %(self.server, self.channel, config)
		value = weechat.config_get_plugin(string)
		if not value:
			string = '%s_%s' %(self.server, config)
			value = weechat.config_get_plugin(string)
			if not value:
				value = weechat.config_get_plugin(config)
		return value

	def get_config_boolean(self, config):
		value = self.get_config(config)
		return boolDict[value]

	def get_op_cmd(self):
		value = self.get_config('op_cmd')
		if not value:
			raise Exception, "No command defined for get op."
		return self.replace_vars(value)

	def get_deop_cmd(self):
		value = self.get_config('deop_cmd')
		if not value:
			return '/deop'
		return self.replace_vars(value)

	def is_op(self):
		try:
			for nick in Infolist('irc_nick', args='%s,%s' %(self.server, self.channel)):
				if nick['name'] == self.nick:
					if nick['flags'] & 8:
						return True
					else:
						return False
		except:
			error('Not in a channel')

	def is_nick(self, nick):
		try:
			for user in Infolist('irc_nick', args='%s,%s' %(self.server, self.channel)):
				if user['name'] == nick:
					return True
			return False
		except:
			error('Not in a channel')

	def run_cmd(self, cmd, wait=1, **kwargs):
		self.queue.queue(self.buffer, cmd, wait)

	def get_op(self, **kwargs):
		self.run_cmd(self.get_op_cmd(), **kwargs)

	def drop_op(self, **kwargs):
		self.run_cmd(self.get_deop_cmd(), **kwargs)

	def kick(self, nick, reason, **kwargs):
		if not reason:
			reason = 'bye'
		cmd = '/kick %s %s' %(nick, reason)
		self.run_cmd(cmd, **kwargs)

	def ban(self, *args, **kwargs):
		cmd = '/ban %s' %' '.join(args)
		self.run_cmd(cmd, **kwargs)

	def unban(self, *args, **kwargs):
		cmd = '/unban %s' %' '.join(args)
		self.run_cmd(cmd, **kwargs)


manual_op = False
class Op(CommandOperator):
	def help(self):
		return ("Asks operator status by using the configured command.", "",
		"""
		The command it's defined globally in plugins.var.python.%(name)s.op_cmd
		   It can be defined per server or per channel:
		    per server: plugins.var.python.%(name)s.'server_name'.op_cmd
		   per channel: plugins.var.python.%(name)s.'server_name'.'channel_name'.op_cmd""" %{'name':SCRIPT_NAME})

	def cmd(self, *args):
		global manual_op
		manual_op = True
		self.op()
	
	def op(self):
		op = self.is_op()
		if op is False:
			self.get_op()
		return op


class Deop(CommandOperator):
	def help(self):
		return ("Drops operator status.", "", "")

	def cmd(self, *args):
		op = self.is_op()
		if op is True:
			self.drop_op()
		return op


deop_hook = ''
deop_callback = None
class CmdOp(Op):
	def __call__(self, *args):
		self._parse(*args)
		op = self.op()
		global manual_op
		if op is None:
			return WEECHAT_RC_OK
		elif op is False:
			manual_op = False
		self.cmd(self, *args)
		# don't deop if we used /oop before
		if not manual_op and self.get_config_boolean('deop_after_use'):
			delay = int(self.get_config('deop_delay'))
			if delay > 0:
				global deop_hook, deop_callback
				if deop_hook:
					weechat.unhook(deop_hook)
				def callback(data, count):
					cmd_deop('', self.buffer, self.args)
					deop_hook = ''
					return WEECHAT_RC_OK
				deop_callback = callback
				deop_hook = weechat.hook_timer(delay * 1000, 0, 1, 'deop_callback', '')
			else:
				self.drop_op()
		self.queue.run()
		return WEECHAT_RC_OK


class Kick(CmdOp):
	def help(self):
		return ("Kicks nick. Request operator status if needed.", "<nick> [<reason>]", "")

	def cmd(self, *args):
		if ' ' in self.args:
			nick, reason = self.args.split(' ', 1)
		else:
			nick, reason = self.args, ''
		self.kick(nick, reason)


class MultiKick(Kick):
	def help(self):
		return ("Kicks nicks, can be more than one. Request operator status if needed.",
				"<nick> [<nick> ...] [:] [<reason>]",
				"It's recommended to use ':' as a separator between the nicks and the reason.")
	def cmd(self, *args):
		args = self.args.split()
		nicks = []
		#debug('multikick: %s' %str(args))
		while(args):
			nick = args[0]
			if nick[0] == ':' or not self.is_nick(nick):
				break
			nicks.append(args.pop(0))
		#debug('multikick: %s, %s' %(nicks, args))
		reason = ' '.join(args).lstrip(':')
		for nick in nicks:
			self.args = '%s %s' %(nick, reason)
			Kick.cmd(self, *args) # '%s %s' %(nick, reason))


class Ban(CmdOp):
	def help(self):
		return ("Bans users. Request operator status if needed.",
				"<nick> [<nick> ..] [(-h|--host)] [(-u|--user)] [(-n|--nick)] [(-e|--exact)]",
				"TODO detailed help")

	banmask = []
	def _parse(self, *args):
		CmdOp._parse(self, *args)
		args = self.args.split()
		(opts, args) = getopt.gnu_getopt(args, 'hune', ('host', 'user', 'nick', 'exact'))
		self.banmask = []
		for k, v in opts:
			if k in ('-h', '--host'):
				self.banmask.append('host')
			elif k in ('-u', '--user'):
				self.banmask.append('user')
			elif k in ('-n', '--nick'):
				self.banmask.append('nick')
			elif k in ('-e', '--exact'):
				self.banmask = ['nick', 'user', 'host']
				break
		if not self.banmask:
			self.banmask = self.get_default_banmask()
		self.args = ' '.join(args)

	def get_host(self, name):
		for user in Infolist('irc_nick', args='%s,%s' %(self.server, self.channel)):
			if user['name'] == name:
				return '%s!%s' % (name, user['host'])

	def get_default_banmask(self):
		value = self.get_config('default_banmask')
		values = value.split(',')
		valid_values = ('nick', 'user', 'host', 'exact')
		for value in values:
			if value not in valid_values:
				error("'%s' is and invalid option for 'default_banmask', allowed: %s."
						%(value, ', '.join(map(repr, valid_values))))
				return []
		return values

	def make_banmask(self, hostmask):
		if not self.banmask:
			return hostmask[:hostmask.find('!')]
		nick = user = host = '*'
		if 'nick' in self.banmask:
			nick = hostmask[:hostmask.find('!')]
		if 'user' in self.banmask:
			user = hostmask.split('!',1)[1].split('@')[0]
		if 'host' in self.banmask:
			host = hostmask[hostmask.find('@') + 1:]
		banmask = '%s!%s@%s' %(nick, user, host)
		return banmask
	
	def cmd(self, *args):
		args = self.args.split()
		banmasks = []
		for arg in args:
			mask = arg
			if not is_hostmask(arg):
				hostmask = self.get_host(arg)
				if hostmask:
					mask = self.make_banmask(hostmask)
			banmasks.append(mask)
		if banmasks:
			self.ban(*banmasks)


class UnBan(Ban):
	def cmd(self, *args):
		args = self.args.split()
		self.unban(*args)


class MergedBan(Ban):
	unban = False
	def ban(self, *args, **kwargs):
		c = self.unban and '-' or '+'
		# do 4 bans per command
		for n in range(0, len(args), 4):
			slice = args[n:n+4]
			hosts = ' '.join(slice)
			cmd = '/mode %s%s %s' %(c, 'b'*len(slice), hosts)
			self.run_cmd(cmd, **kwargs)


class KickBan(Ban):
	def help(self):
		return ("Kickban user. Request operator status if needed.",
				"<nick> [<reason>] [(-h|--host)] [(-u|--user)] [(-n|--nick)] [(-e|--exact)]",
				"TODO detailed help")

	invert = False
	def cmd(self, *args):
			if ' ' in self.args:
			nick, reason = self.args.split(' ', 1)
		else:
			nick, reason = self.args, ''
		hostmask = self.get_host(nick)
		if hostmask:
				banmask = self.make_banmask(hostmask)
			if self.invert:
				self.kick(nick, reason)
				self.ban(banmask)
			else:
				self.ban(banmask)
				self.kick(nick, reason)

# config callbacks
def enable_multiple_kick_conf_cb(data, config, value):
	global cmd_kick
	cmd_kick.unhook()
	if boolDict[value]:
		cmd_kick = MultiKick('okick', 'cmd_kick')
	else:
		cmd_kick = Kick('okick', 'cmd_kick')
	return WEECHAT_RC_OK

def merge_bans_conf_cb(data, config, value):
	global cmd_ban
	cmd_ban.unhook()
	if boolDict[value]:
		cmd_ban  = MergedBan('oban', 'cmd_ban')
	else:
		cmd_ban = Ban('okick', 'cmd_kick')
	return WEECHAT_RC_OK

def invert_kickban_order_conf_cb(data, config, value):
	global cmd_kban
	if boolDict[value]:
		cmd_kban.invert = True
	else:
		cmd_kban.invert = False
	return WEECHAT_RC_OK

if import_ok and weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
		SCRIPT_DESC, '', ''):
	if weeutils_module:
		# settings
		settings = (
				('op_cmd', '/msg chanserv op $channel $nick'),
				('deop_cmd', '/deop'),
				('deop_after_use', 'on'),
				('deop_delay', '300'),
				('default_banmask', 'host'),
				('enable_multiple_kick', 'off'),
				('merge_bans', 'on'),
				('invert_kickban_order', 'off'))
		for opt, val in settings:
			if not weechat.config_is_set_plugin(opt):
					weechat.config_set_plugin(opt, val)

		# hook our Command classes
		cmd_op   = Op('oop', 'cmd_op')
		cmd_deop = Deop('odeop', 'cmd_deop')
		if get_config_boolean('enable_multiple_kick'):
			cmd_kick = MultiKick('okick', 'cmd_kick')
		else:
			cmd_kick = Kick('okick', 'cmd_kick')
		if get_config_boolean('merge_bans'):
			cmd_ban  = MergedBan('oban', 'cmd_ban')
		else:
			cmd_ban  = Ban('oban', 'cmd_ban')
		# FIXME unban cmd disabled as is not very usefull atm
		#cmd_unban  = UnBan('ounban', 'cmd_unban')
		cmd_kban = KickBan('okban', 'cmd_kban')
		if get_config_boolean('invert_kickban_order'):
			cmd_kban.invert = True

		weechat.hook_config('plugins.var.python.%s.enable_multiple_kick' %SCRIPT_NAME, 'enable_multiple_kick_conf_cb', '')
		weechat.hook_config('plugins.var.python.%s.merge_bans' %SCRIPT_NAME, 'merge_bans_conf_cb', '')
		weechat.hook_config('plugins.var.python.%s.invert_kickban_order' %SCRIPT_NAME, 'invert_kickban_order_conf_cb', '')
	else:
		weechat.prnt('', "%s%s: This scripts requires weeutils.py" %(weechat.prefix('error'), SCRIPT_NAME))
		weechat.prnt('', '%s%s: Load failed' %(weechat.prefix('error'), SCRIPT_NAME))

