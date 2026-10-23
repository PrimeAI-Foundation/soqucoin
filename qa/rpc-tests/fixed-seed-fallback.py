#!/usr/bin/env python3
# Copyright (c) 2026 The Soqucoin developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

#
# Fixed-seed fallback (CConnman::ThreadOpenConnections). Sixty seconds after
# the connection thread starts, the fixed seeds enter addrman once if the node
# has either an empty addrman or no completed outbound connection. This covers
# the second condition, which a non-empty addrman alone does not satisfy: one
# peer hands the node a single address that never answers, DNS seeding is off,
# and every outbound attempt goes through a proxy that is not listening, so no
# socket leaves the host. The node must still add the fixed seeds; the log line
# is the observable (regtest declares no fixed seeds, so the table added is
# empty). The clock is moved with setmocktime rather than waited out.
#

import os
import time
from test_framework.mininode import (CAddress, NODE_NETWORK, NetworkThread, NodeConn,
                                     SingleNodeConnCB, msg_addr, wait_until)
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import p2p_port, start_node

# A routable address that nothing answers on; outbound attempts fail at the proxy.
STALE_IP = "250.1.1.1"
REGTEST_PORT = 18444
FALLBACK_LINE = ("Adding fixed seed nodes: no outbound connection has completed "
                 "60 seconds after start (addrman holds 1 addresses)")


class FixedSeedFallbackTest(BitcoinTestFramework):
    def __init__(self):
        super().__init__()
        self.setup_clean_chain = True
        self.num_nodes = 1

    def setup_network(self, split=False):
        self.is_network_split = False
        # -proxy makes every outbound connection fail locally, and turns
        # -listen off unless it is set, which the inbound peer below needs.
        self.nodes = [start_node(0, self.options.tmpdir,
                                 ["-debug=net", "-dnsseed=0", "-proxy=127.0.0.1:1", "-listen=1"])]

    def debug_log(self):
        with open(os.path.join(self.options.tmpdir, "node0", "regtest", "debug.log"), encoding="utf-8") as f:
            return f.read()

    def run_test(self):
        node = self.nodes[0]
        peer = SingleNodeConnCB()
        peer.add_connection(NodeConn('127.0.0.1', p2p_port(0), node, peer))
        NetworkThread().start()
        peer.wait_for_verack()

        # One address enters addrman from the peer; the peer's addr token
        # bucket starts with one token, which this one address spends.
        addr = CAddress()
        addr.time = int(time.time())
        addr.nServices = NODE_NETWORK
        addr.ip = STALE_IP
        addr.port = REGTEST_PORT
        msg = msg_addr()
        msg.addrs = [addr]
        peer.connection.send_message(msg)
        peer.sync_with_ping()

        # Nothing has been added before the window closes.
        assert "Adding fixed seed nodes" not in self.debug_log()

        # Move the clock past the sixty-second window. The connection thread
        # wakes every half second.
        node.setmocktime(int(time.time()) + 600)
        assert wait_until(lambda: FALLBACK_LINE in self.debug_log(), timeout=20), \
            "the fixed-seed fallback did not fire with one unreachable address in addrman"

        # It fires once.
        time.sleep(2)
        assert self.debug_log().count("Adding fixed seed nodes") == 1

        peer.connection.disconnect_node()


if __name__ == '__main__':
    FixedSeedFallbackTest().main()
