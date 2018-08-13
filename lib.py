""" lib.py - A collection of shared classes and helpers for loco_sim.

    Author: Dustin Fast, 2018
"""

import logging
from json import loads
from ConfigParser import RawConfigParser
from logging.handlers import RotatingFileHandler as RFHandler

# Init conf
config = RawConfigParser()
config.read('conf.dat')

# Import conf data
LOG_NAME = config.get('logging', 'name')
LOG_FILES = config.get('logging', 'num_logfiles')
LOG_SIZE = config.get('logging', 'max_logfile_size')
TRACK_RAILS = config.get('track', 'track_rails')
TRACK_BASES = config.get('track', 'track_bases')

# Decalare global logger (defined at eof)
logger = None

#############################################################
# Railroad/Locomotive Component Classes                     #
#############################################################

class Track(object):
    """ A representation of the track, including mileposts, and radio base 
        stations with their associated coverage areas.
    
        self.bases = A dict of radio base stations, used by locos  to send msgs. 
            Format: { BASEID: BASE_OBJECT }
        self.mp_objects = Used to associate BRANCH/MP with MPOBJ.
            Format: { MP: MPOBJ }
        self.mp_linear = A representation of the track in order of mps.
            Format: [ MP1, ... , MPn ], where MP1 < MPn
        self.mp_linear_rev = A represention the track in reverse order of mps.
            Format: [ MPn, ... , MP1], where MP1 < MPn
        Note: BASEID = string, MP/lat/long = floats, MPOBJs = Milepost objects.
    """
    def __init__(self, track_file=TRACK_RAILS, bases_file=TRACK_BASES):
        self.bases = {}
        self.mp_objects = {}
        self.mp_linear = []
        self.mp_linear_rev = []

        logger.info('Initializing Track...')

        # Populate self.bases from TRACK_BASES json
        try:
            with open(bases_file) as base_data:
                bases = loads(base_data.read())
        except Exception as e:
            raise Exception('Error reading ' + bases_file + ': ' + str(e))

        for b in bases:
            try:
                baseID = b['id']
                coverage_start = float(b['coverage'][0])
                coverage_end = float(b['coverage'][1])
            except ValueError:
                logger.warning('Discarding base "' + baseID + '": Conversion Error')
                continue
            except KeyError:
                raise Exception('Invalid data in ' + bases_file + '.')

            self.bases[baseID] = Base(baseID, coverage_start, coverage_end)

        # Populate self.mp_objects from TRACK_RAILS json
        try:
            with open(TRACK_RAILS) as rail_data:
                mileposts = loads(rail_data.read())
        except Exception as e:
            raise Exception('Error reading ' + TRACK_RAILS + ': ' + str(e))

        # Build self.mp_objects dict
        for m in mileposts:
            try:
                mp = float(m['milemarker'])
                lat = float(m['lat'])
                lng = float(m['long'])
            except ValueError:
                logger.warning("Discarding mp '" + str(mp) + "': Conversion Error")
                continue
            except KeyError:
                raise Exception('Invalid data in ' + track_file + '.')

            self.mp_objects[mp] = Milepost(mp, lat, lng)

        # Populate self.mp_linear and self.mp_linear_rev from self.mp_objects
        for mp in sorted(self.mp_objects.keys()):
            self.mp_linear.append(mp)
        self.mp_linear_rev = self.mp_linear[::-1]

    def _get_next_mp(self, curr_mp, distance):
        """ Given a curr_mp and distance, returns the nearest mp marker at
            curr_mp + distance. Also returns any difference not accounted
            for.
            Accepts:
                curr_mp  = Curr location (a Milepost)
                distance = Distance in miles (neg dist denotes decreasing DOT)
            Returns:
                next_mp   = nearest mp for curr_mp + distance without going over
                dist_diff = difference between next_mp and actual location
            Note: If next_mp = curr_mp, diff = distance.
                  If no next mp (end of track), returns None.
        """
        # If no distance, next_mp is curr_mp
        if distance == 0:
            return curr_mp, distance

        # Working vars
        mp = curr_mp.mp
        target_mp = mp + distance
        dist_diff = 0
        next_mp = None

        # Set the milepost object list to iterate, depending on direction
        if distance > 0:
            mps = self.mp_linear
        elif distance < 0:
            mps = self.mp_linear_rev

        # Find next mp marker, noting unconsumed distance
        for i, marker in enumerate(mps):
            if marker == target_mp:
                next_mp = marker
                dist_diff = 0
                break
            elif (distance > 0 and marker > target_mp) or \
                 (distance < 0 and marker < target_mp):
                next_mp = mp
                if i > 0:
                    next_mp = mps[i - 1]
                dist_diff = abs(target_mp - next_mp)
                break

        # If we didn't find a next mp (i.e. end of track)
        if not next_mp:
            return

        # Get mp object associated with next_mp
        next_mp_obj = self.get_milepost_at(next_mp)
        if not next_mp_obj:
            # Print debug info
            log_str = '_get_next_mp failed to find a next milepost from: '
            log_str += str(mps) + ', '
            log_str += 'cur_mp: ' + str(mp) + ', '
            log_str += 'moved : ' + str(distance) + ', '
            log_str += 'tgt_mp: ' + str(target_mp) + ', '
            log_str += 'mp_idx: ' + str(i) + ', '
            log_str += 'nxt_mp: ' + str(next_mp) + ', '
            log_str += 'disdif: ' + str(dist_diff) + '.'
            logger.error(log_str) 
            raise Exception(log_str)

        return next_mp_obj, dist_diff

    def get_milepost_at(self, mile):
        """ Returns the Milepost at distance (a float) iff one exists.
        """
        return self.mp_objects.get(mile, None)


class Loco(object):
    """ An abstration of a locomotive.
    """
    def __init__(self, id_number):
        """
        """
        self.ID = str(id_number)
        self.speed = None
        self.heading = None
        self.direction = None
        self.milepost = None
        self.current_base = None
        self.bases_inrange = []

    def __str__(self):
        """ Returns a string representation of the locomotive.
        """
        ret_str = 'Loco ' + self.ID + ' at mp '
        ret_str += str(self.milepost) + ' traveling in an ' + self.direction
        ret_str += 'going ' + str(self.speed) + 'mph'
        return ret_str


class Milepost:
    """ An abstraction of a milepost.
        self.mp = (Float) The numeric milepost
        self.lat = (Float) Latitude of milepost
        self.long = (Float) Longitude of milepost
    """
    def __init__(self, mp, latitude, longitude):
        self.mp = mp
        self.lat = latitude
        self.long = longitude

    def __str__(self):
        """ Returns a string representation of the milepost """
        return str(self.mp)


class Base:
    """ An abstraction of a base station, including it's coverage area
        self.ID = (String) The base station's unique identifier
        self.coverage_start = (Float) Coverage start milepost
        self.coverage_end = (Float) Coverage end milepost
    """
    def __init__(self, baseID, coverage_start, coverage_end):
        self.ID = baseID
        self.cov_start = coverage_start
        self.cov_end = coverage_end

    def __str__(self):
        """ Returns a string representation of the base station """
        return self.ID

    def covers_milepost(self, milepost):
        """ Given a milepost, returns True if this base station provides 
            coverage at that milepost, else returns False.
        """
        return milepost.mp >= self.cov_start and milepost <= self.cov_end


#############################################################
# Input Classes (REPL, Logger, and Web)                     #
#############################################################

class REPL(object):
    """ A dynamic Read-Eval-Print-Loop. I.e. A command line interface.
        Contains two predefined commands: help, and exit. Additional cmds may
        be added with add_cmd(). These additional cmds all operate on the object
        given as the context. 
        Note: Assumes all expressions provided are well-formed. 
    """

    def __init__(self, context, prompt='>>', welcome_msg=None):
        """ Instantiates an REPL object.
            context: The object all commands operate on.
            prompt: The REPL prompt.
            welcome: String to display on REPL start.
        """
        self.context = context
        self.prompt = prompt
        self.welcome_msg = welcome_msg
        self.exit_command = None
        self.commands = {'help': 'self._help()',
                         'exit': 'self._exit()'
                         }

    def start(self):
        """ Starts the REPL.
        """
        if self.welcome_msg:
            print(self.welcome_msg)
        while True:
            # TODO: readline
            uinput = raw_input(self.prompt)
            cmd = self.commands.get(uinput)

            # Process user input
            if not uinput:
                continue  # if null input
            if not cmd:
                print('Invalid command. Try "help".')
            else:
                eval(cmd)

    def add_cmd(self, cmd_txt, expression):
        """ Makes a command available via the REPL
                cmd_txt: Txt cmd entered by the user
                expression: A well-formed python expression string.
                            ex: 'print('Hello World)'
        """
        if cmd_txt == 'help' or cmd_txt == 'exit':
            raise ValueError('An internal cmd override was attempted.')
        self.commands[cmd_txt] = 'self.context.' + expression

    def set_exitcmd(self, cmd):
        """ Specifies a command to run on exit. Example: 'stop', if a stop
            command is defined and performs cleanup, etc.
        """
        self.exit_command = cmd

    def _help(self):
        """ Outputs all available commands to the console, excluding 'help'.
        """
        cmds = [c for c in sorted(self.commands.keys()) if c != 'help']
        if cmds:
            print('\n'.join(cmds))
        else:
            print('No commands defined.')

    def _exit(self):
        """ Calls exit() after doing the cmd specified by self.exit_command.
        """
        if self.exit_command:
            eval(self.commands[self.exit_command])
        exit()


class RotatingLog(object):  # TODO: Test needs write access if nofile exists
    """ A wrapper for Python's logging module. Implements a log with console
        output and rotating log files.
        Example usage: RotatingLog.error('Invalid Value!')
                       RotatingLog.info('Started Succesfully.')
    """
    def __init__(self, name=LOG_NAME, files=LOG_FILES, max_size=LOG_SIZE):
        """
        """
        self.logger = logging.getLogger()

        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')

        # Console handler (log stmts go to console in addition to log file)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)

        # Log file rotation handler (specifies how to rotate log files)
        rotate_handler = RFHandler(name.lower() + ".log", 
                                   max_size * 1000000,
                                   files)  
        rotate_handler.setLevel(logging.INFO)
        rotate_handler.setFormatter(formatter)

        # Init logger
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(rotate_handler)
        self.logger.addHandler(console_handler)


# Init global logger
logger = RotatingLog().logger