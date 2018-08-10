""" msg_broker.py - A message broker for Edge Message Protocol (EMP) messages.
    Msgs received are enqued for receipt and dequed/served on request.

    The broker consists of 3 main components:
        MsgReceiver     - Watchers for incoming messages over TCP/IP. Runs as
                            a thread.
        RequestWatcher  - Watches for incoming TCP/IP msg fetch requests (ex: A
                            loco checking its msgqueue), serving msgs as 
                            appropriate. Runs as a Thread.
        Broker          - The public interface. Manages the MsgReceiver, 
                            RequestWatcher, and outgoing message queues.

    Message Specification:
        EMP V4 (specified in msg_spec/S-9354.pdf) with fixed-format messages 
        containing a variable-length header section.
        See README.md for implementation specific information.

    Note: Data is not persistent - when broker execution is terminated, all
    unfetched msgs are lost.

    Note: For this simulation/demo implementation, we can assume a minimal load,
    therefore, no session management is performed - a connection to the broker
    must be created each time a msg is sent to, or fetched from, the broker.

    Author:
        Dustin Fast, 2018
"""
import socket
import ConfigParser
from time import sleep
from threading import Thread
from msg_lib import Message, MsgQueue

# Import config data
config = ConfigParser.RawConfigParser()
config.read('conf.dat')

BROKER = config.get('messaging', 'broker')
MAX_TRIES = config.get('misc', 'max_retries')
BROKER_RECV_PORT = config.get('messaging', 'send_port')
BROKER_FETCH_PORT = config.get('messaging', 'fetch_port')
MAX_MSG_SIZE = config.get('messaging', 'max_msg_size')

# Globals
g_new_msgs = MsgQueue()  # Msgs awaiting placment in g_outgoing_queues
g_outgoing_queues = {}  # Dict of msg queues: { dest_addr: Message }

class _FetchWatcher(Thread):  # TODO: move to def of Broker class, then no globals
    """ Watches for incoming TCP/IP msg requests (i.e.: A loco or the BOS
        checking its msg queue) and serves msgs as appropriate.
        Usage: Instantiate, then run as a thread with _FetchWatcher.start()
    """
    def __init__(self):
        """ Instantiates a RequestWatcher object.
        """
        Thread.__init__(self)  # init parent
        
    def run(self):
        """
        """
        # Init listener
        sock = socket.socket()
        sock.bind((BROKER, BROKER_FETCH_PORT))
        sock.listen(1)

        while True:
            # Block until a a fetch request is received
            print('Watching on ' + str(BROKER_FETCH_PORT) + '.')
            conn, client = sock.accept()
            print ('Fetch request received from: ' + str(client))

            # Try MAX_TRIES to process request, responding with 'OK' or 'EMPTY'
            recv_tries = 0
            while True:
                recv_tries += 1
                queue_name = conn.recv(MAX_MSG_SIZE).decode()
                print('' + queue_name + ' fetch requested.')

                # Ensure queue exists and is not empty
                # try:
                msg = g_outgoing_queues[queue_name].pop()
                # except Exception:
                #     conn.send('EMPTY'.encode())
                #     break

                conn.send('OK'.encode())
                conn.send(msg.raw_msg.encode('hex'))  # Send msg

                # Acck with sender
                conn.send('OK'.encode())
                break

            # We're done with client connection, so close it.
            conn.close()
            print('Closing after 1st msg fetched for debug')
            break  # debug

        # Do cleanup
        sock.close()
        print('Watcher Closed.')  # debug

class _MsgReceiver(Thread):  # TODO: move to def of Broker class
    """ Watches for incoming messages over TCP/IP on the interface and port 
        specified.
        Usage: Instantiate, then run as a thread with _MsgReceiver.start()
    """
    def __init__(self):
        """ Instantiates a MsgReceiver object.
        """  
        Thread.__init__(self)  # init parent

    def run(self):
        """ Called on _MsgReceiver.start(), blocks until a message is received, 
            processes it, 
        """
        global g_new_msgs

        # Init TCP/IP listener
        sock = socket.socket()
        sock.bind((BROKER, BROKER_RECV_PORT))
        sock.listen(1)

        while True:
            # Block until a send request is received
            print('Listening on ' + str(BROKER_RECV_PORT) + '.')
            conn, client = sock.accept()
            print ('Snd request received from: ' + str(client))

            # Try MAX_TRIES to recv msg, responding with either 'OK',
            # 'RETRY', or 'FAIL'.
            recv_tries = 0
            while True:
                recv_tries += 1
                raw_msg = conn.recv(MAX_MSG_SIZE).decode()
                try:
                    msg = Message(raw_msg.decode('hex'))
                except Exception as e:
                    errstr = 'Transfer failed due to ' + str(e)
                    if recv_tries < MAX_TRIES:
                        print(errstr + '... Will retry.')
                        conn.send('RETRY'.encode())
                        continue
                    else:
                        print(errstr + '... Retries exhausted.')
                        conn.send('FAIL'.encode())
                        break
                
                # Add msg to global new_msgs queue, then ack with sender
                g_new_msgs.push(msg)
                conn.send('OK'.encode())
                break

            # We're done with client connection, so close it.
            conn.close()
            print('Closing after 1st msg received for debug')
            break  # debug

        # Do cleanup   
        sock.close()
        print('Receiver Closed.')  # debug
        

class Broker(object):  # TODO: test mp?
    """ The message broker.
    """
    def __init__(self):
        """
        """
        self.msg_recvr = _MsgReceiver()
        self.req_watcher = _FetchWatcher()

    def run(self):
        """ Start the msg broker, including the msg receiver and msg watcher 
            threads.
        """
        global g_new_msgs

        # Start msg receiver and request watcher threads
        self.msg_recvr.start()
        self.req_watcher.start()

        for i in range(10):
            # Enqueue any msgs waiting to be enqued in a queue keyed by the 
            # dest address. A msg enqued this way will stay there until fetched
            # by a client.
            while not g_new_msgs.is_empty():
                msg = g_new_msgs.pop()
                if not g_outgoing_queues.get(msg.dest_addr):
                    g_outgoing_queues[msg.dest_addr] = MsgQueue()
                g_outgoing_queues[msg.dest_addr].push(msg)

                print('Broker: Enqued outgoing msg for: ' + msg.dest_addr)
            
            # TODO: Parse all msgs for TTL
            
            sleep(2)

        # Do cleanup
        print('Broker closed.')  # debug


if __name__ == '__main__':
    global on_flag
    on_flag = True
    broker = Broker()
    broker.run()
    print('end main')

