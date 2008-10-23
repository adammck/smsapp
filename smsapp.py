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
		"in":   "\x1b[46m<< \x1b[0m" }
		
	def log(self, msg, type="info"):
		print self.LOG_PREFIX[type], msg
	
	
	def __init__(self, backend, sender_args=[], receiver_args=[]):
		self.receiver = backend.SmsReceiver(self._incoming_sms, *receiver_args)
		self.sender = backend.SmsSender(*sender_args)
		self.transaction = None
	
	
	def __transaction_id(self):
		return random.randint(11111111, 99999999)
	
	
	def split(self, msg):
		return re.split('\s+', msg, 1)
	
	
	def send(self, dest, msg, buffer=False):
		# if something iterable was passed (like an array),
		# then assme that each element is a line of text
		if hasattr(msg, "__iter__"):
			msg = "\n".join(msg)
		
		# call the BEFORE hook
		if hasattr(self, "before_outgoing"):
			self.before_outgoing(dest, msg)
		
		# log to stdout and send the message
		self.log("%s: %r (%d)" % (dest, msg, len(msg)), "out")
		self.sender.send(dest, msg, buffer=buffer)
		
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
	
	
	def _incoming_sms(self, caller, msg):
		self.log("%s: %r" % (caller, msg), "in")
		self.transaction = self.__transaction_id()
		
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
		("slug",    "([a-z0-9\-]+)"),
		("letters", "([a-z]+)"),
		("numbers", "(\d+)"))
	
	def __init__(self):
		self.regexen = []
	
	def prepare(self, str):
		for token, regex in self.TOKEN_MAP:
			str = str.replace("(%s)" % token, regex)
		return re.compile("^%s$" % str, re.IGNORECASE)
	
	def __call__(self, *regex_strs):
		def decorator(func):
			for rstr in regex_strs:
				regex = self.prepare(rstr)
				self.regexen.append((regex, func))
			return func
		return decorator
	
	def match(self, sself, str):
		for pat, func in self.regexen:
			match = pat.match(str)
			if match:
				return (func, match.groups())
		raise ValueError("No method matching %r" % str)




if __name__ == "__main__":

	
	# a simple demo application
	class TestApp(SmsApplication):
		kw = SmsKeywords()
		
		@kw("help")
		def help(self, caller):
			self.respond("Here is some help")
		
		def incoming_sms(self, caller, msg):
			#self.respond("I don't understand")
			pass

	
	import kannel
	TestApp(backend=kannel, sender_args=["user", "pass"]).run()

	while True:
		time.sleep(1)

