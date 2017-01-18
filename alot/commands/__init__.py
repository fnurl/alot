# Copyright (C) 2011-2012  Patrick Totzke <patricktotzke@gmail.com>
# This file is released under the GNU GPL, version 3 or a later revision.
# For further details see the COPYING file
import argparse
import glob
import logging
import os
import re

from ..settings import settings
from ..helper import split_commandstring, string_decode


class Command(object):

    """base class for commands"""
    repeatable = False

    def __init__(self):
        self.undoable = False
        self.help = self.__doc__

        class_ = type(self)
        class_name = class_.__name__
        cmdname, mode = reverse_lookup_command(class_)

        # fetch and set pre and post command hooks
        # they are set to None if not defined in the hooks file
        get_hook = settings.get_hook
        self.prehook = (get_hook('pre_%s_%s' % (mode, cmdname)) or
                        get_hook('pre_global_%s' % cmdname))
        self.posthook = (get_hook('post_%s_%s' % (mode, cmdname)) or
                         get_hook('post_global_%s' % cmdname))

        logging.debug("%s prehook: %s", class_name, str(self.prehook))
        logging.debug("%s posthook: %s", class_name, str(self.posthook))

    def apply(self, caller):
        """code that gets executed when this command is applied"""
        pass


class CommandCanceled(Exception):
    """ Exception triggered when an interactive command has been cancelled
    """
    pass

COMMANDS = {
    'search': {},
    'envelope': {},
    'bufferlist': {},
    'taglist': {},
    'thread': {},
    'global': {},
}

# classes as keys with (cmdname, mode) as values
REVERSE_COMMANDS = {}


def lookup_command(cmdname, mode):
    """
    returns commandclass, argparser and forced parameters used to construct
    a command for `cmdname` when called in `mode`.

    :param cmdname: name of the command to look up
    :type cmdname: str
    :param mode: mode identifier
    :type mode: str
    :rtype: (:class:`Command`, :class:`~argparse.ArgumentParser`,
            dict(str->dict))
    """
    if cmdname in COMMANDS[mode]:
        return COMMANDS[mode][cmdname]
    elif cmdname in COMMANDS['global']:
        return COMMANDS['global'][cmdname]
    else:
        return None, None, None


def lookup_parser(cmdname, mode):
    """
    returns the :class:`CommandArgumentParser` used to construct a
    command for `cmdname` when called in `mode`.
    """
    return lookup_command(cmdname, mode)[1]


def reverse_lookup_command(class_):
    """
    returns (cmdname, mode) for a command class

    :param class_: the class used to look up the cmdname and mode
    :type class_: class
    :rtype: (str, str) the class_ is registered, if not return (None, None)
    """
    return REVERSE_COMMANDS.get(class_, (None, None))


class CommandParseError(Exception):

    """could not parse commandline string"""
    pass


class CommandArgumentParser(argparse.ArgumentParser):

    """
    :class:`~argparse.ArgumentParser` that raises :class:`CommandParseError`
    instead of printing to `sys.stderr`"""
    def exit(self, message):
        raise CommandParseError(message)

    def error(self, message):
        raise CommandParseError(message)


class registerCommand(object):

    """
    Decorator used to register a :class:`Command` as
    handler for command `name` in `mode` so that it
    can be looked up later using :func:`lookup_command`.

    Consider this example that shows how a :class:`Command` class
    definition is decorated to register it as handler for
    'save' in mode 'thread' and add boolean and string arguments::

        @registerCommand('thread', 'save', arguments=[
            (['--all'], {'action': 'store_true', 'help':'save all'}),
            (['path'], {'nargs':'?', 'help':'path to save to'})],
            help='save attachment(s)')
        class SaveAttachmentCommand(Command):
            pass

    """
    def __init__(self, mode, name, help=None, usage=None,
                 forced=None, arguments=None):
        """
        :param mode: mode identifier
        :type mode: str
        :param name: command name to register as
        :type name: str
        :param help: help string summarizing what this command does
        :type help: str
        :param usage: overides the auto generated usage string
        :type usage: str
        :param forced: keyword parameter used for commands constructor
        :type forced: dict (str->str)
        :param arguments: list of arguments given as pairs (args, kwargs)
                          accepted by
                          :meth:`argparse.ArgumentParser.add_argument`.
        :type arguments: list of (list of str, dict (str->str)
        """
        self.mode = mode
        self.name = name
        self.help = help
        self.usage = usage
        self.forced = forced or {}
        self.arguments = arguments or []

    def __call__(self, class_):
        helpstring = self.help or class_.__doc__
        argparser = CommandArgumentParser(description=helpstring,
                                          usage=self.usage,
                                          prog=self.name, add_help=False)
        for args, kwargs in self.arguments:
            argparser.add_argument(*args, **kwargs)
        COMMANDS[self.mode][self.name] = (class_, argparser, self.forced)
        REVERSE_COMMANDS[class_] = (self.name, self.mode)
        return class_


def commandfactory(cmdline, mode='global'):
    """
    parses `cmdline` and constructs a :class:`Command`.

    :param cmdline: command line to interpret
    :type cmdline: str
    :param mode: mode identifier
    :type mode: str
    """
    # split commandname and parameters
    if not cmdline:
        return None
    logging.debug('mode:%s got commandline "%s"', mode, cmdline)
    # allow to shellescape without a space after '!'
    if cmdline.startswith('!'):
        cmdline = 'shellescape \'%s\'' % cmdline[1:]
    cmdline = re.sub(r'"(.*)"', r'"\\"\1\\""', cmdline)
    try:
        args = split_commandstring(cmdline)
    except ValueError as e:
        raise CommandParseError(e.message)
    args = [string_decode(x, 'utf-8') for x in args]
    logging.debug('ARGS: %s', args)
    cmdname = args[0]
    args = args[1:]

    # unfold aliases
    # TODO: read from settingsmanager

    # get class, argparser and forced parameter
    (cmdclass, parser, forcedparms) = lookup_command(cmdname, mode)
    if cmdclass is None:
        msg = 'unknown command: %s' % cmdname
        logging.debug(msg)
        raise CommandParseError(msg)

    parms = vars(parser.parse_args(args))
    parms.update(forcedparms)

    logging.debug('cmd parms %s', parms)

    # create Command
    cmd = cmdclass(**parms)

    return cmd


pyfiles = glob.glob1(os.path.dirname(__file__), '*.py')
__all__ = list(filename[:-3] for filename in pyfiles)
