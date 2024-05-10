### IMPORTS
### ============================================================================
## Future
from __future__ import annotations

## Standard Library
import argparse
from dataclasses import dataclass
import logging
import sys
import time

## Installed
from docker import DockerClient
import netifaces
import nserver
import pillar.application

## Application
from . import _version

### CLASSES
### ============================================================================
_APP = None


### FUNCTIONS
### ============================================================================
def get_available_ips():
    """Get all available IPv4 Address on this machine."""
    # Source: https://stackoverflow.com/a/274644
    ip_list = []
    for interface in netifaces.interfaces():
        for link in netifaces.ifaddresses(interface).get(netifaces.AF_INET, []):
            ip_list.append(link["addr"] + f" ({interface})")

    # shortcut for all
    ip_list.append("0.0.0.0 (all above)")
    return ip_list


def main(argv=None):
    """Main function for use with setup.py"""
    global _APP  # pylint: disable=global-statement

    _APP = Application(argv)
    exit_code = _APP.run()
    return exit_code


### CLASSES
### ============================================================================
@dataclass
class CachedContainer:
    container_ids: dict[str, str]
    container_name: str
    project_name: str
    ipv4_addresses: list[str]
    ipv6_addresses: list[str]
    last_updated: float


class Application(pillar.application.Application):
    """dcdc (Docker Container Domain Connector) is a dns server that allows mapping docker containers to their currently running bridge ip address."""

    name = "dcdc"
    application_name = "dcdc"
    version = _version.VERSION_INFO

    epilog = "\n".join(
        (
            f"Version: {version}",
            "",
            "For full information including licence see https://github.com/nhairs/docker-container-domain-connector",
            "",
            "Copyright (c) 2023 Nicholas Hairs",
        )
    )

    def setup(self) -> None:
        super().setup()
        self.nserver = self.get_nserver()
        self.container_cache: dict[str, CachedContainer] = {}
        self.docker = DockerClient()
        return

    def main(self) -> None:
        if self.args.ips:
            print("\n".join(get_available_ips()))
            return

        self.nserver.run()
        return

    def get_argument_parser(self):
        parser = super().get_argument_parser()

        # Server settings
        parser.add_argument(
            "--host",
            action="store",
            default="localhost",
            help="Host (IP) to bind to. Use --ips to see available. Defaults to localhost.",
        )
        parser.add_argument(
            "--port",
            action="store",
            default=9953,
            type=int,
            help="Port to bind to. Defaults to 9953.",
        )

        transport_group = parser.add_mutually_exclusive_group()
        transport_group.add_argument(
            "--tcp",
            action="store_const",
            const="TCPv4",
            dest="transport",
            help="Use TCPv4 socket for transport.",
        )
        transport_group.add_argument(
            "--udp",
            action="store_const",
            const="UDPv4",
            dest="transport",
            help="Use UDPv4 socket for transport. (default)",
        )

        # DNS settings
        parser.add_argument(
            "--root-domain",
            action="store",
            default=".dcdc",
            help='Root domain for queries (e.g. <query>.<root>). Does not have to be a TLD, can be any level of domain. Defaults to ".dcdc".',
        )

        # Misc
        parser.add_argument("--ips", action="store_true", help="Print available IPs and exit")

        parser.set_defaults(transport="UDPv4")
        return parser

    def get_nserver(self) -> nserver.NameServer:
        """Get NameServer instance."""
        server = nserver.NameServer("dcdc")

        server.settings.SERVER_TYPE = self.args.transport
        server.settings.SERVER_ADDRESS = self.args.host
        server.settings.SERVER_PORT = self.args.port
        server.settings.CONSOLE_LOG_LEVEL = logging.WARNING

        self.args.root_domain = self.args.root_domain.strip(".")
        server.settings.ROOT_DOMAIN = self.args.root_domain

        self.attach_rules(server)
        return server

    def attach_rules(self, server: nserver.NameServer) -> None:
        @server.rule(f"*.*.{server.settings.ROOT_DOMAIN}", ["A", "AAAA"])
        def compose_project_rule(query):
            if query.name not in self.container_cache:
                # cache miss, check for new containers
                self.populate_cache()

            if query.name in self.container_cache:
                container = self.container_cache[query.name]
                now = time.time()
                if now - container.last_updated > 60:
                    # stale cache update
                    self.populate_cache()
                    if query.name in self.container_cache:
                        container = self.container_cache[query.name]
                    else:
                        return None

                ttl = 60 - int(now - container.last_updated)
                response = nserver.Response()
                if query.type == "A":
                    for ip in self.container_cache[query.name].ipv4_addresses:
                        response.answers.append(nserver.A(query.name, ip, ttl=ttl))
                else:
                    # AAAA / IPv6
                    for ip in self.container_cache[query.name].ipv6_addresses:
                        response.answers.append(nserver.AAAA(query.name, ip, ttl=ttl))
                return response
            return None

        return

    def populate_cache(self):
        self.info("populating cache")
        cache: dict[str, CachedContainer] = {}
        # Get new entries
        for container in self.docker.containers.list():
            self.info(f"cache: checking {container.name}")
            container_labels = container.attrs["Config"]["Labels"]
            project_name = container_labels.get("com.docker.compose.project", None)
            if project_name is None:
                # not a docker-compose project container
                continue

            container_name = container_labels.get("com.docker.compose.service")
            cache_key = f"{container_name}.{project_name}.{self.nserver.settings.ROOT_DOMAIN}"

            cached_container = cache.get(cache_key, None)
            if cached_container is None:
                cached_container = CachedContainer(
                    container_ids=dict(),
                    container_name=container_name,
                    project_name=project_name,
                    ipv4_addresses=list(),
                    ipv6_addresses=list(),
                    last_updated=time.time(),
                )
                cache[cache_key] = cached_container

            # update cached_container

            cached_container.container_ids[
                container_labels["com.docker.compose.container-number"]
            ] = container.id

            for network in container.attrs["NetworkSettings"]["Networks"].values():
                ipv4_address = network.get("IPAddress", "")
                if ipv4_address:
                    cached_container.ipv4_addresses.append(ipv4_address)

                ipv6_address = network.get("GlobalIPv6Address", "")
                if ipv6_address:
                    cached_container.ipv6_addresses.append(ipv6_address)

        self.container_cache = cache
        return
