#!/usr/bin/env python3
# Copyright (c) 2026 The Soqucoin developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

#
# Chain id rule (Consensus::Params::nChainIdRequiredHeight, bead 0o4b0): from
# the height every block that is not a legacy block must carry chain id 0x5351
# in the high bits of its version, merge-mined or not; 0 = no rule, which every
# network carries until a release schedules it. The unit test
# (consensus_validation_tests, chainid_required_height) drives the check and
# the miner in process; this covers what it cannot: the -chainidrequiredheight
# regtest path through init and its startup line; the sequence the rule
# completes the merge-mined-only check for, a merge-mined block and the parent
# block that carries its proof of work, solved once and submitted as two
# consecutive blocks of this chain, which both connect below the height and
# whose parent is refused at it; the same parent arriving from a peer that has
# no rule (refused with DoS 100, so the peer is dropped; a loopback peer is
# never banned, only disconnected); the armed node's own blocks at the height;
# and the option's bounds.
#

import os
import struct
import subprocess
import time
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (assert_equal, connect_nodes_bi,
                                 initialize_datadir, soqucoind_processes,
                                 start_node, start_nodes, stop_node)
from test_framework.mininode import CBlockHeader, ser_string, ser_uint256
from test_framework.blocktools import create_block, create_coinbase, serialize_script_num

# Above the regtest AuxPoW start (20), so the merge-mined block of each pair
# below is in the AuxPoW era.
HEIGHT = 30
CHAIN_ID = 0x5351
# What the miner stamps on a direct block: base version 4, chain id 0x5351.
STAMPED_VERSION = (CHAIN_ID << 16) | 4
# The merge-mining tag that precedes the child's hash in the parent's coinbase.
MERGED_MINING_HEADER = b"\xfa\xbe" + b"mm"


class ChainIdRequiredHeightTest(BitcoinTestFramework):
    def __init__(self):
        super().__init__()
        self.setup_clean_chain = True
        self.num_nodes = 2

    def setup_network(self, split=False):
        self.is_network_split = False
        # Node 0 carries the rule. Node 1 has none, and its miner stamps base
        # version 4 with no chain id: a peer on a binary without the rule
        # whose miner does not stamp the id.
        self.nodes = start_nodes(self.num_nodes, self.options.tmpdir,
                                 [["-debug", "-chainidrequiredheight=%d" % HEIGHT],
                                  ["-debug", "-blockversion=4"]])
        connect_nodes_bi(self.nodes, 0, 1)

    def debug_log(self, i):
        with open(os.path.join(self.options.tmpdir, "node%d" % i, "regtest", "debug.log"), encoding="utf-8") as f:
            return f.read()

    def build_pair(self, node, t):
        """A merge-mined block on node's tip and the parent block that proves
        it: the parent's coinbase commits to the child through the merge-mining
        tag, the parent builds on the child as the next block of this chain
        with base version 4 and chain id 0, and one scrypt solution of the
        parent header serves both. Returns the child's hash, its auxpow and the
        parent block; nothing is submitted."""
        aux = node.getauxblock()
        child_hash = aux['hash']
        height = aux['height']
        # The child is timed at the node's clock or one past the median time,
        # whichever is later; the parent follows it by a second.
        median = node.getblockheader(node.getbestblockhash())['mediantime']
        child_time = max(t, median + 1)
        coinbase = create_coinbase(height + 1)
        coinbase.vin[0].scriptSig = (ser_string(serialize_script_num(height + 1)) +
                                     MERGED_MINING_HEADER + bytes.fromhex(child_hash) +
                                     struct.pack("<I", 1) + struct.pack("<I", 0))
        coinbase.rehash()
        parent = create_block(int(child_hash, 16), coinbase, child_time + 1)
        parent.nVersion = 4
        parent.nBits = int(aux['bits'], 16)
        parent.solve()
        auxpow = (coinbase.serialize_without_witness() + ser_uint256(parent.sha256) +
                  b"\x00" + struct.pack("<i", 0) + b"\x00" + struct.pack("<i", 0) +
                  CBlockHeader.serialize(parent))
        return child_hash, auxpow.hex(), parent

    def run_test(self):
        armed, plain = self.nodes
        t = int(time.time())
        for node in self.nodes:
            node.setmocktime(t)

        # 0. The startup line names the rule this binary enforces.
        assert "Chain id rule: 0x5351 required from height %d" % HEIGHT in self.debug_log(0)
        assert "Chain id rule: none" in self.debug_log(1)

        # 1. Below the height the armed node accepts the peer's blocks without
        #    the id: what every node does today.
        plain.generate(HEIGHT - 6)
        self.sync_all()
        assert_equal(armed.getblockcount(), HEIGHT - 6)
        assert_equal(armed.getblock(armed.getbestblockhash())['version'], 4)

        # 2. The pair below the height: the merge-mined child at HEIGHT - 5 and
        #    its parent at HEIGHT - 4 both connect, on the armed node and on
        #    the peer.
        child_hash, auxpow, parent = self.build_pair(armed, t)
        assert_equal(armed.getauxblock(child_hash, auxpow), True)
        assert_equal(armed.getblockcount(), HEIGHT - 5)
        assert_equal(armed.submitblock(parent.serialize().hex()), None)
        assert_equal(armed.getblockcount(), HEIGHT - 4)
        assert_equal(armed.getbestblockhash(), parent.hash)
        assert_equal(armed.getblock(parent.hash)['previousblockhash'], child_hash)
        assert_equal(armed.getblock(parent.hash)['version'], 4)
        self.sync_all()
        assert_equal(plain.getbestblockhash(), parent.hash)

        # 3. The pair at the height: the child at HEIGHT - 1 carries the id and
        #    connects; its parent at HEIGHT carries none and is refused by the
        #    armed node, which stays on the child.
        plain.generate(2)
        self.sync_all()
        assert_equal(armed.getblockcount(), HEIGHT - 2)
        child_hash, auxpow, parent = self.build_pair(armed, t)
        assert_equal(armed.getauxblock(child_hash, auxpow), True)
        assert_equal(armed.getblockcount(), HEIGHT - 1)
        assert_equal(armed.getbestblockhash(), child_hash)
        self.sync_all()
        assert_equal(armed.submitblock(parent.serialize().hex()), "bad-chain-id")
        assert_equal(armed.getblockcount(), HEIGHT - 1)
        assert_equal(armed.getbestblockhash(), child_hash)
        assert ("AcceptBlockHeader: Consensus::ContextualCheckBlockHeader: %s, bad-chain-id" % parent.hash) in self.debug_log(0)

        # 4. The peer, with no rule, accepts the same parent and extends its
        #    chain with it. The armed node refuses the announced header, drops
        #    the peer, and does not follow.
        assert_equal(plain.submitblock(parent.serialize().hex()), None)
        assert_equal(plain.getblockcount(), HEIGHT)
        assert_equal(plain.getbestblockhash(), parent.hash)
        for _ in range(120):
            if armed.getpeerinfo() == []:
                break
            time.sleep(0.5)
        assert_equal(armed.getpeerinfo(), [])
        assert "BAN THRESHOLD EXCEEDED" in self.debug_log(0)
        assert_equal(armed.getblockcount(), HEIGHT - 1)
        assert_equal(armed.getbestblockhash(), child_hash)

        # 5. The armed node's own blocks at and above the height carry the id
        #    and connect.
        armed.generate(2)
        assert_equal(armed.getblockcount(), HEIGHT + 1)
        for h in (HEIGHT, HEIGHT + 1):
            assert_equal(armed.getblock(armed.getblockhash(h))['version'], STAMPED_VERSION)

        # 6. The regtest option is bounded to a block height: the largest value
        #    starts a node and is formatted on its startup line; a negative one
        #    refuses to start. That refusal is printed on the daemon's stderr
        #    before its log opens, so the daemon's stderr is captured to a file
        #    for the check (the test runner fails any test whose own stderr is
        #    not empty). Whatever happens in this step, no process of the third
        #    node outlives it: the outer clause pops its entry from the process
        #    map (the framework's teardown stops nodes 0 and 1 only and then
        #    asserts the map is empty) and ends a process still alive.
        initialize_datadir(self.options.tmpdir, 2)
        stderr_path = os.path.join(self.options.tmpdir, "node2-stderr.txt")
        started_out_of_range = False
        try:
            node2 = start_node(2, self.options.tmpdir, ["-chainidrequiredheight=2147483647"])
            stop_node(node2, 2)
            assert "Chain id rule: 0x5351 required from height 2147483647" in self.debug_log(2)
            saved_stderr = os.dup(2)
            try:
                with open(stderr_path, "w") as captured:
                    os.dup2(captured.fileno(), 2)
                    try:
                        start_node(2, self.options.tmpdir, ["-chainidrequiredheight=-1"])
                        started_out_of_range = True
                    except Exception as e:
                        assert "exited with status 1 during initialization" in str(e), str(e)
            finally:
                os.dup2(saved_stderr, 2)
                os.close(saved_stderr)
        finally:
            proc = soqucoind_processes.pop(2, None)
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        assert not started_out_of_range, "a node started with a negative -chainidrequiredheight"
        with open(stderr_path, encoding="utf-8") as f:
            assert "Invalid -chainidrequiredheight" in f.read()


if __name__ == '__main__':
    ChainIdRequiredHeightTest().main()
