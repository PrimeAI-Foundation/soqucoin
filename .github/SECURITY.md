# Security Policy

## Supported Versions

| Version | Supported          | Notes                |
| ------- | ------------------ | -------------------- |
| 2.5.x   | :white_check_mark: | Current release line |
| < 2.5.0 | :x:                | Not supported        |

## Reporting a Vulnerability

Please do not open a public issue for a security defect. Report it through GitHub private vulnerability
reporting on this repository:

https://github.com/soqucoin/soqucoin/security/advisories/new

A report filed there is visible only to you and the repository's maintainers, and a fix can be prepared in a
private fork. We do not use PGP for reports. If you cannot use GitHub, email security@soqu.org.

Please include the commit or release you tested, the network (mainnet, stagenet or regtest), the steps to
reproduce and your assessment of the impact. Test on regtest or a private network, never against mainnet,
stagenet or public nodes.

## What to Expect

- GitHub confirms receipt when you submit. We triage reports by impact and reply on the advisory when we start
  reviewing yours.
- Every claim is reproduced from our own build before we confirm it. We do not run code or binaries supplied
  with a report.
- The fix is developed privately. Public disclosure follows once the fix is released, or on a timeline agreed
  with you.
- With your permission, you are credited in the release notes.

## Bounty

A critical consensus bug (a remote chain split, inflation of the supply, or a verifiable preimage) confirmed
under this policy is eligible for an award of at least 5,000 SOQ, paid by Soqucoin Labs Inc. Awards are
decided once a report is confirmed, and the first valid report of a defect receives it. Payment is subject to
the checks the law requires of us, such as sanctions screening and tax forms.

Other reports in scope are welcome and credited, without an award.

## Scope

In scope:
- Consensus: chain splits, inflation, double spends
- Post-quantum cryptography: ML-DSA-44 signatures, PAT batch attestation
- Peer-to-peer networking: denial of service against a node, eclipse attacks
- Wallet and key management: key leakage, weak derivation
- RPC authentication bypass

Out of scope:
- Third-party dependencies (report upstream)
- Social engineering and physical attacks
- Unsupported versions
- Testing against mainnet, stagenet or public nodes
