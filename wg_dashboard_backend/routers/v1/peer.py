import ipaddress
import itertools
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import const
import models
import schemas
import middleware
import db.wireguard
import script.wireguard

router = APIRouter()


def generate_ip_address(server: schemas.WGServer, v6):
    if v6:
        address_space = set(
            itertools.islice(ipaddress.ip_network("fd42:42:42::1/64", strict=False).hosts(), 1, 1024)
        )
    else:
        address_space = set(ipaddress.ip_network(f"{server.address}/{server.subnet}", strict=False).hosts())
    occupied_space = set()

    # Try add server IP to list.
    try:
        occupied_space.add(ipaddress.ip_address(server.v6_address if v6 else server.address))
    except ValueError:
        pass

    for p in server.peers:

        # Try add peer ip to list.
        try:
            occupied_space.add(ipaddress.ip_address(p.v6_address if v6 else p.address))
        except ValueError as e:
            pass  # Ignore invalid addresses. These are out of address_space

    address_space -= occupied_space

    # Select first available address
    return str(list(sorted(address_space)).pop(0))


@router.post("/add", response_model=schemas.WGPeer)
def add_peer(
        peer_add: schemas.WGPeerAdd,
        sess: Session = Depends(middleware.get_db)
):
    server = schemas.WGServer(interface=peer_add.server_interface).from_db(sess)
    peer = schemas.WGPeer(server_id=server.id)

    if server.v6_address:
        peer.v6_address = generate_ip_address(server, v6=True)
    peer.address = generate_ip_address(server, v6=False)

    # Private public key generation
    keys = script.wireguard.generate_keys()
    peer.private_key = keys["private_key"]
    peer.public_key = keys["public_key"]

    # Set 0.0.0.0/0, ::/0 as default allowed ips
    peer.allowed_ips = ', '.join(const.PEER_DEFAULT_ALLOWED_IPS)

    # Set unnamed
    peer.name = "Unnamed"

    peer.dns = server.dns

    peer.configuration = script.wireguard.generate_config(dict(
        peer=peer,
        server=server
    ))

    db_peer = models.WGPeer(**peer.dict())
    sess.add(db_peer)
    sess.commit()

    # If server is running. Add peer
    if script.wireguard.is_running(server):
        script.wireguard.add_peer(server, peer)

    # Update server configuration
    db.wireguard.server_update_configuration(sess, db_peer.server_id)

    return schemas.WGPeer.from_orm(db_peer)


@router.post("/delete", response_model=schemas.WGPeer)
def delete_peer(
        peer: schemas.WGPeer,
        sess: Session = Depends(middleware.get_db)
):

    server = sess.query(models.WGServer).filter_by(id=peer.server_id).one()

    if not db.wireguard.peer_remove(sess, peer):
        raise HTTPException(400, detail="Were not able to delete peer %s (%s)" % (peer.name, peer.public_key))

    if script.wireguard.is_running(schemas.WGServer(interface=server.interface)):
        script.wireguard.remove_peer(server, peer)

    return peer


@router.post("/edit")
def edit_peer(
        peer: schemas.WGPeer,
        sess: Session = Depends(middleware.get_db)
):

    peer = db.wireguard.peer_edit(sess, peer)

    return peer
