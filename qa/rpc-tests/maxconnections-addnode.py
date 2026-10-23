#!/usr/bin/env python3
# Copyright (c) 2026 The Soqucoin developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

#
# -maxconnections and manually added peers. Peers added with -addnode or the
# addnode RPC have their own limit (MAX_ADDNODE_CONNECTIONS) and sit outside
# -maxconnections: the inbound budget in CConnman::AcceptConnection and the
# descriptor reservation at start-up leave them out, and so must the reduce
# loop in CConnman::ThreadSocketHandler, or a node at its cap with added peers
# on top drops inbound peers it has just accepted. Shape: cap 30, eight peers
# given with -addnode at start and two one-try outbound peers, all on local
# listener sockets that never speak, then 21 inbound peers (the inbound budget
# is 30 - 8 - 1). The node then holds 31 connections, one above the cap; the
# 21 inbound peers must stay and the reduce line must not appear. The added
# peers are given at start so one pass of the added-connections thread
# connects them all; a pass that found only some of them would sleep a minute
# before the rest.
#

import os
import socket
import threading
import time
from test_framework.mininode import NetworkThread, NodeConn, NodeConnCB, wait_until
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, start_node, p2p_port

MAX_CONNECTIONS = 30
MAX_OUTBOUND_CONNECTIONS = 8   # net.h
MAX_ADDNODE_CONNECTIONS = 8    # net.h
FEELER_CONNECTIONS = 1
INBOUND_BUDGET = MAX_CONNECTIONS - MAX_OUTBOUND_CONNECTIONS - FEELER_CONNECTIONS
ONETRY_PEERS = 2
REDUCE_LINE = "attempting to reduce connections"


class SilentListener:
    """A local socket that accepts connections and never speaks. The node counts
    each connection as a peer until its first-message timeout, sixty seconds."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.accepted = []
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.accepted.append(conn)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
        for conn in self.accepted:
            try:
                conn.close()
            except OSError:
                pass


class InboundPeer(NodeConnCB):
    def __init__(self):
        NodeConnCB.__init__(self)
        self.connection = None

    def add_connection(self, conn):
        self.connection = conn


class MaxConnectionsAddnodeTest(BitcoinTestFramework):
    def __init__(self):
        super().__init__()
        self.setup_clean_chain = True
        self.num_nodes = 1

    def setup_network(self, split=False):
        self.is_network_split = False
        self.listeners = [SilentListener() for _ in range(MAX_ADDNODE_CONNECTIONS + ONETRY_PEERS)]
        self.started = time.time()
        args = ["-debug=net", "-maxconnections=%d" % MAX_CONNECTIONS]
        args += ["-addnode=127.0.0.1:%d" % l.port for l in self.listeners[:MAX_ADDNODE_CONNECTIONS]]
        self.nodes = [start_node(0, self.options.tmpdir, args)]

    def debug_log(self):
        with open(os.path.join(self.options.tmpdir, "node0", "regtest", "debug.log"), encoding="utf-8") as f:
            return f.read()

    def peer_counts(self):
        info = self.nodes[0].getpeerinfo()
        inbound = sum(1 for p in info if p["inbound"])
        addnode = sum(1 for p in info if p["addnode"])
        outbound = sum(1 for p in info if not p["inbound"] and not p["addnode"])
        return inbound, addnode, outbound

    def run_test(self):
        node = self.nodes[0]
        listeners = self.listeners
        try:
            assert wait_until(lambda: self.peer_counts()[1] == MAX_ADDNODE_CONNECTIONS, timeout=30), \
                "the added peers did not all connect"

            for listener in listeners[MAX_ADDNODE_CONNECTIONS:]:
                node.addnode("127.0.0.1:%d" % listener.port, "onetry")
            assert wait_until(lambda: self.peer_counts()[2] == ONETRY_PEERS, timeout=30), \
                "the one-try peers did not all connect"

            # The connections exist before the network thread starts: it ends
            # at once when it finds none to serve.
            peers = []
            for _ in range(INBOUND_BUDGET):
                peer = InboundPeer()
                peer.add_connection(NodeConn('127.0.0.1', p2p_port(0), node, peer))
                peers.append(peer)
            NetworkThread().start()
            assert wait_until(lambda: all(p.verack_received for p in peers), timeout=30), \
                "the inbound peers did not all complete the handshake"

            # One above the cap, with the inbound budget exactly used.
            expected_total = MAX_ADDNODE_CONNECTIONS + ONETRY_PEERS + INBOUND_BUDGET
            assert expected_total > MAX_CONNECTIONS
            assert_equal(node.getconnectioncount(), expected_total)

            # The reduce loop runs on every pass of the socket handler; two
            # seconds is many passes.
            time.sleep(2)
            inbound, addnode, outbound = self.peer_counts()
            assert_equal((inbound, addnode, outbound),
                         (INBOUND_BUDGET, MAX_ADDNODE_CONNECTIONS, ONETRY_PEERS))
            assert_equal(node.getconnectioncount(), expected_total)
            assert REDUCE_LINE not in self.debug_log(), "the node tried to reduce connections below the cap"
            assert all(p.connection.state == "connected" for p in peers), "an inbound peer was dropped"

            # The listener peers are still within their first-message window,
            # so every count above was read while they were connected.
            assert time.time() - self.started < 50
        finally:
            for listener in listeners:
                listener.close()


if __name__ == '__main__':
    MaxConnectionsAddnodeTest().main()
