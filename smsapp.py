#!/usr/bin/env python
# vim: noet

import random, re


class CallerError(Exception):
	"""Raised during incoming SMS processing, to inform the
	   caller that they did something wrong, and abort the action"""
	pass

class Response(Exception):
	"""Raised during incoming SMS processing (probably by SmsApplication.respond,
	   but the actual handler method can do it too), to trigger an immediate SMS
	   response to the caller and abort processing"""
	pass


class SmsApplication():
	LOG_PREFIX = {
		"info": "\x1b[40m   \x1b[0m",
		"warn": "\x1b[41mERR\x1b[0m",
		"out":  "\x1b[45m >>\x1b[0m",
		"in":   "\x1b[46m<< \x1b[0m",
		"virt": "\x1b[46m<- \x1b[0m" }
	
	def log(self, msg, type="info"):
		print self.LOG_PREFIX[type], msg
	
	
	def __init__(self, backend, sender_args=[], receiver_args=[]):
		self.receiver = backend.SmsReceiver(self._incoming_sms, *receiver_args)
		self.sender = backend.SmsSender(*sender_args)
		self.transaction = None
	
	
	def new_transaction(self, caller):
		return random.randint(11111111, 99999999)
	
	
	def __incoming_number(self, number):
		# as default, drop the international
		# plus, since all numbers that we deal
		# with are international. override in
		# apps to perform black magic
		return number.lstrip("+")
	
	
	def __outgoing_number(self, number):
		# add the international PLUS, if not present
		if number.startswith("+"): return number
		else: return "+" + number
	
	
	def send(self, dest, msg, buffer=False):
		
		# if something iterable was passed (like an array),
		# then assme that each element is a line of text
		if hasattr(msg, "__iter__"):
			msg = "\n".join(msg)
		
		# drop any trailing whitespace
		msg = msg.strip()
		
		# call the BEFORE hook
		if hasattr(self, "before_outgoing"):
			self.before_outgoing(dest, msg)
		
		
		try:
			# log to stdout and (attempt to) send the message
			self.log("%s: %r (%d)" % (dest, msg, len(msg)), "out")
			
			# transform the destination at the
			# last minute, in case we need to
			# perform any scary black magic
			real_dest = self.__outgoing_number(dest)
			self.sender.send(real_dest, msg, buffer=buffer)
		
		# the message couldn't be sent. we run many
		# backends, so it could be any reason...
		except Exception, err:
			self.log("Outgoing message failed: %s" % err, "warn")
		
		
		# and the AFTER hook
		if hasattr(self, "after_outgoing"):
			self.after_outgoing(dest, msg)
	
	
	# sneaky hack: allow the incoming handler method to
	# call self.respond, which cancels further processing
	# by raising a friendly (not error!) exception for
	# SmsApplication._incoming_sms to catch
	def respond(self, msg):
		raise Response(msg)
	
	
	def flush(self):
		self.sender.flush()
	
	
	INCOMING_SPLIT = re.compile(r"(?:\s*[;,#]\s*|\s{3,})")
	def _incoming_sms(self, caller, msg, virtual=False):
		
		# transform the caller, in case we
		# need to perform any black magic
		caller = self.__incoming_number(caller)
		
		if not virtual:
			# this is a raw incoming message
			self.transaction = self.new_transaction(caller)
			self.log("%s: %r" % (caller, msg), "in")
			
			# multiple commands can be issued in a single
			# incoming sms, so attempt to split up the message,
			# and recurse for each "chunk", if there are any
			chunks = re.split(self.INCOMING_SPLIT, msg)
			if len(chunks) > 1:
				for chunk in chunks:
					self._incoming_sms(caller, chunk, True)
				
				# all chunks have been processed
				# independantly, so ignore the
				# real message (todo: more logging?)
				return
		
		else:
			# this message is part of a larger message,
			# so behave as normal, except log differently
			self.log("%s: %r" % (caller, msg), "virt")
		
		
		# call the pre-incoming hook
		if hasattr(self, "before_incoming"):
			self.before_incoming(caller, msg)
		
		try:
			# if we are using magic keywords,
			# then attempt to find a match
			if hasattr(self, "kw"):
				try:
					func, captures = self.kw.match(self, msg)
					func(self, caller, *captures)
					
				# nothing was found, use default handler
				except ValueError:
					self.incoming_sms(caller, msg)
		
			# the application isn't using sms keyword decorators,
			# "incoming_sms" method, which should be overloaded
			else: self.incoming_sms(caller, msg)
			
		# the request could not be completed
		# because THE USER did something wrong
		except CallerError, ex:
			self.send(caller, ex.args)
		
		# the request succeeded with a
		# response back to the caller
		except Response, ex:
			self.send(caller, ex.args)
		
		
		# call the post-incoming hook
		if hasattr(self, "after_incoming"):
			self.after_incoming(caller, msg)
		
		# the transaction is DONE, so
		# prevent anyone from accidently
		# using the ID again elsewhere
		self.transaction = None
	
	
	def incoming_sms(self, caller, msg):
		self.log("Incoming message ignored", "warn")
	
	
	def run(self):
		app = self.__class__.__name__
		print "Starting %s..." % app
		self.receiver.run()


class SmsKeywords(object):
	TOKEN_MAP = (
		("slug",     "([a-z0-9\-]+)"),
		("letters",  "([a-z]+)"),
		("numbers",  "(\d+)"),
		("whatever", "(.+)"))
	
	def __init__(self):
		self.regexen = []
		self.prefix = ""
		self.pattern = "^%s$"
	
	def prepare(self, prefix, suffix):
		
		
		# no prefix is defined, so match
		# only the suffix (so simple!)
		if prefix == "":
			str = suffix
		
		# we have a prefix, but no suffix,
		# so accept JUST the prefix
		elif suffix == "":
			str = prefix
		
		# the most common case; we have both a
		# prefix and suffix, so simpley join
		# them with a space
		else: str = prefix + " " + suffix
		
		
		# also assume that one space means
		# "any amount of whitespace"
		str = str.replace(" ", "\s+")
		
		# replace friendly tokens with real chunks
		# of regex, to make the patterns more readable
		for token, regex in self.TOKEN_MAP:
			str = str.replace("(%s)" % token, regex)
		
		return re.compile(self.pattern % str, re.IGNORECASE)
	
	
	def __call__(self, *regex_strs):
		def decorator(func):
			
			# make the current prefix into something
			# iterable (so multiple prefixes can be
			# specified as list, or single as strig)
			prefixen = self.prefix
			if not hasattr(self.prefix, "__iter__"):
				prefixen = [self.prefix]
			
			# iterate and add all combinations of
			# prefix and regex for this keyword
			for prefix in prefixen:			
				for rstr in regex_strs:
					regex = self.prepare(prefix, rstr)
					print "Handler: %s" % regex.pattern
					self.regexen.append((regex, func))
			
			return func
		return decorator
	
	
	def match(self, sself, str):
		for pat, func in self.regexen:
			match = pat.match(str)
			if match:
				return (func, match.groups())
		raise ValueError("No method matching %r" % str)
	
	# a semantic way to add a default
	# handler (when nothing else is matched)
	def blank(self):
		return self.__call__("")
	
	# another semantic way to add a catch-all
	# most useful with a prefix for catching
	# invalid syntax and responding with help
	def invalid(self):
		return self.__call__("(whatever)")




if __name__ == "__main__":
	
	
	# a simple demo application
	class TestApp(SmsApplication):
		kw = SmsKeywords()
		
		
		kw.prefix = "help" # --------------------
		
		@kw("letters")
		def help_letters(self, caller):
			self.respond("a, b, c, d, e, f, g")
		
		@kw.blank()
		def help(self, caller):
			self.respond("Here is some help")
		
		
		kw.prefix = "repeat" # ------------------
		
		@kw("(numbers) (.+)")
		def letter(self, caller, number, str):
			self.respond((str + " ") * int(number))
		
		@kw.blank()
		@kw.invalid()
		def repeat_inv(self, caller, msg):
			raise CallerError("Usage: REPEAT <NUMBER> <STRING>")

	
	import kannel
	TestApp(backend=kannel, sender_args=["user", "pass"]).run()

	while True:
		time.sleep(1)

