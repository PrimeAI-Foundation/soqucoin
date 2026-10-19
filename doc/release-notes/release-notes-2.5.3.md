Soqucoin Core 2.5.3
===================

Soqucoin Core 2.5.3 is a maintenance release for every network. It carries one
change to the node: stricter validation of the compact block messages a node
receives from its peers, applied when a message is read and before the node
acts on it. Messages that a correctly operating node produces pass the new
checks, so a 2.5.3 node connects to and relays with 2.5.1 and 2.5.2 nodes as
before.

Every node operator should upgrade. Consensus rules, the peer-to-peer protocol
version, the RPC interface, the wallet and every on-disk format are unchanged,
so the upgrade is a binary replacement: no reindex, no migration.

Upgrading
---------

Stop the running daemon, replace `soqucoind` and `soqucoin-cli`, start it. The
data directory carries over on every network. The upgrade neither reads nor
writes a wallet file, whether the node loads one or runs with `disablewallet=1`;
the usual practice of keeping a current backup of any wallet file applies as
before. A node that last ran 2.5.0 or older on mainnet still needs a fresh
mainnet data directory, as `doc/node-operators.md` describes.

Notable changes
---------------

### Compact block message validation

Compact block messages received from peers, and the follow-up requests for the
transactions a compact block leaves out, are validated more strictly at the
point where they are read from the network. A message that fails the validation
is rejected before the node does any further work on it. Unit tests cover the
new checks and confirm that well-formed messages are still accepted.

### Build and packaging

- The version is 2.5.3 in `configure.ac`, `src/clientversion.h` and
  `doc/Doxyfile`.
- The release archives are built as the 2.5.2 archives were: the Linux x64 and
  arm64 archives through depends with a static runtime and a container smoke
  test, the macOS archives on their own architecture without the wallet, the
  Windows archive through depends. The release page shows this file as its
  notes.

### Documentation

- `INSTALL.md`, `README.md` and `doc/node-operators.md` name 2.5.3 as the
  current release.
- `SECURITY.md` and `.github/SECURITY.md` state one way to report a
  vulnerability, GitHub private vulnerability reporting, with what to expect
  and the bounty.

Known limitations
-----------------

- Verification-cost budgeting for post-quantum signatures is defined but not
  enforced. The block weight limit and the sigop budget bound the verification
  work a block can demand; peer limits and ban thresholds cover the rest. A fix
  is planned for a later release.
- The manual pages under `doc/man/` still describe an earlier release.

Credits
-------

Thanks to everyone who contributed to this release.
