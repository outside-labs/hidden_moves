"""Test application: bind a synthetic transport to the same configured host."""

import asyncio

from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.host import serve_client
from replay import ReplayTransport

if __name__ == "__main__":
	asyncio.run(serve_client(
		ProjectsClient("fixture-only", transport=ReplayTransport()), ["github.projects.items"],
	))
