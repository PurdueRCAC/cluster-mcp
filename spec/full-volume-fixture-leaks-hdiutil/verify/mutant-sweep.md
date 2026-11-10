# Mutant sweep — full-volume-fixture-leaks-hdiutil

The sweep [`mutants.py`](mutants.py) plants each case into a fresh copy of `tests/`, `bin/` and the
top-level files, runs its named rows there in the handshake era, and counts the case killed only
when every named row fails with its `why` (PLAN §6). 40 cases: 26 decisions the fixture makes
(PLAN §6's first table, its `figures` case planted as `figures-bound` and `figures-wait`) and 14
carve-outs it must not have (the second table, the additive cases). **40 of 40 killed.**

Runs (build host, macOS 27, `UV_PYTHON=3.14`, the code of P3's commit):

- **Mode a**, 19 cases: baseline 15 of 15 rows passed unchanged; 19 of 19 killed in **4.3 min**
  (load average 9 at the start). An earlier run of mode a showed `stderr-dropped` not killed: its
  edit also dropped the `: ` after the status, so the row failed on the status text first and never
  reached the `why`. The case's edit was narrowed to the stderr tail; the row was red both times.
- **Mode b**, 21 cases: baseline 17 of 17 rows passed unchanged; 21 of 21 killed in **1.6 min**
  (load average 4 to 10).

After each run no stand-in process and no disk image was left on the host.

| Case | Kind | Mode | Rows | Why | Verdict | Time |
|---|---|---|---|---|---|---|
| `stop-term` | decision | a | `create-hangs`, `detach-hangs`, `test_the_disk_image_figures` | SIGKILL; still running after the fixture | killed | 15.0 s |
| `stop-step-only` | decision | a | `create-hangs`, `create-hangs-with-device`, `attach-hangs`, `attach-hangs-with-device`, `detach-hangs`, `cleanup-detach-hangs` | still running after the fixture | killed | 47.7 s |
| `wait-dropped` | decision | b | `test_a_stopped_step_still_running_is_named` | does not say what is still running | killed | 4.1 s |
| `wait-x10` | decision | b | `test_a_stopped_step_still_running_is_named` | the run took | killed | 8.4 s |
| `survivors-unnamed` | decision | b | `test_a_stopped_step_still_running_is_named` | does not say what is still running | killed | 3.6 s |
| `bound-constant` | decision | a | `create-hangs` | past its limit | killed | 122.0 s |
| `bound-misnamed` | decision | a | `create-hangs`, `detach-hangs` | ran past its bound of 1 s | killed | 4.3 s |
| `status-dropped` | decision | a | `create-fails`, `attach-fails`, `detach-fails`, `info-fails-in-cleanup` | exited with status 1 | killed | 3.1 s |
| `stderr-dropped` | decision | a | `create-fails`, `attach-fails`, `detach-fails` | failed - stand-in failure | killed | 2.7 s |
| `cleanup-attach-only` | decision | a | `create-hangs-with-device`, `create-fails-with-device` | of its own devices left attached | killed | 3.2 s |
| `match-by-string` | decision | a | `create-hangs-with-device`, `create-fails-with-device`, `attach-hangs-with-device`, `attach-fails-with-device`, `cleanup-detach-hangs` | of its own devices left attached; the image is gone | killed | 6.3 s |
| `slice-not-disk` | decision | a | `create-hangs-with-device`, `create-fails-with-device`, `attach-hangs-with-device`, `attach-fails-with-device` | of its own devices left attached | killed | 5.3 s |
| `unlink-first` | decision | a | `cleanup-detach-hangs` | the image is gone | killed | 4.1 s |
| `unlink-strict` | decision | a | `create-hangs`, `create-fails` | raised no HostFailure | killed | 3.3 s |
| `info-ignored` | decision | b | `info-fails-in-cleanup`, `info-answers-garbled` | the image is gone | killed | 2.9 s |
| `left-unnamed` | decision | b | `detach-hangs`, `detach-fails` | the volume stays attached at | killed | 4.5 s |
| `chain-dropped` | decision | b | `body-and-detach-fail` | not caused by the body | killed | 2.1 s |
| `order-swapped` | decision | b | `cleanup-detach-hangs` | in order | killed | 4.2 s |
| `unlink-dropped` | decision | b | `every-step-succeeds` | the image was left | killed | 2.1 s |
| `detach-image` | decision | b | `every-step-succeeds` | raised although every step succeeded | killed | 3.3 s |
| `figures-bound` | decision | b | `test_the_disk_image_figures` | 120 | killed | 1.8 s |
| `figures-wait` | decision | b | `test_the_disk_image_figures` | 50 == 5 | killed | 1.8 s |
| `raise-dropped` | decision | b | `body-fails` | the body's own failure was not raised unchanged | killed | 2.1 s |
| `unlink-dropped-on-body` | decision | b | `body-fails` | the image was left | killed | 2.0 s |
| `match-basename` | decision | b | `create-hangs`, `attach-fails`, `attach-hangs-with-device` | it did not make was detached | killed | 4.8 s |
| `listing-unread` | decision | b | `info-answers-garbled` | raised no HostFailure | killed | 2.1 s |
| `no-stop-detach` | additive | a | `detach-hangs`, `cleanup-detach-hangs` | still running after the fixture | killed | 5.8 s |
| `no-stop-cleanup` | additive | a | `cleanup-detach-hangs` | still running after the fixture | killed | 4.0 s |
| `no-stop-info` | additive | a | `info-fails-in-cleanup` | still running after the fixture | killed | 2.1 s |
| `no-stop-on-fail` | additive | a | `create-fails`, `attach-fails`, `detach-fails`, `info-fails-in-cleanup` | still running after the fixture | killed | 3.1 s |
| `no-stop-on-attach-fail` | additive | a | `attach-fails`, `attach-fails-with-device` | still running after the fixture | killed | 2.5 s |
| `no-stop-on-detach-fail` | additive | a | `detach-fails`, `body-and-detach-fail`, `cleanup-detach-fails` | still running after the fixture | killed | 2.8 s |
| `no-cleanup-on-hang` | additive | a | `create-hangs-with-device`, `attach-hangs-with-device` | of its own devices left attached | killed | 4.1 s |
| `no-unlink-without-device` | additive | a | `attach-hangs`, `attach-fails` | the image was left | killed | 3.3 s |
| `retry-detach` | additive | b | `detach-hangs`, `detach-fails`, `body-and-detach-fail` | of its own devices left attached, not 1 | killed | 4.0 s |
| `retry-cleanup-detach` | additive | b | `cleanup-detach-hangs`, `cleanup-detach-fails` | of its own devices left attached, not 1 | killed | 4.6 s |
| `no-left-on-body` | additive | b | `body-and-detach-fail` | the volume stays attached at | killed | 2.0 s |
| `match-any` | additive | b | `create-hangs`, `attach-hangs`, `attach-fails-with-device` | it did not make was detached | killed | 4.8 s |
| `term-then-kill` | additive | b | `create-hangs`, `detach-hangs` | sent TERM | killed | 8.3 s |
| `survivor-always` | additive | b | `create-fails`, `create-hangs`, `detach-fails` | names a survivor where none was left | killed | 3.7 s |
