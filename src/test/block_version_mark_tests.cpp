// Copyright (c) 2026 Soqucoin Labs Inc.
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

/**
 * The release mark (CPureBlockHeader::VERSION_RELEASE_MARK, bit 15 of the
 * block version, bead zq1xc). The block template sets it on every network, so
 * the blocks built by nodes of this release and later can be counted on the
 * chain. The version layout (CPureBlockHeader) keeps the base version in the
 * low byte, the merge-mining flag at bit 8 and the chain id from bit 16, so no
 * header predicate reads bit 15 and no deployment signals on it. This suite
 * pins that: the predicates return the same values with and without the mark
 * on every shape the template produces and on every non-legacy shape; the
 * setters around the mark keep it; the template carries exactly the mark, base
 * version 4 and the chain id; the merge-mining flag joins it undisturbed; a
 * marked header passes the version rules of ContextualCheckBlockHeader, below
 * and at the chain id rule's height; and the mark does not rescue a header the
 * chain id rule refuses.
 */

#include "chain.h"
#include "chainparams.h"
#include "consensus/merkle.h"
#include "consensus/params.h"
#include "consensus/validation.h"
#include "miner.h"
#include "pow.h"
#include "primitives/block.h"
#include "primitives/pureheader.h"
#include "script/script.h"
#include "timedata.h"
#include "util.h"
#include "validation.h"
#include "versionbits.h"

#include "test/test_bitcoin.h"

#include <boost/test/unit_test.hpp>

#include <memory>
#include <string>
#include <vector>

BOOST_FIXTURE_TEST_SUITE(block_version_mark_tests, TestingSetup)

namespace {

const int32_t kMark = CPureBlockHeader::VERSION_RELEASE_MARK;
const int32_t kChainId = 0x5351;
const int32_t kDirect = (kChainId << 16) | 4;                       // 0x53510004, what the miner stamps
const int32_t kMerged = kDirect | CPureBlockHeader::VERSION_AUXPOW; // 0x53510104, merge-mined

struct RegtestChainIdRule {
    explicit RegtestChainIdRule(int32_t nHeight) { UpdateRegtestChainIdRequiredHeight(nHeight); }
    ~RegtestChainIdRule() { UpdateRegtestChainIdRequiredHeight(0); }
};

// Builds the next block through the production miner, solves it and connects it.
void MineRegtestBlock(const CChainParams& cp, const CScript& spk)
{
    const int nHeight = chainActive.Height() + 1;
    std::unique_ptr<CBlockTemplate> tmpl = BlockAssembler(cp).CreateNewBlock(spk, true);
    BOOST_REQUIRE(tmpl != nullptr);
    CBlock block = tmpl->block;
    block.hashMerkleRoot = BlockMerkleRoot(block);
    while (!CheckProofOfWork(block.GetPoWHash(), block.nBits, cp.GetConsensus(nHeight))) {
        ++block.nNonce;
    }
    std::shared_ptr<const CBlock> shared = std::make_shared<const CBlock>(block);
    BOOST_REQUIRE(ProcessNewBlock(cp, shared, true, nullptr));
    BOOST_REQUIRE_EQUAL(chainActive.Height(), nHeight);
}

// Judges a header of the given version at the next height through the
// production check. The miner's template supplies everything else a valid
// header needs, so a refusal is the version's alone.
bool Judge(const CChainParams& cp, const CScript& spk, int32_t nVersion, std::string& reason)
{
    std::unique_ptr<CBlockTemplate> tmpl = BlockAssembler(cp).CreateNewBlock(spk, true);
    BOOST_REQUIRE(tmpl != nullptr);
    CBlockHeader hdr = tmpl->block.GetBlockHeader();
    hdr.nVersion = nVersion;
    CValidationState state;
    const bool ok = ContextualCheckBlockHeader(hdr, state, chainActive.Tip(), GetAdjustedTime());
    reason = state.GetRejectReason();
    return ok;
}

} // namespace

BOOST_AUTO_TEST_CASE(the_mark_is_bit_15_and_no_other_field_or_deployment_names_it)
{
    BOOST_CHECK_EQUAL(kMark, 1 << 15);
    BOOST_CHECK_EQUAL(kMark % CPureBlockHeader::VERSION_AUXPOW, 0);    // outside the base version byte
    BOOST_CHECK_EQUAL(kMark & CPureBlockHeader::VERSION_AUXPOW, 0);    // not the merge-mining flag
    BOOST_CHECK(kMark < CPureBlockHeader::VERSION_CHAIN_START);        // below the chain id
    BOOST_CHECK_EQUAL(kMark & VERSIONBITS_TOP_MASK, 0);                // outside the version-bits top bits

    // getblocktemplate writes a deployment's bit into the template version by
    // the deployment's state; no deployment on any network signals on bit 15.
    const std::vector<std::string> networks = {CBaseChainParams::MAIN, CBaseChainParams::TESTNET,
                                               CBaseChainParams::STAGENET, CBaseChainParams::REGTEST};
    for (const std::string& network : networks) {
        const Consensus::Params& consensus = Params(network).GetConsensus(0);
        for (int j = 0; j < (int)Consensus::MAX_VERSION_BITS_DEPLOYMENTS; ++j) {
            BOOST_CHECK_MESSAGE(consensus.vDeployments[j].bit != 15,
                                network + " deployment " + std::to_string(j) + " signals on bit 15");
        }
    }
}

BOOST_AUTO_TEST_CASE(the_predicates_read_past_the_mark)
{
    // Every shape the template produces, and the non-legacy shapes a header
    // can take: with and without the id, with another id, with the sign bit.
    const std::vector<int32_t> shapes = {kDirect, kMerged, 4, 0x00000104, 0x00620004,
                                         (int32_t)0x80000004, 3, 0x53510003};
    for (const int32_t v : shapes) {
        CBlockHeader plain;
        plain.nVersion = v;
        CBlockHeader marked;
        marked.nVersion = v | kMark;
        BOOST_CHECK_EQUAL(marked.GetBaseVersion(), plain.GetBaseVersion());
        BOOST_CHECK_EQUAL(marked.GetChainId(), plain.GetChainId());
        BOOST_CHECK_EQUAL(marked.IsAuxpow(), plain.IsAuxpow());
        BOOST_CHECK_EQUAL(marked.IsLegacy(), plain.IsLegacy());
        BOOST_CHECK(!marked.IsLegacy());
        // The block index carries the same readers.
        const CBlockIndex indexPlain(plain);
        const CBlockIndex indexMarked(marked);
        BOOST_CHECK_EQUAL(indexMarked.GetBaseVersion(), indexPlain.GetBaseVersion());
        BOOST_CHECK_EQUAL(indexMarked.GetChainId(), indexPlain.GetChainId());
        BOOST_CHECK_EQUAL(indexMarked.IsAuxpow(), indexPlain.IsAuxpow());
    }

    // The setters around the mark: SetChainId and SetAuxpowFlag keep it;
    // SetBaseVersion builds the whole value, which is why the template sets
    // the mark after it.
    CBlockHeader hdr;
    hdr.nVersion = kDirect | kMark;
    hdr.SetChainId(0x62);
    BOOST_CHECK_EQUAL(hdr.nVersion, (0x62 << 16) | 4 | kMark);
    hdr.SetChainId(kChainId);
    BOOST_CHECK_EQUAL(hdr.nVersion, kDirect | kMark);
    hdr.SetAuxpowFlag(true);
    BOOST_CHECK_EQUAL(hdr.nVersion, kMerged | kMark);
    hdr.SetAuxpowFlag(false);
    BOOST_CHECK_EQUAL(hdr.nVersion, kDirect | kMark);
    hdr.SetBaseVersion(4, kChainId);
    BOOST_CHECK_EQUAL(hdr.nVersion, kDirect);

    // A legacy block is a whole-value comparison (1, or 2 with chain id 0), so
    // it is no shape the mark can sit on; the template never produces one.
    CBlockHeader legacy;
    legacy.nVersion = 1;
    BOOST_CHECK(legacy.IsLegacy());
    legacy.nVersion = 1 | kMark;
    BOOST_CHECK(!legacy.IsLegacy());
}

BOOST_AUTO_TEST_CASE(the_template_carries_the_mark)
{
    const CChainParams& cp = Params();
    const CScript spk = CScript() << OP_1 << std::vector<unsigned char>(32, 0xB2);
    BOOST_REQUIRE_EQUAL(cp.GetConsensus(0).nAuxpowChainId, kChainId);
    BOOST_REQUIRE(!IsArgSet("-blockversion"));

    std::unique_ptr<CBlockTemplate> tmpl = BlockAssembler(cp).CreateNewBlock(spk, true);
    BOOST_REQUIRE(tmpl != nullptr);
    const CBlock& block = tmpl->block;
    BOOST_CHECK_EQUAL(block.nVersion, kDirect | kMark);
    BOOST_CHECK_EQUAL(block.GetBaseVersion(), VERSIONBITS_LAST_OLD_BLOCK_VERSION);
    BOOST_CHECK_EQUAL(block.GetChainId(), kChainId);
    BOOST_CHECK(!block.IsAuxpow());
    BOOST_CHECK(!block.IsLegacy());

    // The merge-mining path adds the flag to the same template (rpc/auxpow.cpp).
    CBlock merged = block;
    merged.SetAuxpowFlag(true);
    BOOST_CHECK_EQUAL(merged.nVersion, kMerged | kMark);
    BOOST_CHECK_EQUAL(merged.GetBaseVersion(), VERSIONBITS_LAST_OLD_BLOCK_VERSION);
    BOOST_CHECK_EQUAL(merged.GetChainId(), kChainId);

    // The mined block connects, and the index and the stored header carry the mark.
    MineRegtestBlock(cp, spk);
    BOOST_CHECK_EQUAL(chainActive.Tip()->nVersion, kDirect | kMark);
    BOOST_CHECK_EQUAL(chainActive.Tip()->GetBlockHeader(cp.GetConsensus(chainActive.Height())).nVersion, kDirect | kMark);
}

BOOST_AUTO_TEST_CASE(the_header_rules_read_past_the_mark)
{
    const CChainParams& cp = Params();
    const CScript spk = CScript() << OP_1 << std::vector<unsigned char>(32, 0xC3);
    BOOST_REQUIRE_EQUAL(cp.GetConsensus(0).nChainIdRequiredHeight, 0);
    std::string reason;

    // The direct shape at height 1, with and without the mark.
    BOOST_CHECK_MESSAGE(Judge(cp, spk, kDirect, reason), "direct header refused: " + reason);
    BOOST_CHECK_MESSAGE(Judge(cp, spk, kDirect | kMark, reason), "marked direct header refused: " + reason);

    // The merge-mined shapes above the regtest AuxPoW start, where
    // early-auxpow-block no longer answers first.
    const int nAuxpowStart = cp.GetConsensus(0).nAuxpowStartHeight;
    while (chainActive.Height() < nAuxpowStart) {
        MineRegtestBlock(cp, spk);
    }
    BOOST_CHECK_MESSAGE(Judge(cp, spk, kMerged, reason), "merge-mined header refused: " + reason);
    BOOST_CHECK_MESSAGE(Judge(cp, spk, kMerged | kMark, reason), "marked merge-mined header refused: " + reason);

    // With the chain id rule armed at the next height the marked shapes pass
    // as the unmarked do, and the mark does not rescue a header without the id.
    const int nArmed = chainActive.Height() + 1;
    RegtestChainIdRule armed(nArmed);
    BOOST_CHECK_MESSAGE(Judge(cp, spk, kDirect | kMark, reason), "marked direct header refused at the height: " + reason);
    BOOST_CHECK_MESSAGE(Judge(cp, spk, kMerged | kMark, reason), "marked merge-mined header refused at the height: " + reason);
    BOOST_CHECK(!Judge(cp, spk, 4 | kMark, reason));
    BOOST_CHECK_EQUAL(reason, "bad-chain-id");
    BOOST_CHECK(!Judge(cp, spk, 0x00000104 | kMark, reason));
    BOOST_CHECK_EQUAL(reason, "bad-chain-id");

    // The production template at the armed height connects.
    MineRegtestBlock(cp, spk);
    BOOST_CHECK_EQUAL(chainActive.Height(), nArmed);
    BOOST_CHECK_EQUAL(chainActive.Tip()->nVersion, kDirect | kMark);
}

BOOST_AUTO_TEST_SUITE_END()
