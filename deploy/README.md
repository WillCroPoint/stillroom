# Stillroom: Docker, Unraid and Nginx

[← Back to the README](../README.md)

One image, no cloud service, database, Node.js or Rust required. The optional
epd-dither engine is not installed in this image. UI labels and CLI options remain
English. The existing `python gui.py` local workflow is unchanged.

## First start (generic Docker)

Requirements: Git, Bash, Docker Engine and Docker Compose **v2.20+**. Clone **your
fork containing these deployment files**, then from its root:

```bash
cp deploy/docker/env.example deploy/docker/.env
# Edit deploy/docker/.env, especially PUID/PGID (id -u / id -g).
./deploy/manage.sh start
```

Open http://localhost:8080. To access from another machine, set
`BIND_ADDRESS=0.0.0.0` (or the server's LAN IP) and set
`FRAIMIC_PUBLIC_ORIGIN=http://SERVER_IP:8080` to the exact browser address.
Do not put a trailing slash on the origin. Changing `PORT` also requires updating
the origin. The configured hostname and port are explicitly allowed; arbitrary
Host headers and cross-origin writes remain rejected.

The `.env` is ignored by Git. It is sourced by Bash as trusted local configuration,
so use simple `NAME=value` assignments, quote paths with spaces, and do not paste
untrusted shell commands into it. Relative DATA_DIR paths are resolved relative
to `deploy/docker`; an absolute path is recommended on a server.

The start command builds before replacing a running container, then waits for its
health check. No container is stopped if the build fails. A failed runtime health
check is reported; it does not automatically roll back the running container.

## Unraid

1. Enable Docker in Unraid and install the **Docker Compose Manager** plugin if
   `docker compose version` is not available. These containers are managed by
   Compose, not by a second native Docker template.
2. Clone your fork into a persistent share, e.g.
   `/mnt/user/appdata/fraimic-studio-source` (not the USB boot device or /tmp).
3. From that checkout:

```bash
cp deploy/unraid/env.example deploy/docker/.env
# Edit the exact browser URL (tower or the server's IP), Git remote and branch.
./deploy/manage.sh start
```

The Unraid example uses UID 99 / GID 100 (`nobody:users`) and stores configuration
at `/mnt/user/appdata/fraimic-studio/frames.json`. When run as root, the helper sets
ownership on a **newly created** data directory only. Existing directories/files
are never recursively chowned. If reusing a directory, grant that UID write
access to both it and frames.json. Docker runs the application unprivileged.

To migrate existing frames, stop the container, copy your existing frames.json to
DATA_DIR, ensure it is writable by PUID/PGID, and start again. Never copy it into
the image. Prefer a local DNS name or reserved IP for each frame: multicast `.local`
resolution is not guaranteed inside a Docker bridge network. Bridge networking
with the published web port is sufficient; host networking is not required.

## Apply .env changes and customise the Unraid icon

After editing `deploy/docker/.env`, run:

```bash
./deploy/manage.sh apply
```

This recreates the container using the existing image, without rebuilding or
pulling Git. A plain Docker restart does not apply environment/port/label changes.
It preserves DATA_DIR (if you did not change its path) but clears temporary images;
finish active conversions/uploads first. Use `start` for the first installation.

A bundled 256×256 PNG icon is used by default, served at
`FRAIMIC_PUBLIC_ORIGIN/icon.png`. It is original artwork matching the companion
app, not the official Fraimic logo. The editable SVG lives in `web/icon.svg`;
`deploy/assets/build_icon.py` rebuilds the PNG using Pillow.
Safari/browser icons are also bundled: `/favicon.ico` (16/32/48 px),
`/icon.png` (256 px) and `/apple-touch-icon.png` (opaque, 180 px).
The Nginx template proxies all of them through `location /`. If your existing
Nginx configuration has a separate favicon/static-image location, remove it for
this virtual host or proxy those paths to the same backend.
No GitHub hosting or external image service is required. Unraid must be able to
reach the configured public URL; if your proxy requires login, allow anonymous
access to this icon alone or provide another reachable URL.

To override the default, add `UNRAID_ICON_URL=https://your-server.example/icon.png` to
`.env`, with a direct image URL reachable from Unraid, then run `apply` and refresh
the Unraid page. The Compose file declares `net.unraid.docker.icon` and
`net.unraid.docker.webui`; the WebUI URL follows FRAIMIC_PUBLIC_ORIGIN.
These labels are harmless on other Docker hosts. An empty or omitted UNRAID_ICON_URL selects the bundled icon.

Launching via this helper does not register a stack in Compose Manager's own
project database. A “3rd Party” badge is therefore expected; adding an icon does
not require changing ownership to Compose Manager. Its stack controls require
explicit registration/import (depending on plugin version); don't create a second
copy of the stack just to change the icon. Keep this helper as the update mechanism
for the locally built image.

To inspect the running settings from the repository root:

```bash
docker inspect fraimic-studio --format '{{json .Config.Env}}'
docker port fraimic-studio
```

## Container name and automatic startup

The container has the explicit name `fraimic-studio` (one instance per Docker host).
Run `./deploy/manage.sh apply` after retrieving this change to let Compose replace
its previous generated name; do not manually create a second container.

The default `RESTART_POLICY=always` restarts the container after a Docker daemon
restart, including when it was stopped before that restart. A manual stop still
keeps it stopped until the daemon or container is started again. Set
`RESTART_POLICY=unless-stopped` if an intentional stop should survive daemon restarts.
The policy does not enable Unraid's array or Docker service: both must start first.
An unhealthy health check alone does not restart a running process.

Verify the applied setting on Unraid:

```bash
docker inspect fraimic-studio --format '{{.HostConfig.RestartPolicy.Name}}'
```

“3rd Party” in Unraid's Autostart column means the native UI is not managing this
container's startup; it does not report the Docker restart policy. For a Compose
Manager startup toggle, register an **indirect stack** named `fraimic-studio` using
the existing checkout's `deploy/docker` directory and its `.env`, then enable the
stack's Autostart. Do not copy the compose file elsewhere: its build context is
relative. Labels alone do not register a stack. Exact UI names depend on plugin
version. Keep Git updates via `manage.sh update`, not registry-based image updates.
Do not edit generated override labels independently of the Compose file, since
that would give the two launch paths different settings.

If the icon remains absent, inspect its actual applied label rather than assuming
Safari's icon issue has the same cause:

```bash
docker inspect fraimic-studio --format '{{index .Config.Labels "net.unraid.docker.icon"}}'
```

The Unraid host must itself be able to retrieve that URL with valid DNS/TLS. A
successful request from a Mac does not verify the server's DNS, routing or trust.
A missing label requires `apply`; a present label needs a check of the response
from the Unraid host and possibly its icon cache. Don't disable TLS verification
to conceal a certificate problem.

## One-command Git updates

Set these once in deploy/docker/.env, pointing at your deployment fork and branch:

```bash
GIT_REMOTE=your-remote-name
GIT_BRANCH=your-deployment-branch
```

The checkout must already be on that branch with a configured remote. Do not
blindly use the upstream Fraimic repository: it may not contain these changes.
The helper refuses dirty working trees and uses fast-forward-only updates.

```bash
./deploy/manage.sh update
```

This pulls from the configured Git remote, rebuilds the image (including checking
for a newer base image), and recreates the container only as necessary. DATA_DIR
is kept. No cron job or auto-update service runs. The helper re-reads the updated
script after pulling. It does not reset commits, switch branches or discard work.
If a pull succeeds but the build fails, the checkout is updated while the old
container stays running; fix the issue and run `start` again.

Useful commands:

```bash
./deploy/manage.sh status
./deploy/manage.sh logs
./deploy/manage.sh stop
```

Without the helper, use the same Compose file/environment:

```bash
docker compose --env-file deploy/docker/.env -f deploy/docker/compose.yaml build --pull
docker compose --env-file deploy/docker/.env -f deploy/docker/compose.yaml up -d --no-build --wait
```

Back up DATA_DIR before upgrading. To return to an earlier code revision, stop
work in this checkout, select that revision deliberately with Git, then run
`./deploy/manage.sh start` (not `update`). Configuration format migrations are not
automatically reversed. The current format remains version 1.

## Persistent configuration, disposable images

Only `/data` persists. `/tmp` is a 1 GiB tmpfs: sources, previews and BINs disappear
on container stop/recreation, including a forced stop. Individual browser-session
jobs stay available until shutdown, allowing previews and repeat sends. No job
history or converted-image archive is written to /data. Linux may swap tmpfs
pages if the host enables swap; it is not an archival disk volume.

The filesystem is read-only except /data and /tmp. No images, local environments,
Git metadata, secrets or frames.json enter the build context: the Dockerfile-specific
ignore file uses an allowlist. The image uses binary Python wheels only.
Compose limits memory to 4 GiB and CPU to 2 cores; adjust for your server. Large
images or many uploads in one session may exhaust the temporary space; restarting
clears it. SIGTERM requests graceful cleanup, with a two-minute stop grace period.
The Docker health check requests the local web server only, never a physical frame.
Battery checks still occur only after a successful upload.

## Nginx reverse proxy

Copy `deploy/nginx/fraimic.conf.example` into your Nginx configuration and replace:

- `fraimic.example.com` with your hostname;
- the two TLS certificate paths with certificates you already manage;
- `proxy_pass` with the address reachable from Nginx (Unraid IP if separate).

Set `FRAIMIC_PUBLIC_ORIGIN=https://fraimic.example.com` in the Docker .env and run
`./deploy/manage.sh start`. Validate with `nginx -t`, then reload Nginx using your
normal service management. The template neither creates certificates nor changes
any existing proxy. Deploy at the hostname root, not a subpath.

Host and Origin are preserved: don't replace Host with the upstream IP. HTTPS is
terminated at Nginx; the application checks the configured public origin and does
not blindly trust forwarded headers. If Nginx is another container, 127.0.0.1 means
that container, not the Unraid host. Use a reachable host IP or shared network.

This app has no login or user isolation. Use it on a trusted LAN/VPN. If exposing
it beyond that, enable authentication in Nginx (an example is included) or your
existing gateway, and restrict direct access to the backend port. The session
write token protects against cross-site requests, not other authorized LAN users.

## Verification status

Server host/origin protection and shutdown behaviour are tested locally, alongside
the existing application suite. The deployment helper is checked with simulated
Docker/Git commands. No Docker daemon is available in the development environment,
so an actual image build, HEIC Linux-wheel installation, container startup and
Unraid/Nginx deployment still need validation on the target host. No image has been
published to a registry and no remote server has been modified.

References: [Docker Compose build](https://docs.docker.com/reference/cli/docker/compose/build/),
[Docker Compose up](https://docs.docker.com/reference/cli/docker/compose/up/),
[Unraid container management](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/).
