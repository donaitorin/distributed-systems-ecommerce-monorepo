# 0008. Gateway: trusted forwarded headers and per-client rate limits

Status: accepted (2026-10-15)

## Context

The gateway rate limits `POST /api/v1/auth/login` (10 per minute, burst 10) and `POST /api/v1/auth/register` (5 per minute, burst 5) by source address. From E8 the Next.js servers make these calls on behalf of users, so every request would come from the store or backoffice container and the limit would become global: a few logins in a minute would lock everyone out. At the same time a client must not be able to choose its own bucket by sending an `X-Forwarded-For` header.

## Decision

1. **Only the two frontend servers are trusted.** The `frontend` Docker network has a fixed subnet (`10.250.10.0/28`); the store is `10.250.10.2` and the backoffice `10.250.10.3`. The network also has an `ip_range` (`10.250.10.8/29`) for containers without a fixed address, so the gateway can never be handed `.2` or `.3` before the store or the backoffice start (that race made `make up` fail intermittently). The `web` entry point lists exactly those two addresses in `forwardedHeaders.trustedIPs`. From any other source Traefik discards the incoming `X-Forwarded-For` and sets it to the connection's address. The entry point also deletes alias headers such as `X_Forwarded_For` (`aliasHeadersStrategy: delete`).
2. **The Next.js servers forward the visitor's address.** `packages/auth` takes the last entry of the `X-Forwarded-For` it received (the address our own gateway wrote) and sends it as `X-Forwarded-For` on the calls to the gateway (`API_BASE_URL=http://gateway:80`, the same entry point). Traefik trusts that header from the store and appends the store's address, so the upstream sees `client, 10.250.10.2`.
3. **Two routers per limited endpoint, split by source address.** Requests whose connection comes from the store or backoffice (`ClientIP(...)`, priority 101) use a limiter keyed on the forwarded client, with `ipStrategy.excludedIPs` set to the two frontend addresses, so the key is the rightmost address that is not ours. Every other request (priority 100) uses the plain limiter keyed on the connection address. One limiter with `excludedIPs` for everything does not work: for an untrusted source Traefik has already removed the header, the key is empty, and all outside clients share one bucket (found while building the proof).

Alternatives considered: limiting inside the Next.js servers (loses the single enforcement point and does not protect direct API use), and keying on a custom header set by the servers (trivially forgeable by anyone who can reach the gateway).

## What is proven, and what is not

`make check-rate-limit` (also a CI job) starts an isolated stack with the real `traefik.yml` and `dynamic/*.yml` (only the subnet prefix is rewritten so it can run beside the main stack), a `whoami` backend that echoes the headers it receives, and throwaway curl containers: two or three outside clients with different addresses, a container on the frontend network that is not the store, and a stand-in that has the store's trusted address. It checks that:

- an `X-Forwarded-For` chain or an underscore alias sent from outside never reaches the backend; the backend sees only the real source address;
- the same holds for a container on the frontend network that is not the store or backoffice;
- the trusted hop's header is kept and its own address appended (`203.0.113.7, 10.250.20.2`);
- two clients get separate buckets and a spoofed header neither lets a limited client escape nor drains another client's bucket;
- behind the trusted hop each forwarded client has its own bucket;
- login and register have separate limits (11th and 6th request are `429`).

Also checked by hand against the running stack: from inside the real store container, twelve logins with `X-Forwarded-For: 203.0.113.50` get `401` ten times and `429` twice, a second address gets its own ten attempts, and a spoofing request from the host does not touch that bucket.

Not covered:

- Docker Desktop shows every request from the host as one address, so two real browsers on one machine cannot be told apart; that is why the proof uses containers. Direct browser traffic to the gateway from the host therefore shares one bucket locally, and in a real deployment sees real addresses.
- The full browser path through the Next.js login pages: the proof exercises the store hop with a stand-in and with a fetch from the real store container, not with the real forms.
- IPv6 forwarded addresses and a load balancer or CDN in front of Traefik. With one in front, its address must also be trusted and the client is the rightmost address that is not one of ours, which changes how `packages/auth` picks the address.
- Limits are in memory per Traefik instance; several gateway replicas would each count separately.

If the store or backoffice has no address to forward, the hop shares one bucket (degraded, never unlimited); a test pins that behaviour.

## Operational notes

- A stack created before the `ip_range` was added to the `frontend` network needs `docker compose down` once (never `-v`: the volumes keep the data), because Docker cannot change the ranges of an existing network.
- `10.250.10.0/28` can collide with some VPNs and with other Docker networks, and two stacks cannot run side by side. Changing it means editing the four places that name it together, see ADR 0020.

## Consequences

- The two trusted addresses are written in three files that must change together: `infra/gateway/traefik.yml`, `infra/gateway/dynamic/auth.yml` (rules and limiters) and the static addresses in `docker-compose.yml`. Scaling a zone to replicas means giving the zone a small fixed range and trusting that range.
- The gateway mounts the whole `infra/gateway` directory at `/etc/traefik`, not `traefik.yml` as a single file. A single-file bind mount keeps pointing at the old inode when git rewrites the file (a branch switch, a pull), so the container saw an empty `traefik.yml` and `traefik healthcheck` failed while routing still worked from the configuration it had already loaded; `make up` then waited on a gateway that never became healthy.
- Changing a limit means editing the two limiters of an endpoint.
