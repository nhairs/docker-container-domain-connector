### IMPORTS
### ============================================================================
## Future
from __future__ import annotations

## Standard Library
from dataclasses import dataclass
import time

## Installed
from docker import DockerClient
import ifaddr
import nserver
import pillar.application

## Application
from . import _version

### CLASSES
### ============================================================================
_APP: pillar.application.Application


### FUNCTIONS
### ============================================================================
def get_available_ips() -> list[str]:
    """Get all available IPv4 Address on this machine."""
    # Source: https://stackoverflow.com/a/274644
    ip_list: list[str] = []
    for adaptor in ifaddr.get_adapters():
        for _ip in adaptor.ips:
            ip = _ip.ip
            if isinstance(ip, str):
                # IPv4
                ip_list.append(f"{ip}\t({adaptor.nice_name})")
            elif isinstance(ip, tuple):
                # IPv6
                # Currently only IPv4
                pass
                # ip_list.append(f"{ip[0]}]\t({adapter.nice_name})")
            else:
                raise ValueError(f"Unsupported IP: {ip!r}")

    ip_list.sort()
    # shortcut for all
    ip_list.append("0.0.0.0\t(all)")
    return ip_list


def main(argv=None):
    """Main function entrypoint for dcdc"""
    global _APP  # pylint: disable=global-statement

    _APP = Application(argv)
    exit_code = _APP.run()
    return exit_code


def ips_main() -> None:
    """Main function entrypoint for dcdc-ips"""
    print("\n".join(get_available_ips()))
    return


### CLASSES
### ============================================================================
@dataclass
class CachedContainer:
    """Dataclass for caching container info"""

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

    config_args_enabled = False
    config_required = False

    logging_manifest = pillar.application.LoggingManifest(additional_namespaces=["nserver"])  # type: ignore[call-arg]

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        self.nserver = self.get_nserver()
        self.container_cache: dict[str, CachedContainer] = {}
        self.docker = DockerClient()
        return

    def main(self) -> None:
        self.info(f"Starting server on {self.args.transport} {self.args.host}:{self.args.port}")
        self.nserver.run()
        self.info("Shutting down")
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

        parser.set_defaults(transport="UDPv4")
        return parser

    def get_nserver(self) -> nserver.NameServer:
        """Get NameServer instance."""
        server = nserver.NameServer("dcdc")

        server.settings.SERVER_TYPE = self.args.transport
        server.settings.SERVER_ADDRESS = self.args.host
        server.settings.SERVER_PORT = self.args.port
        server.settings.CONSOLE_LOG_LEVEL = 100
        server.settings.FILE_LOG_LEVEL = 1

        self.args.root_domain = self.args.root_domain.strip(".")
        server.settings.ROOT_DOMAIN = self.args.root_domain

        self.attach_rules(server)
        return server

    def attach_rules(self, server: nserver.NameServer) -> None:
        """Attach rules to the given nserver instance"""

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

    def populate_cache(self) -> None:
        """Populate self.container_cache"""
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
                    container_ids={},
                    container_name=container_name,
                    project_name=project_name,
                    ipv4_addresses=[],
                    ipv6_addresses=[],
                    last_updated=time.time(),
                )
                cache[cache_key] = cached_container

            # update cached_container

            cached_container.container_ids[
                container_labels.get("com.docker.compose.container-number", 0)
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
