<!-- source: https://www.hpc.dtu.dk/?page_id=2501 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Accessing the LSF 10 Cluster

## Overview

Two primary methods for accessing DTU's LSF 10 cluster infrastructure:

1. **Command-line SSH access** — requires a terminal emulator and SSH client; minimal bandwidth
2. **Graphical interface via ThinLinc** — provides a GUI; requires more bandwidth

The system runs Scientific Linux 7.9.

## SSH Access Instructions

```
ssh userid@login1.gbar.dtu.dk
ssh userid@login1.hpc.dtu.dk
ssh userid@login2.gbar.dtu.dk
ssh userid@login2.hpc.dtu.dk
```

Replace `userid` with your DTU username.

> **Please DO NOT run any application** on login nodes.

For interactive work, type `linuxsh` to access a shared interactive node.

## ThinLinc Access

**From DTU or VPN:**

- Server: `thinlinc.gbar.dtu.dk`
- Username: DTU userid
- Password: DTU password

**From remote locations (without VPN):** use SSH key authentication with public key security
enabled in ThinLinc options. See [ssh-keys.md](ssh-keys.md).

## Important Notes

- Both methods provide secure authentication
- SSH key authentication is required for remote access without VPN
- Application nodes reached through ThinLinc can submit jobs to LSF-managed clusters
- SSH fingerprints are available for verification on first login (<https://www.hpc.dtu.dk/fp.txt>)

---

## This machine's configuration

Already set up in `~/.ssh/config` — `ssh dtu` works from anywhere, no VPN:

```
Host dtu
    HostName login1.gbar.dtu.dk
    User s234842
    IdentityFile ~/.ssh/gbar
    IdentitiesOnly yes
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 8h
```

`ControlPersist 8h` means one authentication covers eight hours of subsequent commands.
`tournament/hpc.py` relies on this: it checks `ssh -O check dtu` and refuses to run rather than
hanging on a passphrase prompt.

**Gotcha:** if `DISPLAY` is set, `ssh` may try to launch a GUI `ssh-askpass` helper instead of
prompting in the terminal, silently failing three times. Prefix with `SSH_ASKPASS_REQUIRE=never`:

```sh
SSH_ASKPASS_REQUIRE=never ssh dtu true    # opens the 8h master
ssh -O check dtu                          # verify it is alive
```
