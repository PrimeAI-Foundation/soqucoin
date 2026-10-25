#!/usr/bin/env python3
# Copyright (c) 2026 The Soqucoin developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

#
# The release mark (CPureBlockHeader::VERSION_RELEASE_MARK, bit 15 of the
# block version, bead zq1xc): the block template sets it so the blocks built
# by nodes of this release and later can be counted on the chain; no check
# reads it. The unit test (block_version_mark_tests) drives the header
# predicates and the miner in process; this covers what it cannot: a node on
# an earlier release accepting marked blocks over the network (node 0 runs the
# binary named by SOQUCOIND_PREVIOUS when the variable is set, otherwise the
# binary under test with the version pinned to the earlier shape), the mark
# through getblocktemplate and through the merge-mining path, the earlier
# node's own unmarked blocks accepted by the marked node, the regtest
# -blockversion override, and the count of marked blocks over the window,
# which is how the share of blocks from upgraded nodes is read.
#

import os
import subprocess
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (assert_equal, connect_nodes_bi, start_node,
                                 start_nodes, stop_node, sync_blocks)
from test_framework import scrypt_auxpow as auxpow

CHAIN_ID = 0x5351
MARK = 1 << 15
AUXPOW_FLAG = 1 << 8
DIRECT = (CHAIN_ID << 16) | 4          # 0x53510004: base version 4, chain id 0x5351
MERGED = DIRECT | AUXPOW_FLAG          # 0x53510104: the same, merge-mined
DIRECT_MARKED = DIRECT | MARK          # 0x53518004
MERGED_MARKED = MERGED | MARK          # 0x53518104
# A parent chain id for the merge-mining helper, distinct from ours.
PARENT_CHAIN_ID = "98"
# A regtest witness v1 address for the coinbase outputs; nothing spends them,
# so neither node needs a wallet.
MINER_ADDRESS = "sq1pn9ejf5l4ge2j9hu5tlwrhvazsq9x5w64tw2dlx83vjs2lnhtgmrqxs2w7h"


def version_line(binary):
    out = subprocess.check_output([binary, "--version"]).decode("utf-8", "replace")
    return out.splitlines()[0]


class BlockVersionMarkTest(BitcoinTestFramework):
    def __init__(self):
        super().__init__()
        self.setup_clean_chain = True
        self.num_nodes = 2

    def setup_network(self, split=False):
        self.is_network_split = False
        self.previous = os.getenv("SOQUCOIND_PREVIOUS")
        # Node 0 stands for the earlier release. On the earlier binary its
        # template stamps the unmarked shape by itself; on the binary under
        # test the regtest override pins the same shape.
        node0_args = ["-debug"] if self.previous else ["-debug", "-blockversion=%d" % DIRECT]
        self.nodes = start_nodes(self.num_nodes, self.options.tmpdir,
                                 [node0_args, ["-debug"]],
                                 binary=[self.previous, None])
        connect_nodes_bi(self.nodes, 0, 1)

    def restart_marked_node(self, extra_args):
        stop_node(self.nodes[1], 1)
        self.nodes[1] = start_node(1, self.options.tmpdir, ["-debug"] + extra_args)
        connect_nodes_bi(self.nodes, 0, 1)
        return self.nodes[1]

    def run_test(self):
        earlier, marked = self.nodes
        under_test = os.getenv("SOQUCOIND", "soqucoind")
        if self.previous:
            # Two binaries, and they are not the same build.
            previous_line = version_line(self.previous)
            under_test_line = version_line(under_test)
            print("node 0: %s (%s)" % (previous_line, self.previous))
            print("node 1: %s (%s)" % (under_test_line, under_test))
            assert previous_line != under_test_line, "SOQUCOIND_PREVIOUS names the binary under test"
        else:
            print("one binary: node 0 pins the earlier shape with -blockversion")
        address = MINER_ADDRESS

        # 1. The marked node's direct blocks carry the mark, and the earlier
        #    node accepts them.
        marked.generatetoaddress(5, address)
        sync_blocks(self.nodes)
        assert_equal(earlier.getblockcount(), 5)
        assert_equal(earlier.getbestblockhash(), marked.getbestblockhash())
        for height in range(1, 6):
            block = earlier.getblock(earlier.getblockhash(height))
            assert_equal(block['version'], DIRECT_MARKED)
            assert_equal(block['versionHex'], "53518004")

        # 2. The template carries the mark.
        assert_equal(marked.getblocktemplate()['version'], DIRECT_MARKED)

        # 3. The earlier node's own blocks carry no mark, and the marked node
        #    accepts them. This also carries the chain past the regtest AuxPoW
        #    start for step 4.
        earlier.generatetoaddress(20, address)
        sync_blocks(self.nodes)
        assert_equal(marked.getblockcount(), 25)
        for height in range(6, 26):
            assert_equal(marked.getblock(marked.getblockhash(height))['version'], DIRECT)

        # 4. The merge-mining path: the marked node's child block carries the
        #    merge-mining flag and the mark, and the earlier node accepts it.
        aux = marked.createauxblock(address)
        target = auxpow.reverseHex(aux['target'])
        proof = auxpow.computeAuxpowWithChainId(aux['hash'], target, PARENT_CHAIN_ID, True)
        assert_equal(marked.submitauxblock(aux['hash'], proof), True)
        assert_equal(marked.getbestblockhash(), aux['hash'])
        assert_equal(marked.getblock(aux['hash'])['version'], MERGED_MARKED)
        sync_blocks(self.nodes)
        assert_equal(earlier.getbestblockhash(), aux['hash'])
        assert_equal(earlier.getblock(aux['hash'])['versionHex'], "53518104")

        # 5. The regtest override replaces the whole version, mark included.
        marked = self.restart_marked_node(["-blockversion=4"])
        marked.generatetoaddress(1, address)
        sync_blocks(self.nodes)
        assert_equal(marked.getblock(marked.getbestblockhash())['version'], 4)
        assert_equal(earlier.getbestblockhash(), marked.getbestblockhash())
        marked = self.restart_marked_node([])
        marked.generatetoaddress(1, address)
        sync_blocks(self.nodes)
        assert_equal(marked.getblock(marked.getbestblockhash())['version'], DIRECT_MARKED)
        assert_equal(earlier.getbestblockhash(), marked.getbestblockhash())

        # 6. The count over the window: the marked blocks are exactly the ones
        #    the marked node built without the override.
        tip = earlier.getblockcount()
        assert_equal(tip, 28)
        marked_heights = [h for h in range(1, tip + 1)
                          if earlier.getblock(earlier.getblockhash(h))['version'] & MARK]
        assert_equal(marked_heights, [1, 2, 3, 4, 5, 26, 28])
        print("marked blocks: %d of %d" % (len(marked_heights), tip))


if __name__ == '__main__':
    BlockVersionMarkTest().main()
