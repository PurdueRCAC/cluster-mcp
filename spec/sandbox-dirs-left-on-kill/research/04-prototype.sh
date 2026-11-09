#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
# THE PLANNER'S PROTOTYPE, NOT THE BUILD. This is the bin/sandbox.sh the plan's gate was dry-run
# against (PLAN.md section 4 and section 7, the planner's report): kept so the build can read what
# passed every process mode in both shells. The build writes bin/sandbox.sh from PLAN.md section 2,
# and its own comments; nothing runs this copy.
#
#
# Run a command against a throwaway cluster-mcp sandbox so factory verify
# commands and review CLI drives never touch the developer's real home
# directory, config, credentials — or a real HPC cluster.
#
# This is the analogue of a pytest tmp_path fixture for CLI drives. It is the
# only safe way to exercise tools that WRITE (write_file, upload_file,
# run_command), because in `local` execution mode those act on the machine you
# are sitting at, as you.
#
# Three protections, in order of importance:
#
#   1. FAIL CLOSED ON SSH. CLUSTER_MCP_SSH_HOST and its legacy name RCAC_SSH_HOST
#      are both unset, and uv env files are turned off so `uv run` cannot load
#      either back, so a bare `cluster-mcp` or deprecated `rcac-mcp` (whose stdio
#      transport defaults to `ssh` execution) raises
#      "SSH host required: use --ssh-host or set CLUSTER_MCP_SSH_HOST" instead of
#      opening a session on a production cluster. Drive `-e local` explicitly.
#      This is a guard against accidents, not against an explicit --ssh-host.
#   2. HOME IS THE SANDBOX. `~` expansion inside a tool call (`write_file`,
#      `read_file`, `cwd="~/jobs"`) lands in the throwaway dir. XDG config and
#      cache follow it, so per-user state never lands in the real ~/.config.
#   3. AUTH ENV IS BLANK. JWT_SECRET, the OIDC_* variables and the user map, by
#      both names (CLUSTER_MCP_USER_MAP and its legacy RCAC_USER_MAP), are unset,
#      and no uv env file can set them again, so a drive cannot accidentally mint
#      or accept a token signed with the developer's real secret.
#
# Usage:
#   bin/sandbox.sh uv run cluster-mcp --help
#   bin/sandbox.sh sh -c "uv run cluster-mcp -e local --generate-token"
#
# CWD IS THE SANDBOX, NOT THE REPO. That is protection 2 working as intended, but it breaks any
# tool that discovers the project by walking up from the working directory. `uv run` is handled
# (UV_PROJECT below), but pytest is not: run from here it sets rootdir to the throwaway dir, never
# loads pyproject.toml, and so silently loses --strict-markers and every registered marker. For a
# test drive, step back into the repo explicitly — you keep the HOME, auth, and fail-closed-SSH
# guarantees and give up only cwd containment, which pytest's own tmp_path fixture replaces:
#
#   bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run pytest -v -m integration'
#
# The sandbox directory is created under $TMPDIR and removed on every exit path. The script's exit
# trap removes it before the wrapper exits. When the wrapper is killed outright (SIGKILL, which no
# trap sees), a keeper removes it once the wrapper and its command have both ended: a small perl
# process the script starts, detached from it (a process group of its own, parent pid 1, stdio on
# /dev/null, none of the caller's descriptors), that makes the directory, waits on a pipe whose
# other end only this shell holds, then for the command, and exits as it removes the directory.
# Without perl, or with a relative TMPDIR, the script runs as it always did, trap only.
# The script writes nothing of its own to stdout, and its exit status is the command's.
set -eu

# Re-run this script once under perl to start the keeper. The descriptors of its pipes and the perl
# that started it reach the second run in CLUSTER_MCP_SANDBOX_KEEPER, unset before anything else.
keeper="${CLUSTER_MCP_SANDBOX_KEEPER:-}"
unset CLUSTER_MCP_SANDBOX_KEEPER
template="${TMPDIR:-/tmp}/cluster-mcp-sandbox.XXXXXX"
if [ -z "$keeper" ]; then
    perl=
    if command -v perl >/dev/null 2>&1; then perl=perl; elif [ -x /usr/bin/perl ]; then perl=/usr/bin/perl; fi
    case $template in
        /*) ;;
        *) perl= ;;
    esac
    case $template in
        *'
'*) perl= ;;
    esac
    if [ -n "$perl" ]; then
        set -- "$0" "$template" "${PERL5OPT+x$PERL5OPT}" "${PERL5LIB+x$PERL5LIB}" "${PERLLIB+x$PERLLIB}" \
            "${PERLIO+x$PERLIO}" "${PERL_UNICODE+x$PERL_UNICODE}" "${PERL_BADLANG+x$PERL_BADLANG}" \
            "${LC_ALL+x$LC_ALL}" "$@"
        # Perl's own variables would change how it starts: it starts with them neutral and puts the
        # caller's back before it execs anything.
        PERL5OPT= PERL5LIB= PERLLIB= PERLIO= PERL_UNICODE=0 PERL_BADLANG=0 LC_ALL=C
        export PERL5OPT PERL5LIB PERLLIB PERLIO PERL_UNICODE PERL_BADLANG LC_ALL
        CLUSTER_MCP_SANDBOX_KEEPER=start
        export CLUSTER_MCP_SANDBOX_KEEPER
        exec "$perl" -e '
            $^F = 255;
            my ($script, $template, @argv) = @ARGV;
            my @names = qw(PERL5OPT PERL5LIB PERLLIB PERLIO PERL_UNICODE PERL_BADLANG LC_ALL);
            my @saved = splice @argv, 0, scalar @names;
            for my $i (0 .. $#names) {
                if (length $saved[$i]) { $ENV{$names[$i]} = substr $saved[$i], 1 } else { delete $ENV{$names[$i]} }
            }
            my @ends;
            sub plain { close $_ for @ends; delete $ENV{CLUSTER_MCP_SANDBOX_KEEPER}; exec "/bin/sh", $script, @argv; exit 126 }
            pipe(my $up_r, my $up_w) or plain();
            push @ends, $up_r, $up_w;
            pipe(my $down_r, my $down_w) or plain();
            push @ends, $down_r, $down_w;
            plain() if grep { fileno($_) > 9 } $up_r, $up_w, $down_r;
            my $wrapper = $$;
            my $mid = fork;
            plain() unless defined $mid;
            if (!$mid) {
                my $pid = fork;
                exit(defined $pid ? 0 : 1) if !defined $pid || $pid;
                setpgrp(0, 0);
                $SIG{HUP} = $SIG{PIPE} = "IGNORE";
                open STDIN, "<", "/dev/null";
                open STDOUT, ">", "/dev/null";
                close $up_w;
                close $down_r;
                my %mine = (fileno($up_r) => 1, fileno($down_w) => 1);
                for my $fd (3 .. 255) { next if $mine{$fd}; if (open(my $h, "<&=", $fd)) { close $h } }
                %ENV = (PATH => $ENV{PATH} // "/usr/bin:/bin");
                # Out of the run now (no parent link, a group of its own): say so, and make the
                # directory only once the wrapper, still running, answers. A stop that froze the
                # wrapper before it answered may have seen this process; it then makes nothing.
                syswrite $down_w, "ready\n";
                my $go = "";
                while (length($go) < 3) { my $n = sysread($up_r, $go, 3 - length($go), length($go)); exit 0 unless $n }
                exit 0 unless $go eq "go\n";
                open(my $mk, "-|", "mktemp", "-d", $template) or exit 1;
                my $dir = <$mk> // "";
                close $mk;
                chomp $dir;
                exit 1 if $dir eq "" || $dir =~ /\n/ || !-d $dir;
                syswrite $down_w, "$dir\n";
                open STDERR, ">", "/dev/null";
                chdir "/";
                exec { $^X } "cluster-mcp-sandbox-keeper", "-e", q{
                    my ($dir, $up, $down) = @ARGV;
                    my (@pids, $now);
                    if (open(my $in, "<&=", $up)) {
                        while (defined(my $line = <$in>)) {
                            if ($line eq "now\n") { $now = 1 } elsif ($line =~ /^(\d+)$/) { push @pids, $1 }
                        }
                        close $in;
                    }
                    @pids = () if $now;
                    my $alive = sub {
                        my $pid = shift;
                        return $!{EPERM} ? 1 : 0 unless kill 0, $pid;
                        open(my $st, "<", "/proc/$pid/stat") or return 1;
                        my $stat = <$st> // "";
                        return !($stat =~ /.*\)\s(\S)/s && $1 eq "Z");
                    };
                    my $nap = 0.005;
                    while (grep { $alive->($_) } @pids) {
                        select(undef, undef, undef, $nap);
                        $nap = $nap < 0.05 ? $nap * 2 : 0.1;
                    }
                    exec "rm", "-rf", "--", $dir;
                    exit 1;
                }, $dir, fileno($up_r), fileno($down_w);
                exit 1;
            }
            my $reaped = waitpid($mid, 0);
            plain() if $reaped == $mid && $?;
            close $down_w;
            $ENV{CLUSTER_MCP_SANDBOX_KEEPER} = join " ", $wrapper, (map { fileno $_ } $up_r, $up_w, $down_r), $^X;
            exec "/bin/sh", $script, @argv;
            exit 126;
        ' "$@"
    fi
fi

# Capture the repo root before we cd into the sandbox below. `uv run` discovers
# the project by walking up from the working directory, so once cwd is the /tmp
# sandbox it can no longer find pyproject.toml; UV_PROJECT pins discovery back
# to the repo. The root is the checkout this script lives in (bin/..), not the
# caller's cwd, so a drive always exercises this tree, from any directory.
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

# Resolve uv's cache from the REAL home before HOME is replaced, or every drive
# re-downloads the whole dependency tree into a directory we then delete.
UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}"

# HUP, INT and TERM wait for the command, as they always did; the wrapper then exits through EXIT.
trap : HUP INT TERM
# The keeper's pipes: kr and kw are the two ends of the one this shell holds for its life, kd the
# read end of the one the keeper holds until it has removed the directory and exited.
kr= kw= kd= kp=
case $keeper in
    "$$ "[3-9]" "[3-9]" "[3-9]" "?*)
        kp=${keeper#* * * * }
        kr=${keeper#* }
        kw=${kr#* }
        kd=${kw#* }
        kr=${kr%% *}
        kw=${kw%% *}
        kd=${kd%% *}
        sandbox=
        while :; do
            IFS= read -r sandbox <&"$kd" && break
            [ $? -gt 128 ] || exit 1
        done
        [ "$sandbox" = ready ] || exit 1
        printf 'go\n' >&"$kw"
        sandbox=
        while :; do
            IFS= read -r sandbox <&"$kd" && break
            [ $? -gt 128 ] || exit 1
        done
        ;;
    *)
        keeper=
        sandbox="$(mktemp -d "$template")"
        ;;
esac
# On exit, close this shell's pipe and wait for the keeper to exit, its removal done, then remove the
# directory here too. A wrapper leaving while its command may still run (a signal no trap names,
# which some shells let run this trap at once) first tells the keeper not to wait for the command,
# so the directory goes now, as it always did.
running=
trap '
    if [ -n "$keeper" ]; then
        keeper=
        if [ -n "$running" ]; then printf "now\n" >&"$kw" || :; fi
        eval "exec $kr<&- $kw>&-"
        while :; do
            IFS= read -r keeper <&"$kd" && continue
            [ $? -gt 128 ] || break
        done
        keeper=
        eval "exec $kd<&-"
    fi
    rm -rf "$sandbox"
' EXIT

HOME="$sandbox"
XDG_CONFIG_HOME="$sandbox/.config"
XDG_CACHE_HOME="$sandbox/.cache"
XDG_DATA_HOME="$sandbox/.local/share"
UV_PROJECT="$root"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
export HOME XDG_CONFIG_HOME XDG_CACHE_HOME XDG_DATA_HOME UV_PROJECT UV_CACHE_DIR

# Fail closed rather than reaching a real cluster or a real identity provider. uv loads the file
# UV_ENV_FILE names into every `uv run`, after this script has run: an env file carrying a host or a
# user map would set it again past the unset below, so env files are turned off for the whole drive.
unset UV_ENV_FILE
export UV_NO_ENV_FILE=1
unset CLUSTER_MCP_SSH_HOST RCAC_SSH_HOST CLUSTER_MCP_USER_MAP RCAC_USER_MAP JWT_SECRET \
      OIDC_CONFIG_URL OIDC_CLIENT_ID OIDC_CLIENT_SECRET MCP_BASE_URL

# A marker a test or tool can assert on to prove it is running contained, and the way back to the
# repo for a command that must be run from it (see the pytest note in the usage header).
CLUSTER_MCP_SANDBOX="$sandbox"
CLUSTER_MCP_REPO="$root"
export CLUSTER_MCP_SANDBOX CLUSTER_MCP_REPO

# Run inside the sandbox so relative writes (e.g. `sh -c "… > out.txt"`) stay
# contained instead of escaping into the working tree, where a build phase's
# `git add -A` would sweep them into the atomic commit.
cd "$sandbox"
# With a keeper, a command found as a file runs through a perl shim that reports its pid to the
# keeper, closes the pipes and execs it, so it stays this shell's child, in this group; when that
# exec fails, the shim hands the command to /bin/sh, which fails as this shell would have. A builtin,
# a function or a missing command runs in a subshell that reports its pid and closes the pipes first;
# `exec` runs here, as it always did.
direct=
if [ -n "$keeper" ]; then
    found=$(command -v "${1-}" || :)
    case $found in
        */*)
            set -- "$kp" -e '
                my ($me, $found, @fds) = splice @ARGV, 0, 5;
                my @names = qw(PERL5OPT PERL5LIB PERLLIB PERLIO PERL_UNICODE PERL_BADLANG LC_ALL);
                my @saved = splice @ARGV, 0, scalar @names;
                for my $i (0 .. $#names) {
                    if (length $saved[$i]) { $ENV{$names[$i]} = substr $saved[$i], 1 } else { delete $ENV{$names[$i]} }
                }
                if (open(my $up, ">&=", $fds[0])) { syswrite $up, "$$\n" }
                for my $fd (@fds) { if (open(my $h, "<&=", $fd)) { close $h } }
                exec { $found } @ARGV;
                exec "/bin/sh", "-c", q("$@"), $me, @ARGV;
                exit 126;
            ' "$0" "$found" "$kw" "$kr" "$kd" "${PERL5OPT+x$PERL5OPT}" "${PERL5LIB+x$PERL5LIB}" \
                "${PERLLIB+x$PERLLIB}" "${PERLIO+x$PERLIO}" "${PERL_UNICODE+x$PERL_UNICODE}" \
                "${PERL_BADLANG+x$PERL_BADLANG}" "${LC_ALL+x$LC_ALL}" "$@"
            PERL5OPT= PERL5LIB= PERLLIB= PERLIO= PERL_UNICODE=0 PERL_BADLANG=0 LC_ALL=C
            export PERL5OPT PERL5LIB PERLLIB PERLIO PERL_UNICODE PERL_BADLANG LC_ALL
            ;;
        *)
            [ "${1-}" = exec ] || direct=yes
            ;;
    esac
fi
status=0
running=yes
if [ -z "$direct" ]; then
    "$@" || status=$?
else
    (
        /bin/sh -c 'printf "%s\n" "$PPID"' >&"$kw"
        eval "exec $kr<&- $kw>&- $kd<&-"
        "$@"
    ) || status=$?
fi
running=
exit "$status"
