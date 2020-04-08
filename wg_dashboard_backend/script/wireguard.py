import logging
import subprocess
import const
import schemas
import os
import re

_LOGGER = logging.getLogger(__name__)


class WGAlreadyStartedError(Exception):
    pass


class WGAlreadyStoppedError(Exception):
    pass


class WGPermissionsError(Exception):
    pass


def _run_wg(server: schemas.WGServer, command):
    try:
        output = subprocess.check_output(const.CMD_WG_COMMAND + command, stderr=subprocess.STDOUT)
        return output
    except Exception as e:
        if b'Operation not permitted' in e.output:
            raise WGPermissionsError("The user has insufficientt permissions for interface %s" % server.interface)

def is_installed():
    output = subprocess.check_output(const.CMD_WG_COMMAND)
    return output == b'' or b'interface' in output


def generate_keys():

    private_key = subprocess.check_output(const.CMD_WG_COMMAND + ["genkey"])
    public_key = subprocess.check_output(
        const.CMD_WG_COMMAND + ["pubkey"],
        input=private_key
    )
    return private_key.decode("utf-8").strip(), public_key.decode("utf-8").strip()


def generate_psk():
    return subprocess.check_output(const.CMD_WG_COMMAND + ["genpsk"]).decode("utf-8").strip()


def start_interface(server: schemas.WGServer):
    server_file = os.path.join(const.SERVER_DIR(server.interface), server.interface + ".conf")

    try:
        print(*const.CMD_WG_QUICK, "up", server_file)
        output = subprocess.check_output(const.CMD_WG_QUICK + ["up", server_file], stderr=subprocess.STDOUT)
        return output
    except Exception as e:

        if b'already exists' in e.output:
            raise WGAlreadyStartedError("The wireguard device %s is already started." % server.interface)


def stop_interface(server: schemas.WGServer):
    server_file = os.path.join(const.SERVER_DIR(server.interface), server.interface + ".conf")

    try:
        output = subprocess.check_output(const.CMD_WG_QUICK + ["down", server_file], stderr=subprocess.STDOUT)
        return output
    except Exception as e:

        if b'is not a WireGuard interface' in e.output:
            raise WGAlreadyStoppedError("The wireguard device %s is already stopped." % server.interface)


def restart_interface(server: schemas.WGServer):

    try:
        stop_interface(server)
    except WGAlreadyStoppedError:
        pass
    start_interface(server)


def is_running(server: schemas.WGServer):

    try:
        output = _run_wg(server, ["show", server.interface])
        if output is None:
            return False
    except Exception as e:
        if b'No such device' in e.output:
            return False
    return True


def add_peer(server: schemas.WGServer, peer: schemas.WGPeer):
    try:
        output = _run_wg(server, ["set", server.interface, "peer", peer.public_key, "allowed-ips", peer.address])
        return output == b''
    except Exception as e:
        _LOGGER.exception(e)
        return False


def remove_peer(server: schemas.WGServer, peer: schemas.WGPeer):
    try:
        output = _run_wg(server, ["set", server.interface, "peer", peer.public_key, "remove"])
        return output == b''
    except Exception as e:
        _LOGGER.exception(e)
        return False


def get_stats(server: schemas.WGServer):
    try:
        output = _run_wg(server, ["show", server.interface])
        if not output:
            return []
        regex = r"peer:.*?^\n"
        test_str = output.decode("utf-8") + "\n"

        peers = []

        peers_raw = re.findall(regex, test_str, re.MULTILINE | re.DOTALL)

        for peer in peers_raw:
            peer = peer.strip()
            lines = [x.split(": ")[1] for x in peer.split("\n")]

            if len(lines) == 2:
                public_key, allowed_ips = lines
                peers.append(dict(
                    public_key=public_key,
                    client_endpoint=None,
                    allowed_ips=allowed_ips,
                    handshake=None,
                    rx=None,
                    tx=None
                ))
            elif len(lines) == 5:

                public_key, client_endpoint, allowed_ips, handshake, rx_tx = lines

                rx = re.match(r"^(.*) received", rx_tx).group(1)
                tx = re.match(r"^.*, (.*)sent", rx_tx).group(1)
                peers.append(dict(
                    public_key=public_key,
                    client_endpoint=client_endpoint,
                    allowed_ips=allowed_ips,
                    handshake=handshake,
                    rx=rx,
                    tx=tx
                ))
            else:
                ValueError("We have not handled peers with line number of %s" % str(len(lines)))

        return peers
    except Exception as e:
        _LOGGER.exception(e)
        return []
