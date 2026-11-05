---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A live link that delivers nothing for one connect bound reads as dead

## Problem

`ssh-half-open-link` notices a silent SSH link by what arrives from the peer. Any message counts, a
probe's reply included, so nothing merely quiet is cut while the peer answers
(`spec/ssh-half-open-link/PLAN.md` §2.1). The verdict is split:
- a probe sent when a call starts is judged after one connect bound (15 s by default), to leave the
  reconnect room;
- a background probe, sent after one bound of quiet, is judged after two bounds less a second (29 s).

The floor is a live link on which nothing arrives for that long. At the default bound:
- **A quiet command** (`sbatch --wait`, a long compile) is reported lost when the peer answers
  nothing for 29 s after a probe. That is an outage of more than about 25 s that begins as the probe
  is sent (TCP's retransmission backoff resends it at about 0.2, 0.6, 1.4, 3, 6.2, 12.6 and 25.4 s,
  then 51 s), or more than about 40 s that begins at the last message heard. A login node's SSH
  daemon stalled for 29 s reads the same way.
- **A transfer** is cut when no reply arrives for 44 s. An SFTP upload is heard once per write
  request (32 KiB, Paramiko's `MAX_REQUEST_SIZE`), so an uplink slower than about 0.75 KB/s is cut
  and reported as possibly partly made.
- **While another call starts on the connection**, its own verdict at one bound applies to every
  call: a 15 s answer, an upload above about 2.2 KB/s.

All three scale with the bound: a longer ssh_config `ConnectTimeout` lowers the floor. Measured
in `spec/ssh-half-open-link/research/01-paramiko-silent-link.md` §5; the split and its figures are
PLAN §4.2.

**Pre-existing:** no. It is the recorded limit of the detection `ssh-half-open-link` adds; before
it, such a link was never cut, and a dead one was never noticed.

## Why it was deferred

The GOAL bounds detection inside the reconnect bound (3 × the connect bound), so any detector has
a longest gap it can wait out. The split verdict already gives the background probe the longest
wait the in-flight bound allows (two bounds less a second); only a call's own probe is judged at
one bound, so that the reconnect keeps two. No application-level signal sees TCP's acknowledgements, which
would tell a slow uplink from a dead one. The plan recorded it as its R4 deviation (PLAN §3,
Deviation 3) for the PLAN/TECH sign-off.

## Outcome / vision

A slow but live link is never cut, at any rate a user would call working, while a dead one is still
noticed within the bound.

## Sketch of the acceptance criteria

- **R1** — WHILE a transfer's link delivers at least <rate>, the transfer SHALL run to its end,
  however long its requests take to be answered.

## Notes

- Candidate directions: smaller SFTP write requests in `write`'s staging (more replies per byte);
  reading the socket's unacknowledged bytes where the platform reports them (`TCP_INFO`, Linux
  only); a longer verdict only while an upload is in flight.
- Related: `spec/ssh-half-open-link/`, `issues/ssh-half-open-link.md`.
- Found by: `ssh-half-open-link` planning research, 2026-11-05.
