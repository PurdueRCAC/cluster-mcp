---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A live link that delivers nothing for one connect bound reads as dead

## Problem

`ssh-half-open-link` notices a silent SSH link by what arrives from the peer: it sends a probe when
nothing has been heard for one connect bound (15 s by default), and calls the link dead when that
probe has been out for one more connect bound with nothing at all heard since
(`spec/ssh-half-open-link/PLAN.md` §2.1). Any message counts, so a quiet command or a slow download
is never cut: a probe's reply proves the link live, and data does too.

The floor is a live link on which *nothing* arrives for a whole connect bound. An SFTP upload hears
once per write request (32 KiB, Paramiko's `MAX_REQUEST_SIZE`), and a probe queues in the client's
send buffer behind the upload's data, so an uplink slower than about 2.2 KB/s (32 KiB per 15 s)
can go a whole bound with nothing heard, and the transfer is cut and reported as possibly partly made
(measured by `spec/ssh-half-open-link/research/01-paramiko-silent-link.md` §5). Commands are bound
by it too. A quiet command (`sbatch --wait`, a long compile) is reported lost when the peer cannot
answer a probe within the bound: a login node's SSH daemon stalled for 15 s, or an outage of about
13 s, which TCP would ride out, but whose retransmission backoff resends the probe only after the
bound has passed (the plan's adversarial review, finding 8). It scales with
the bound: a longer ssh_config `ConnectTimeout` lowers the floor.

**Pre-existing:** no. It is the recorded limit of the detection `ssh-half-open-link` adds; before
it, such a link was never cut, and a dead one was never noticed.

## Why it was deferred

The GOAL bounds detection inside the reconnect bound (3 × the connect bound), so any detector has
a longest gap it can wait out. Waiting two bounds instead of one halves the floor but leaves the
reconnect one bound instead of two. No application-level signal sees TCP's acknowledgements, which
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
