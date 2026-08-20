#!/usr/bin/env bash
#
# Bring this host's firewall and intrusion-protection in line with
# docs/security.md §4 and §6.
#
#   scripts/harden_host.sh            # dry run — prints, changes nothing
#   scripts/harden_host.sh --apply    # actually applies
#
# Dry run is the default deliberately. This script can change how you reach
# this machine, and one of the rules it removes may be the one your current
# SSH session is using. Read the plan it prints before passing --apply.
#
# What it fixes, and why each is not already done:
#
#   1. SSH is reachable from the whole LAN. `ufw status` on this host shows
#      `22/tcp ALLOW IN Anywhere` (v4 and v6), while docs/security.md §4
#      specifies SSH on tailscale0 only. Every device on the home network —
#      including anything that joins it later — can currently reach sshd.
#   2. ufw may not be managing IPv6. docs/security.md §2 calls this out as the
#      leak that defeats the whole tunnel design: this connection has a
#      globally-routable delegated IPv6 prefix (docs/CLAUDE.md §2.1), so with
#      IPV6=no in /etc/default/ufw the v6 stack is simply unfiltered.
#   3. fail2ban is not installed, so repeated failures are refused one at a
#      time forever rather than escalating to a ban (docs/security.md §6).
#
# --- WSL2 caveat, which changes what this script can promise ---------------
# This host is WSL2 (`systemd-detect-virt` → wsl). ufw here filters the Linux
# distro only. Inbound traffic from the LAN reaches WSL2 through the Windows
# host's NAT and the *Windows* firewall, which this script cannot configure.
# So these rules harden the server VM; they are not the outer perimeter.
# The outer perimeter is that nothing is port-forwarded (CGNAT makes inbound
# IPv4 impossible upstream anyway) and that the tunnel is outbound-only.

set -o pipefail
cd "$(dirname "$0")/.."

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

step()  { printf '\n\033[1m%s\033[0m\n' "$1"; }
note()  { printf '  %s\n' "$1"; }
ok()    { printf '  \033[32mOK\033[0m    %s\n' "$1"; }
todo()  { printf '  \033[33mTODO\033[0m  %s\n' "$1"; }
bad()   { printf '  \033[31mSTOP\033[0m  %s\n' "$1"; }

run() {
  if [[ $APPLY -eq 1 ]]; then
    printf '  \033[36m$\033[0m %s\n' "$*"
    "$@" || { bad "command failed: $*"; exit 1; }
  else
    printf '  \033[90mwould run:\033[0m %s\n' "$*"
  fi
}

# Same as run(), but a non-zero exit is expected and not fatal. Used for the
# rule deletions below: ufw refuses to delete a rule that does not exist, and
# which spelling exists depends on how the rule was originally added.
run_optional() {
  if [[ $APPLY -eq 1 ]]; then
    printf '  \033[36m$\033[0m %s\n' "$*"
    "$@" 2>&1 | sed 's/^/        /' || true
  else
    printf '  \033[90mwould try:\033[0m %s\n' "$*"
  fi
}

if [[ $APPLY -eq 0 ]]; then
  printf '\033[33m*** DRY RUN — nothing will change. Re-run with --apply to act. ***\033[0m\n'
fi

# --- Preconditions ---------------------------------------------------------
# Checked before anything is changed, because the SSH rule swap below is only
# safe if Tailscale is actually up. Removing the open SSH rule while the
# tailnet is down would leave no way back in over the network at all.
step "Preconditions"

command -v ufw >/dev/null || { bad "ufw is not installed — apt install ufw"; exit 1; }
ok "ufw present"

if ! command -v tailscale >/dev/null; then
  bad "tailscale is not installed — SSH would become unreachable. Install and join the tailnet first."
  exit 1
fi

TS_IP=$(tailscale ip -4 2>/dev/null | head -1)
if [[ ! "$TS_IP" =~ ^100\. ]]; then
  bad "this host has no tailnet address (got '${TS_IP:-none}') — run: tailscale up"
  exit 1
fi
ok "tailnet address is $TS_IP"

if ! ip link show tailscale0 >/dev/null 2>&1; then
  bad "the tailscale0 interface does not exist — the rules below would match nothing"
  exit 1
fi
ok "tailscale0 interface is up"

# --- 1. IPv6 ---------------------------------------------------------------
step "1. ufw must manage IPv6 (docs/security.md §2)"

if grep -qi '^IPV6=yes' /etc/default/ufw 2>/dev/null; then
  ok "IPV6=yes already set"
else
  todo "IPV6 is not enabled — inbound IPv6 currently bypasses ufw entirely"
  note "This host has a routable delegated IPv6 prefix, so this is the leak"
  note "that would make the tunnel's IP-hiding property moot."
  run sudo sed -i 's/^IPV6=.*/IPV6=yes/' /etc/default/ufw
fi

# --- 2. Default policies ---------------------------------------------------
step "2. Default-deny inbound (docs/security.md §4)"
run sudo ufw default deny incoming
run sudo ufw default allow outgoing

# --- 3. SSH: tailnet only --------------------------------------------------
step "3. SSH restricted to the tailnet (docs/security.md §3, §4)"

# Order matters and is the whole reason this is a script rather than a doc
# snippet: the permissive rule is deleted only AFTER the tailscale0 rule is in
# place, so there is never a window with no way in.
note "Adding the tailnet rules first, deleting the open ones second —"
note "so there is never a moment when no SSH rule permits access."
run sudo ufw allow in on tailscale0
run sudo ufw allow in on tailscale0 to any port 22 proto tcp

# `ufw status` labels this rule by its app profile ("SSH"); only `status
# verbose` spells out the port ("22/tcp (SSH)"). Matching both forms, because
# matching only one silently reports an open port as closed — which is the
# worst possible direction for this check to fail in.
ufw_rules=$(sudo -n ufw status verbose 2>/dev/null)
if [[ -z "$ufw_rules" ]]; then
  bad "could not read ufw status (needs sudo) — cannot tell whether SSH is exposed"
  exit 1
fi
open_ssh=$(grep -E '^(22(/tcp)?|SSH)[[:space:](]' <<<"$ufw_rules" | grep -v tailscale0 | grep 'ALLOW')
if [[ -z "$open_ssh" ]]; then
  ok "no SSH rule open beyond the tailnet"
else
  todo "removing SSH rules that are open beyond the tailnet:"
  sed 's/^/          /' <<<"$open_ssh"
  if [[ $APPLY -eq 1 ]]; then
    printf '\n  \033[31mThis may drop the SSH session you are using right now.\033[0m\n'
    printf '  Reconnect afterwards over Tailscale: ssh %s\n' "$TS_IP"
    read -r -p "  Type 'yes' to remove them: " confirm
    [[ "$confirm" == "yes" ]] || { note "skipped — SSH rules left as they are"; }
  fi
  # ufw deletes by rule *specification*, so the spelling has to match how the
  # rule was added — `ufw allow SSH` (app profile) is not deleted by
  # `ufw delete allow 22/tcp`. On this host the rules read "22/tcp (SSH)",
  # i.e. added via the profile. Rather than guess, try each spelling and let
  # the ones that do not apply fail harmlessly, then verify the result.
  if [[ $APPLY -eq 0 || "${confirm:-}" == "yes" ]]; then
    run_optional sudo ufw delete allow SSH
    run_optional sudo ufw delete allow 22/tcp
    run_optional sudo ufw delete allow 22
  fi

  if [[ $APPLY -eq 1 && "${confirm:-}" == "yes" ]]; then
    # Verify rather than assume: a delete that matched nothing exits non-zero
    # and is swallowed above, so without this the script would report success
    # while SSH stayed open.
    still_open=$(sudo -n ufw status verbose 2>/dev/null \
      | grep -E '^(22(/tcp)?|SSH)[[:space:](]' | grep -v tailscale0 | grep 'ALLOW')
    if [[ -n "$still_open" ]]; then
      bad "SSH is STILL open beyond the tailnet after deletion:"
      sed 's/^/          /' <<<"$still_open"
      note "Delete it by number instead:  sudo ufw status numbered && sudo ufw delete <n>"
    else
      ok "SSH is now reachable over the tailnet only"
    fi
  fi
fi

step "4. Enable ufw"
run sudo ufw --force enable

# --- 5. fail2ban -----------------------------------------------------------
step "5. fail2ban (docs/security.md §6)"

if systemctl is-active --quiet fail2ban 2>/dev/null; then
  ok "fail2ban is already running"
else
  todo "fail2ban is not running"
  note "Redundant with steps 3–4 for SSH, which is the point: it is the layer"
  note "that still works if a firewall rule regresses, and the only one that"
  note "escalates repeated failures into a ban rather than refusing forever."
  # This host is Fedora (WSL), not Debian/Ubuntu — an earlier version of this
  # script hardcoded apt-get and died here with "command not found". Detect
  # instead of assuming, so it works on either family.
  if command -v dnf >/dev/null; then
    run sudo dnf install -y fail2ban
  elif command -v apt-get >/dev/null; then
    run sudo apt-get install -y fail2ban
  else
    bad "no supported package manager found (looked for dnf, apt-get)"
    note "Install fail2ban by hand, then re-run."
    exit 1
  fi

  # Only jail sshd if sshd actually exists. On this host it does not (no sshd
  # binary, nothing listening on :22), so enabling the jail would either fail
  # to start or sit watching a log that is never written — which looks like
  # protection without being any.
  if command -v sshd >/dev/null || systemctl list-unit-files 2>/dev/null | grep -qE '^(ssh|sshd)\.service'; then
    ssh_jail_enabled="true"
    ok "sshd present — enabling the sshd jail"
  else
    ssh_jail_enabled="false"
    todo "sshd is NOT installed on this host, so the sshd jail is written disabled"
    note "Nothing listens on :22, so there is no SSH surface to protect today."
    note "If you ever install an SSH server, flip this to true in"
    note "/etc/fail2ban/jail.local and restart fail2ban."
  fi

  if [[ $APPLY -eq 1 ]]; then
    sudo tee /etc/fail2ban/jail.local >/dev/null <<JAIL
# Managed by scripts/harden_host.sh — see docs/security.md §6.
[DEFAULT]
# The tailnet is the admin's own devices; locking them out on a fat-fingered
# password helps nobody.
ignoreip = 127.0.0.1/8 ::1 100.64.0.0/10

# ufw is what is actually active on this host. Fedora's fail2ban would
# otherwise default to a firewalld action, and bans would be written to a
# firewall that is not enforcing anything here.
banaction = ufw

[sshd]
enabled  = $ssh_jail_enabled
maxretry = 5
findtime = 900
bantime  = 3600
JAIL
    printf '  \033[36m$\033[0m wrote /etc/fail2ban/jail.local (sshd jail enabled=%s)\n' "$ssh_jail_enabled"
  else
    printf '  \033[90mwould write:\033[0m /etc/fail2ban/jail.local (banaction=ufw, tailnet ignored, sshd jail enabled=%s)\n' "$ssh_jail_enabled"
  fi
  run sudo systemctl enable --now fail2ban
fi

# --- Result ----------------------------------------------------------------
step "Result"
if [[ $APPLY -eq 1 ]]; then
  sudo -n ufw status verbose 2>/dev/null | sed 's/^/  /'
  note ""
  note "Verify from another device on the tailnet:  ssh $TS_IP"
  note "Then re-run: make preflight"
else
  note "Dry run complete. Nothing changed."
  note "Re-run with --apply once you have read the plan above."
fi
