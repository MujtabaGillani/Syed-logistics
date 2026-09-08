# Deployment workflow setup

`deploy.yml` deploys every push to `main`. It connects to a server that already
has a clone of this repository, resets that clone to `origin/main`, stops the
existing production Docker Compose stack, and rebuilds and starts it. Production
deployments use `docker-compose.production.yml`; the ordinary
`docker-compose.yml` remains available for local development.

Create a GitHub environment named `production`, then add these environment
secrets:

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | Server hostname or IP address |
| `DEPLOY_USER` | SSH user that can run Docker without `sudo` |
| `DEPLOY_SSH_KEY` | Private SSH key for that user |
| `DEPLOY_PATH` | Absolute path to the repository clone on the server |
| `DEPLOY_PORT` | SSH port (optional; defaults to `22`) |

Before enabling deployment, ensure the server clone has an `origin` remote that
can fetch `main` non-interactively and that Docker Compose is installed. The
production Compose configuration requires the pre-existing external Docker
network `proxy_net`.

The workflow intentionally uses `git reset --hard origin/main`. Keep the
server's production `.env` file untracked at the repository root; it supplies
database credentials and other environment settings to the containers and is
not overwritten by deployment. The PostgreSQL data is kept in the named
`postgres_data` volume, which is retained when the stack is stopped.
