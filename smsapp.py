#!/usr/bin/env python
# vim: noet

import re


class SmsApplication():
	LOG_PREFIX = {
		"info":  "   ",
		"warn": "\x1b[41mERR\x1b[0m",
		"out":  "\x1b[45m >>\x1b[0m",
		"in":   "\x1b[46m<< \x1b[0m" }
		
	def log(self, msg, type="info"):
		print self.LOG_PREFIX[type], msg

	def __init__(self, backend, sender_args=[], receiver_args=[]):
		self.receiver = backend.SmsReceiver(self._incoming_sms, *receiver_args)
		self.sender = backend.SmsSender(*sender_args)
	
	def split(self, msg):
		return re.split('\s+', msg, 1)
	
	def send(self, dest, msg, buffer=False):
		# if something iterable was passed (like an array),
		# then assme that each element is a line of text
		if hasattr(msg, "__iter__"):
			msg = "\n".join(msg)
		
		# log to stdout and send the message
		self.log("%s: %r" % (dest, msg), "out")
		self.sender.send(dest, msg, buffer=buffer)
	
	def flush(self):
		self.sender.flush()
	
	def _incoming_sms(self, caller, msg):
		self.log("%s: %r" % (caller, msg), "in")
		
		try:
			if hasattr(self, "kw"):
				func, captures = self.kw.match(self, msg)
				func(self, caller, *captures)
				return
				
		except ValueError:
			self.log("No matching method", "warn")
		
		# the application isn't using sms keyword decorators,
		# or nothing matched. either way, dispatch to the
		# "incomming_sms" method, which should be overloaded
		self.incoming_sms(caller, msg)
	
	def incoming_sms(self, caller, msg):
		pass
	
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
	
	def __call__(self, regex_str):
		def decorator(func):
			regex = self.prepare(regex_str)
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
	class TestApp(SmsApplication):
		def incoming_sms(self, caller, msg):
			self.send(caller, "OMG like that's *so* interesting LOLZ")
	
	import gnokii, time
	app = TestApp(backend=gnokii, sender_args=["user", "pass"])
	#app.send("12064849177", "wat")
	app.run()

	while True:
		time.sleep(1)

