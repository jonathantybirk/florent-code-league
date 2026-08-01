<!-- source: https://www.hpc.dtu.dk/?page_id=4317 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# SSH and ThinLinc Login Using SSH Keys

## Overview

The DTU network requires SSH key authentication for external access to G-bar and HPC clusters.
Users accessing from campus or via DTU VPN do not need these changes.

## Prerequisites

- A trustworthy machine with updated operating system and software
- Access to the DTU network (campus or VPN) **during initial setup**
- Verify server fingerprints at <https://www.hpc.dtu.dk/fp.txt>

## macOS / Linux / Windows (OpenSSH)

### Step 1: Generate Key Pair

```bash
cd
mkdir -p .ssh
cd .ssh
ssh-keygen -t ed25519 -f gbar
```

When prompted, create a strong passphrase (not your DTU password). This generates `gbar` (private
key — keep secure) and `gbar.pub` (public key).

### Step 2: Copy Public Key to Cluster

**Option A** (if `authorized_keys` exists) — connect via VPN/campus and append:

```bash
cat >> .ssh/authorized_keys
```

Paste the public key content and press Ctrl+D.

**Option B** (new `authorized_keys`):

```bash
ssh s123456@transfer.gbar.dtu.dk mkdir -m 700 -p .ssh
scp gbar.pub s123456@transfer.gbar.dtu.dk:.ssh/authorized_keys
ssh s123456@transfer.gbar.dtu.dk chmod 600 .ssh/authorized_keys
```

### Step 3: Connect

```bash
ssh -i ~/.ssh/gbar s123456@login.hpc.dtu.dk
```

### Step 4: Simplify SSH (Optional)

Create `~/.ssh/config`:

```
Host gbar1
User s123456
IdentityFile ~/.ssh/gbar
Hostname login1.gbar.dtu.dk
```

Then connect with `ssh gbar1`.

### Step 5: ThinLinc Access

- Launch the ThinLinc client
- Options -> Security -> Authentication method: "public key"
- Select the `gbar` file as key

## PuTTY (Windows)

```bash
mkdir -p keys && cd keys
puttygen -t ed25519 -o gbar-putty -O private
puttygen gbar-putty -o gbar-openssh.key -O private-openssh-new
puttygen gbar-putty -o gbar-openssh.pub -O public-openssh
cat gbar-openssh.pub          # copy into the cluster's .ssh/authorized_keys via VPN/campus
putty -i gbar-putty s123456@login2.hpc.dtu.dk
```

Or via GUI: Data -> Username `s123456`; Data -> SSH -> Auth: browse to `gbar-putty`; Hostname
`login.gbar.dtu.dk` (or `login2` variants, or `login.hpc.dtu.dk`).

---

## Why this enables VPN-free access

Once the public key is installed, DTU authenticates with three factors — SSH key, key passphrase,
and DTU password — instead of requiring VPN or DTU WiFi. **The one-time key installation itself
must still be done from campus or the VPN.**

On this machine the key lives at `~/.ssh/gbar` and was installed with `ssh-copy-id` to
`login1.gbar.dtu.dk` — *not* `transfer.gbar.dtu.dk`, which was in SFTP-only mode and rejects the
shell command `ssh-copy-id` needs.

## Contact

support@cc.dtu.dk — DTU Compute, Building 324, Room 280, Technical University of Denmark,
2800 Kgs Lyngby, Denmark
